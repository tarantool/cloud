#!/bin/sh

memory=$(tarantool <<-'EOF'
os = require("os")
netbox = require('net.box')
conn = netbox.new("localhost:3301")
print(conn:eval('return box.slab.info().quota_used'))
os.exit()
EOF
      )

echo "$memory"

case $memory in
    ''|*[!0-9]*) exit 2 ;;
    *) exit 0 ;;
esac
