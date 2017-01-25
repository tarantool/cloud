#!/bin/sh

replication_status=$( (tarantool <<-'EOF'
local CONSOLE_SOCKET_PATH = 'unix/:/var/run/tarantool/tarantool.sock'
local console = require('console')
local os = require("os")
local yaml = require("yaml")

console.on_start(function(self)
    local status, reason
    status, reason = pcall(function() require('console').connect(CONSOLE_SOCKET_PATH) end)
    if not status then
        self:print(reason)
        os.exit(1)
    end

    local cmd = 'box.info.replication'

    local res = self:eval(cmd)
    if res ~= nil then
        res = yaml.decode(res)
        local status = 'follow'
        for _, entry in pairs(res[1]) do
            if entry.status ~= 'follow' then
                status = 'error'
            end
        end
        print(status)
    end

    os.exit(0)
end)

console.on_client_disconnect(function(self) self.running = false end)
console.start()

os.exit(0)
EOF
) 2>/dev/null)

if [ "$replication_status" = "follow" ]; then
    exit 0
else
    exit 1
fi
