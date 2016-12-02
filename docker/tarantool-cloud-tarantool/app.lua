#!/usr/bin/env tarantool

local fio = require('fio')
local log = require('log')
local os = require('os')
local http = require('http.server')
local prometheus = require('tarantool-prometheus')

local APP_FILE_PATH = '/opt/tarantool/app.lua'
local app_file_exists = fio.stat(APP_FILE_PATH) ~= nil

local httpd = http.new('0.0.0.0', 8080)

prometheus.init()

httpd:route( { path = '/metrics' }, prometheus.collect_http)
httpd:start()


if not app_file_exists then
    log.info("No app present ('%s'). Running in 'database mode'", APP_FILE_PATH)
    box.cfg{}
else

    dofile(APP_FILE_PATH)
end
