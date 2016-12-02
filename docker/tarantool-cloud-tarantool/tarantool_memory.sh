#!/bin/sh

memory=$( (tarantool <<-'EOF'
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

    cmd = 'box.slab.info().quota_used'
    local res = self:eval(cmd)
    if res ~= nil then
        res = yaml.decode(res)
        print(res[1])
    end

    os.exit(0)
end)

console.on_client_disconnect(function(self) self.running = false end)
console.start()

os.exit(0)
EOF
) 2>/dev/null)


echo "$memory"

case $memory in
    ''|*[!0-9]*) exit 2 ;;
    *) exit 0 ;;
esac
