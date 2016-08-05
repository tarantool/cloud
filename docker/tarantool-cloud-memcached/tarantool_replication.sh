#!/bin/sh

replication_status=$(tarantool <<-'EOF'
os = require("os")
netbox = require('net.box')
conn = netbox.new("localhost:3301")
print(conn:eval('return box.info.replication.status'))
os.exit()
EOF
)

if [ "$replication_status" = "follow" ]; then
    exit 0
else
    exit 1
fi
