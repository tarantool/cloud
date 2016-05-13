local docker = require('docker')
local fiber = require('fiber')
local log = require('log')
local netbox = require('net.box')
local iputil = require('iputil')

local MEMCACHED_PORT = 3301
local ADMIN_PORT = 3302
local TIMEOUT = 1
local IMAGE_NAME = 'memcached'

local RPL_WORKING = 'follow'

local NODE_DOWN = 0
local NODE_WORKING = 1

local STATE_READY = 0
local STATE_CHECK = 1

local NETWORK_NAME='customnet'

--order schema
--{
--  id, user_id, pair_name,
--  [{
--    <image_id>, -- docker image id
--    <ip>,       -- service ip addr
--    <server_id> -- docker server id
--  }, ]
--  state
--}


local function lease_ip()
    local network = docker.inspect_network(NETWORK_NAME)

    local subnet = network.IPAM.Config[1].Subnet
    local gateway_subnet = network.IPAM.Config[1].Gateway
    if iputil.is_subnet(gateway_subnet) then
        gateway_ip = iputil.subnet_get_ip(gateway_subnet)
    else
        gateway_ip = gateway_subnet
    end
    local used_ips = {}
    for _, container in pairs(network.Containers) do
        used_ips[iputil.subnet_get_ip(container.IPv4Address)] = true
    end

    instances = box.space.orders:select{}
    for _, tuple in pairs(instances) do
        for _, server in pairs(tuple[4]) do
            used_ips[server[2]] = true
        end
    end

    local min_ip, max_ip = iputil.subnet_to_range(subnet)

    for int_ip = iputil.ip_str_to_int(min_ip), iputil.ip_str_to_int(max_ip) do
        ip = ip_int_to_str(int_ip)
        if used_ips[ip] == nil and ip ~= gateway_ip then
            return ip
        end
    end

    return false
end

-- create spaces and indexes
local function create_spaces(self)
    log.info('Creating spaces...')
    local orders = box.schema.create_space('orders')
    _ = orders:create_index('primary', { type='tree', parts={1, 'num'} })

    -- docker servers ip addresses list(min 3 required for failover)
    local servers = box.schema.create_space('servers')
    _ = servers:create_index('primary', { type='hash', parts={1, 'str'} })
    box.schema.user.grant('guest', 'read,write,execute', 'universe')
    log.info('Done')
end

-- check all cloud servers and fill servers space
local function set_config(self, config)
    log.info('Checking available docker servers...')
    -- need to implement server selection
end

-- setup master-master replication between memcached nodes
local function set_replication(self, pair)
    local master1 = pair[1]
    local master2 = pair[2]
    local uri1 = master1.info[2]..':'..tostring(ADMIN_PORT)
    local uri2 = master2.info[2]..':'..tostring(ADMIN_PORT)
    log.info('Set master-master replication between %s and %s', uri1, uri2)
    master1.conn:eval('box.cfg{replication_source="'..uri2..'"}')

    check1 = master1.conn:eval('return box.info.replication')
    check2 = master2.conn:eval('return box.info.replication')

    if check1.status ~= RPL_WORKING or check2.status ~= RPL_WORKING then
        -- FIXME: retry after replication error?
        log.error('Replication error between %s and %s', uri1, uri2)
    end
    -- debug demo
    log.info(require('yaml').encode(check1))
    log.info(require('yaml').encode(check2))
end

-- check do we need to start with replication source
local function get_new_master(pair)
    local master = nil
    if pair[1].conn:is_connected() then
        master = pair[1].info[2]
    elseif pair[2].conn:is_connected() then
        master = pair[2].info[2]
    end

    if master ~= nil then
        return master .. ':' .. tostring(ADMIN_PORT)
    end
end

-- netbox connections reuse
local function get_server(self, addr)
    if addr == '' then
        return nil
    end
    if self.servers[addr] == nil then
        self.servers[addr] = netbox.new(
            addr .. ':' .. tostring(ADMIN_PORT),
            {wait_connected = false, reconnect_after=1}
        )
    end
    return self.servers[addr]
end

local function add(self, master)
    ip = lease_ip()
    if master ~= nil then
        master =  master .. ':' .. tostring(ADMIN_PORT)
    end
    local info = docker.run(IMAGE_NAME, NETWORK_NAME, ip, master)
    return info.Id, info.NetworkSettings.Networks[NETWORK_NAME].IPAddress
