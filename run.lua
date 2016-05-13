local inspector = require('inspector')
local fiber = require('fiber')
local log = require('log')
local PAIRS_LIMIT = 10

box.cfg{listen=33011}
local cloud = inspector.new()
cloud:start()

function list()
    return box.space.orders:select{}
end

function detail(id)
    return box.space.orders:select{tonumber(id)}
end

function create(name)
    -- check maximum pairs length
    if box.space.orders:len() >= PAIRS_LIMIT then
        return 1
    end
    local id1, server1 = cloud:add()
    local id2, server2 = cloud:add(server1)

    local order = {
        'demo'; name; {
            {id1; server1; 'test1'; 0;0;0;0; 'stopped'; 0; {}};
            {id2; server2; 'test2'; 0;0;0;0; 'stopped'; 0; {}};
        }; 0;
    }
    box.space.orders:auto_increment(order)
    return 0
end

function drop(lxc_id)
    -- container drop for demonstration
    cloud:drop(lxc_id)
    fiber.sleep(1)
    return 0
end

function delete(order_id)
    cloud:delete(tonumber(order_id))

    local t = box.space.orders:select{tonumber(order_id)}
    while #t > 0 do
        t = box.space.orders:select{tonumber(order_id)}
        fiber.sleep(0.01)
    end
    return 0
end
