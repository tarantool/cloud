local docker = require('docker')
local fiber = require('fiber')
local log = require('log')
local netbox = require('net.box')

local MEMCACHED_PORT = 3301
local ADMIN_PORT = 3302
local TIMEOUT = 1
local IMAGE_NAME = 'memcached'

--order schema
--{
--  id, user_id, pair_name,
--  [{
--    <image_id>, -- docker image id
--    <ip>,       -- service ip addr
--    <server_id> -- docker server id
--  }, ]
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

local function check_order(self, order)
    local pair = order[4]
    local pair_conn = {}
    local need_failover = false

    -- check servers
    for i, server in pairs(pair) do
        image_id, ip_addr, server_id = server[1], server[2], server[3]
        conn = netbox:new(
            ip_addr .. ':' .. tostring(ADMIN_PORT),
            {wait_connected = false}
        )
        if conn:wait_connected(TIMEOUT) and conn:ping() then
            log.info('%s is alive', ip_addr)
        else
            -- restart instance and udpate metadata
            log.info('%s is dead', ip_addr)
            local info = docker.run(IMAGE_NAME)
            pair[i][1] = info.Id
            pair[i][2] = info.NetworkSettings.Networks.bridge.IPAddress
            need_failover = true
        end
        pair_conn[i] = conn
    end

    if need_failover then
        -- self:set_replication(pair_conn)
    end

    -- save pair info
    box.space.orders:update(order[1], {{'=', 4, pair}})
end

local function failover_fiber(self)
    fiber.name('memcached failover')
    while true do
        -- FIXME: replace select with range + limit
        instances = box.space.orders:select{}

        for _, tuple in pairs(instances) do
            self:check_order(tuple)
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
        set_config = set_config
    }
    return obj
end

local lib = {
    new = new
}
return lib
