local log = require('log')
local string = require('string')
local bit = require('bit')


function ip_str_to_int(ip_str)
   local ip_re = "(%d+)%.(%d+)%.(%d+)%.(%d+)"
   local ip = {string.match(ip_str, ip_re)}

   assert(next(ip) ~= nil, "ip_str must be valid ipv4 address")

   if next(ip) == nil then
      return nil
   end

   o1, o2, o3, o4 = unpack(ip)

   return 2^24*o1 + 2^16*o2 + 2^8*o3 + o4
end

function ip_int_to_str(ip_int)
   assert(type(ip_int) == "number", "ip_int must be number")

   result = ''
   for i = 3, 0, -1 do
      if i ~= 3 then
         result = result .. '.'
      end

      result = result .. bit.band(bit.rshift(ip_int, (bit.lshift(i, 3))), 255)

   end
   return result
end

function subnet_to_range(subnet_str)
   local subnet_re = "(%d+%.%d+%.%d+%.%d+)/(%d+)"
   local subnet = {string.match(subnet_str, subnet_re)}

   assert(next(subnet) ~= nil, "subnet_str must be valid ipv4 subnet")

   ip_str, mask = unpack(subnet)
   ip_min = bit.band(ip_str_to_int(ip_str),
                     bit.bnot(bit.lshift(1, mask) - 1))
   ip_max = bit.bor(ip_min, bit.lshift(1, mask) - 1)

   return ip_int_to_str(ip_min+1), ip_int_to_str(ip_max)
end

function is_subnet(subnet_str)
   subnet_re = "%d+%.%d+%.%d+%.%d+/%d+"

   return string.match(subnet_str, subnet_re) ~= nil
end

function subnet_get_ip(subnet_str)
   local subnet_re = "(%d+%.%d+%.%d+%.%d+)/(%d+)"
   local subnet = {string.match(subnet_str, subnet_re)}

   assert(next(subnet) ~= nil, "subnet_str must be valid ipv4 subnet")

   ip_str, mask = unpack(subnet)
   return ip_str
end


return {
   ip_str_to_int=ip_str_to_int,
   ip_int_to_str=ip_int_to_str,
   subnet_to_range=subnet_to_range,
   is_subnet=is_subnet,
   subnet_get_ip=subnet_get_ip
}
