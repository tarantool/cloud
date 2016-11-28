#!/usr/bin/env tarantool

local http = require('http.server')
local prometheus = require('tarantool-prometheus')

local EXPOSED_PORT = 11211
local memcached = require('memcached')
local fiber = require('fiber')
local yaml = require('yaml')
local fio = require('fio')
local errno = require('errno')
local os = require('os')
local AUTH_FILE_PATH = '/opt/tarantool/auth.sasldb'

local memcached_password = os.getenv('MEMCACHED_PASSWORD') or nil
local memcached_password_base64 = os.getenv('MEMCACHED_PASSWORD_BASE64') or nil

local auth_file_exists = fio.stat(AUTH_FILE_PATH) ~= nil

if memcached_password_base64 ~= nil and not auth_file_exists then
    local cmd = "echo '" .. memcached_password_base64 .. "' |" ..
        "base64 -d | gunzip > '" .. AUTH_FILE_PATH .. "'"
    os.execute(cmd)
    auth_file_exists = true
end

if memcached_password ~= nil and not auth_file_exists then
    local cmd = "echo '" .. memcached_password .. "' |" ..
        "saslpasswd2 -p -c -a tarantool-memcached memcached"

    os.execute(cmd)
    auth_file_exists = true
end

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

function collect_stats()
    local instance = memcached.get("instance")

    local requests_total = prometheus.gauge(
        'memcached_requests_total',
        'Total number of memcached requests by request type',
        {'request_type'})

    local read_bytes = prometheus.gauge(
        'memcached_read_bytes',
        'Total number of bytes read')

    local write_bytes = prometheus.gauge(
        'memcached_write_bytes',
        'Total number of bytes written')

    local request_tags = {
        'cmd_get', 'get_hits', 'get_misses',
        'cmd_delete', 'delete_hits', 'delete_misses',
        'cmd_set', 'cas_hits', 'cas_badval', 'cas_misses',
        'cmd_incr', 'incr_hits', 'incr_misses',
        'cmd_decr', 'decr_hits', 'decr_misses',
        'cmd_touch', 'touch_hits', 'touch_misses',
        'cmd_flush'}

    while true do
        local stats = instance:info()

        for _, v in pairs(request_tags) do
            requests_total:set(tonumber(stats[v]), {v})
        end

        read_bytes:set(tonumber(stats['bytes_read']))
        write_bytes:set(tonumber(stats['bytes_written']))

        fiber.sleep(5)
    end
end

-- start memcached instance
if auth_file_exists then
    memcached.create('instance', '0.0.0.0:' .. tostring(EXPOSED_PORT),
                     {sasl = true})
else
    memcached.create('instance', '0.0.0.0:' .. tostring(EXPOSED_PORT))
end


fiber.create(collect_stats)

local httpd = http.new('0.0.0.0', 8080)

prometheus.init()

httpd:route( { path = '/metrics' }, prometheus.collect_http)
httpd:start()
