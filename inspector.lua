local docker = require('docker')
local fiber = require('fiber')
local log = require('log')
local netbox = require('net.box')

local MEMCACHED_PORT = 3301
local ADMIN_PORT = 3302
local TIMEOUT = 1
local IMAGE_NAME = 'memcached'

local STATE_READY = 0
local STATE_CHECK = 1

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

-- create spaces and indexes
local function create_spaces(self)
    log.info('Creating spaces...')
    local orders = box.schema.create_space('orders')
    _ = orders:create_index('primary', { type='hash', parts={1, 'num'} })

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

local function set_replication(self, pair)
    local master1 = pair[1]
    local master2 = pair[2]
    local uri1 = master1.info[2]..':'..tostring(ADMIN_PORT)
    local uri2 = master2.info[2]..':'..tostring(ADMIN_PORT)
    log.info('Set master-master replication between %s and %s', uri1, uri2)
    master2.conn:eval('box.cfg{replication_source="'..uri1..'"}')
    master1.conn:eval('box.cfg{replication_source="'..uri2..'"}')

    check1 = master1.conn:eval('return box.info.replication')
    check2 = master2.conn:eval('return box.info.replication')

    if check1.status ~= 'running' or check2.status ~= 'running' then
        -- FIXME: retry after replication error?
        log.error('Replication error between %s and %s', uri1, uri2)

        -- debug
        log.info(require('yaml').encode(check1))
        log.info(require('yaml').encode(check2))
    end
end

local function check_order(self, order)
    local pair = order[4]
    local pair_conn = {}
    local need_failover = false

    box.begin()
    box.space.orders:update(order[1], {{'=', 5, STATE_CHECK}})
    -- check servers
    for i, server in pairs(pair) do
        image_id, ip_addr, server_id = server[1], server[2], server[3]

        -- FIXME: extract connection from check_order() and save it
        conn = netbox:new(
            ip_addr .. ':' .. tostring(ADMIN_PORT),
            {wait_connected = false, reconnect_after=1}
        )
        if conn:wait_connected(TIMEOUT) and conn:ping() then
            log.info('%s is alive', ip_addr)
        else
            -- restart instance and udpate metadata
            log.info('%s is dead', ip_addr)
            local info = docker.run(IMAGE_NAME)
            pair[i][1] = info.Id
            pair[i][2] = info.NetworkSettings.Networks.bridge.IPAddress
            while not conn:is_connected() do
                fiber.sleep(0.001)
            end
            need_failover = true
        end
        pair_conn[i] = {conn=conn, info=pair[i]}
    end

    if need_failover then
        self:set_replication(pair_conn)
        -- save pair info
        box.space.orders:update(order[1], {{'=', 4, pair}})
    end
    box.space.orders:update(order[1], {{'=', 5, STATE_READY}})
    box.commit()
end

local function failover_fiber(self)
    fiber.name('memcached failover')
    while true do
        -- FIXME: replace select with range + limit
        instances = box.space.orders:select{}

        for _, tuple in pairs(instances) do
            if tuple[5] == STATE_READY then
                self:check_order(tuple)
            end
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
        set_replication = set_replication
    }
    return obj
end

local lib = {
    new = new
}
return lib
