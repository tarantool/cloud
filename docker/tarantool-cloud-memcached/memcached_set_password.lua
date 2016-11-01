#!/usr/bin/env tarantool

local os = require('os')

if arg[1] == nil then
    print("Usage: " .. arg[0] .. " <password>")
    os.exit(1)
end

local memcached_password = arg[1]

local cmd = "echo '" .. memcached_password .. "' |" ..
    "saslpasswd2 -p -c -a tarantool-memcached memcached"

os.execute(cmd)
