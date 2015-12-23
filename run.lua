local inspector = require('inspector')
box.cfg{listen=33011}
local cloud = inspector.new()
cloud:start()
