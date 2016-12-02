#!/usr/bin/env tarantool

local fio = require('fio')
local log = require('log')
local os = require('os')

local APP_FILE_PATH = '/opt/tarantool/app.lua'
local app_file_exists = fio.stat(APP_FILE_PATH) ~= nil

if not app_file_exists then
    log.info("No app present ('%s'). Running in 'database mode'", APP_FILE_PATH)
    box.cfg{}
else

    dofile(APP_FILE_PATH)
end