end

local function drop(self, container_id)
    return docker.kill(container_id)
end

local function remove_order(self, order_id)
    -- remove order from space
    local t = box.space.orders:delete{order_id}
    local first = t[4][1]
    local second = t[4][2]

    --close connections
    self.servers[first[2]]:close()
    self.servers[second[2]]:close()

    -- remove connections
    self.servers[first[2]] = nil
    self.servers[second[2]] = nil

    -- kill and remove containers
    docker.rm(first[1])
    docker.rm(second[1])
end

local function delete(self, order_id)
    self.delete_list[order_id] = 1
    return 0
end

-- fix broken memcached pair
local function failover(self, order, pair_conn)
    local master = get_new_master(pair_conn)
    local pair = order[4]
    -- restart instance and udpate metadata
    for i, server in pairs(pair_conn) do
        if not server.conn:is_connected() then
            local info = docker.run(IMAGE_NAME, NETWORK_NAME, pair[i][2], master)
            pair[i][1] = info.Id
            pair[i][2] = info.NetworkSettings.Networks[NETWORK_NAME].IPAddress

            while not pair_conn[i].conn:is_connected() do
                fiber.sleep(0.001)
            end
            master = get_new_master(pair_conn)
        end
    end
    self:set_replication(pair_conn)
    -- save pair info
    box.space.orders:update(order[1], {{'=', 4, pair}})
end

-- check cloud order and restore it if need
local function check_order(self, order)
    local pair = order[4]
    local pair_conn = {}
    local need_failover = false

    box.space.orders:update(order[1], {{'=', 5, STATE_CHECK}})
    -- check servers
    for i, server in pairs(pair) do
        image_id, ip_addr, server_id = server[1], server[2], server[3]
        local conn = self:get_server(ip_addr)

        if conn:wait_connected(TIMEOUT) and conn:ping() then
            slabs = conn:eval('return box.slab.info()')
            pair[i][4] = slabs.quota_size
            pair[i][5] = slabs.quota_used

            pair[i][6] = slabs.arena_size
            pair[i][7] = slabs.arena_used

            pair[i][8] = conn:eval('return box.info.replication.status')
            pair[i][9] = NODE_WORKING
            pair[i][10] = conn:eval('return box.stat()')
            log.info('%s is alive', ip_addr)
        else
            log.info('%s is dead', ip_addr)
            need_failover = true
            pair[i][8] = 'error'
            pair[i][9] = NODE_DOWN
        end
        pair_conn[i] = {conn=conn, info=pair[i]}
    end

    box.space.orders:update(order[1], {{'=', 4, pair}})
    if need_failover then
        -- FIXME: delay for web demo
        ----------------------
        fiber.sleep(2)
        ----------------------
        self:failover(order, pair_conn)
    end

    -- check replication status from running nodes
    -- set master-master for new pairs
    if pair[1][8] ~= RPL_WORKING or pair[2][8] ~= RPL_WORKING then
        self:set_replication(pair_conn)
    end

    box.space.orders:update(order[1], {{'=', 5, STATE_READY}})
end

-- orders observer
local function failover_fiber(self)
    fiber.name('memcached failover')
    while true do
        -- FIXME: replace select with range + limit
        instances = box.space.orders:select{}

        for _, tuple in pairs(instances) do
            if tuple[5] == STATE_READY and
                    self.delete_list[tuple[1]] == nil then
                self:check_order(tuple)
            end
        end

        -- drop unused containers
        for id, x in pairs(self.delete_list) do
            self:remove_order(id)
            self.delete_list[id] = nil
        end
        fiber.sleep(0.1)
    end
end

-- cloud initialization
local function start(self, config)
    log.info('Memcached cloud started...')
    if box.space.orders == nil then
        self:create_spaces()
    end
    self:set_config(config)

    fiber.create(failover_fiber, self)
    log.info('Cloud is ready to serve.')
end

-- object wrapper
local function new(config)
    local obj = {
        start = start,
        create_spaces = create_spaces,
        check_order = check_order,
        set_config = set_config,
        set_replication = set_replication,
        failover = failover,
        get_server = get_server,
        add = add,
        delete = delete,
        remove_order = remove_order,
        delete_list = {},
        drop = drop,
        servers = {}
    }
    return obj
end

local lib = {
   new = new,
   lease_ip = lease_ip
}
return lib
