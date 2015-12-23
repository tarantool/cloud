#!/usr/bin/env tarantool
local EXPOSED_PORT = 3301
local ADMIN_PORT = 3302
local memcached = require('memcached')

box.cfg{
    slab_alloc_arena = 0.5;
    wal_mode = 'none';
    listen = ADMIN_PORT;
}

-- enable admin provison
box.schema.user.grant('guest', 'read,write,execute', 'universe')

-- start memcached instance
instance = memcached.create('instance', '0.0.0.0:' .. tostring(EXPOSED_PORT))
