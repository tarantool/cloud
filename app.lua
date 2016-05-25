#!/usr/bin/env tarantool

http = require('http.server')

local replica = os.getenv('REPLICA')
local EXPOSED_PORT = 3301
local ADMIN_PORT = 3302
local memcached = require('memcached')
local fiber = require('fiber')

box.cfg{
    slab_alloc_arena = 0.5;
    wal_mode = 'write';
    listen = ADMIN_PORT;
    logger = './tnt.log';
    replication_source = replica;
}

if replica == nil or replica == '' then
    -- enable admin provison
    box.schema.user.grant('guest', 'read,write,execute', 'universe')
    box.schema.user.grant('guest', 'replication')
else
    -- wait for relay on init
    while box.space.instance == nil do
        fiber.sleep(0.1)
    end
end
-- start memcached instance
instance = memcached.create('instance', '0.0.0.0:' .. tostring(EXPOSED_PORT))

httpd = http.new('0.0.0.0', 8080)

function check(self)
    return {
        status = 200,
        headers = { ['content-type'] = 'text/html; charset=utf8' },
        body = [[
            <html>
                <body>OK</body>
            </html>
        ]]
    }
end

httpd:route(
     { path = '/ping' }, check)
httpd:start()
