#!/usr/bin/env tarantool

http = require('http.server')
prometheus = require('tarantool-prometheus')

local replica = os.getenv('REPLICA')
local arena = tonumber(os.getenv('ARENA')) or 0.5
local EXPOSED_PORT = 3301
local ADMIN_PORT = 3302
local memcached = require('memcached')
local fiber = require('fiber')

box.cfg{
    slab_alloc_arena = arena;
    wal_mode = 'write';
    listen = ADMIN_PORT;
    replication_source = replica;
}

if replica == nil or replica == '' then
    -- enable admin provison
    box.schema.user.grant('guest', 'read,write,execute',
                          'universe', nil, {if_not_exists=true})
    box.schema.user.grant('guest', 'replication', nil, nil, {if_not_exists=true})
else
    -- wait for relay on init
    while box.space.instance == nil do
        fiber.sleep(0.1)
    end
end
-- start memcached instance
instance = memcached.create('instance', '0.0.0.0:' .. tostring(EXPOSED_PORT))

httpd = http.new('0.0.0.0', 8080)

prometheus.init()

httpd:route( { path = '/metrics' }, prometheus.collect_http)
httpd:start()
