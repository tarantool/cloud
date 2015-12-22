#!/usr/bin/env tarantool
local EXPOSED_PORT = 3301
local memcached = require('memcached')

box.cfg{
    slab_alloc_arena = 0.5;
    wal_mode = 'none';
}

-- start memcached instance
instance = memcached.create('local_instance', '0.0.0.0:' .. tostring(EXPOSED_PORT))
