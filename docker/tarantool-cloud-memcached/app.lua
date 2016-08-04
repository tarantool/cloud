#!/usr/bin/env tarantool

http = require('http.server')
prometheus = require('tarantool-prometheus')

local EXPOSED_PORT = 11211
local memcached = require('memcached')
local fiber = require('fiber')
local yaml = require('yaml')
local fio = require('fio')
local errno = require('errno')

box.cfg {
    wal_mode = 'write';
}

box.once(
    "memcached-init",
    function()
        box.schema.user.grant('guest', 'read,write,execute',
                              'universe', nil, {if_not_exists=true})
        box.schema.user.grant('guest', 'replication', nil, nil, {if_not_exists=true})
    end
)

-- start memcached instance
instance = memcached.create('instance', '0.0.0.0:' .. tostring(EXPOSED_PORT))

httpd = http.new('0.0.0.0', 8080)

prometheus.init()

httpd:route( { path = '/metrics' }, prometheus.collect_http)
httpd:start()
