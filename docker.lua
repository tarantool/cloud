-- lua docker API
local log = require('log')
local client = require('http.client')
local json = require('json')

local DOCKER ='http://unix/:/var/run/docker.sock:'

local function request(method, uri, body)
    if body then
        body = json.encode(body)
    end
    local headers = { ["Content-Type"] = "application/json" }
    local r = client.request(method, DOCKER..uri, body, { headers = headers })
    if r.status < 200 or r.status >= 300 then
        log.error('failed to process docker request: %s %s %s', uri, r.status,
            r.body)
        return
    end
    log.debug('docker: %s %s [[%s]] => %s [[%s]]', method, uri, body or '',
    r.status, r.body)
    if #r.body == 0 then
        return true
    end
    return json.decode(r.body)
end

local function kill(lxc_id)
    local inf1 = request('POST', '/containers/'..lxc_id..'/kill')
    if not inf1 then
        return
    end
    log.info('killed container %s', lxc_id)
end

local function rm(lxc_id)
    kill(lxc_id)
    local inf2 = request('DELETE', '/containers/'..lxc_id)
    if not inf2 then
        return
    end
    log.info('removed container %s', lxc_id)
end

local function info(lxc_id)
    return request('GET', '/containers/'..lxc_id..'/json')
end

local function run(image, replica)
    local body = {
            Image = image;
    }
    if replica ~= nil then
        body['Env'] = {'REPLICA='..replica}
    end

    --  Create container
    local inf = request('POST', '/containers/create', body)
    if not inf or not inf.Id then
        log.error('failed to create container')
        return false
    end
    local lxc_id = inf.Id

    -- Start container    
    local inf = request('POST', '/containers/'..lxc_id..'/start',
        { Detach = true })
    if not inf then
        log.error('failed to start container')
        return false
    end

    -- Get container information
    local inf = info(lxc_id)
    return inf
end

return {
    run=run,
    rm=rm,
    kill=kill,
    info=info,
    request=request
}
