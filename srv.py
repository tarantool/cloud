#!/usr/bin/env python3

import gevent
from gevent import monkey
monkey.patch_all()

import os
import sys
import uuid
import ipaddress
import memcached
import tarantino
import tarantool
import sense
import global_env
import logging
import consul
import docker
import argparse
import yaml
import ip_pool
import backup_storage
import task

import werkzeug

from gevent.wsgi import WSGIServer
import flask
from flask import Flask
from flask import Response
from flask_restful import reqparse, abort, Api, Resource
from flask_bootstrap import Bootstrap
from flask_basicauth import BasicAuth

app = Flask(__name__)
app.config['DEBUG'] = True
api = Api(app)
Bootstrap(app)
BasicAuth(app)

TASKS = {}

def abort_if_group_doesnt_exist(group_id):
    if group_id not in sense.Sense.blueprints():
        abort(404, message="group {} doesn't exist".format(group_id))

def abort_if_instance_doesnt_exist(instance_id):
    group_id, instance_num = instance_id.split('_')
    blueprints = sense.Sense.blueprints()

    if group_id in blueprints:
        if instance_num in blueprints[group_id]['instances']:
            return

    abort(404, message="instance {} doesn't exist".format(instance_id))


def abort_if_backup_doesnt_exist(backup_id):
    if backup_id not in sense.Sense.backups():
        abort(404, message="backup {} doesn't exist".format(backup_id))


def state_to_dict(state_name):
    if state_name == 'passing':
        return {'id': '1', 'name': 'OK', 'type': 'passing'}
    if state_name == 'warning':
        return {'id': '2', 'name': 'Degraded', 'type': 'warning'}
    if state_name == 'critical':
        return {'id': '3', 'name': 'Down', 'type': 'critical'}

    raise RuntimeError("No such state: '%s'" % state_name)

def instance_to_dict(instance_id):
    group_id, instance_num = instance_id.split('_')

    memc = memcached.Memcached.get(group_id)
    blueprint = memc.blueprint
    allocation = memc.allocation
    services = memc.services

    addr = blueprint['instances'][instance_num]['addr']
    host = allocation['instances'][instance_num]['host']
    type_str = blueprint['type']
    name = instance_num
    instance_id = group_id + '_' + instance_num
    state = services['instances'][instance_num]['status']
    port = services['instances'][instance_num]['port']
    mem_used = services['instances'][instance_num]['mem_used']

    return {'id': instance_id,
            'name': name,
            'addr': addr,
            'port': port,
            'type': type_str,
            'host': host,
            'state': state_to_dict(state),
            'mem_used': mem_used}


def backup_to_dict(backup_id):
    backups = sense.Sense.backups()

    backup = backups[backup_id]

    return {'id': backup_id,
            'archive_id': backup['archive_id'],
            'group_id': backup['group_id'],
            'type': backup['type'],
            'creation_time': backup['creation_time'].isoformat(),
            'size': backup['size'],
            'mem_used': backup['mem_used'],
            'storage': backup['storage']}


def group_to_dict(group_id):
    memc = memcached.Memcached.get(group_id)
    blueprint = memc.blueprint
    allocation = memc.allocation
    services = memc.services
    containers = sense.Sense.containers().get(group_id,
                                              {'instances': {}})

    state = 'passing'

    states = [i['status'] for i in services['instances'].values()]
    state = sense.combine_consul_statuses(states)

    instances = []

    for instance_num in blueprint['instances']:
        addr = blueprint['instances'][instance_num]['addr']

        type_str = blueprint['type']
        name = instance_num
        instance_id = group_id + '_' + instance_num

        if instance_num in allocation['instances']:
            host = allocation['instances'][instance_num]['host']
        else:
            host = "N/A"

        if instance_num in services['instances']:
            instance_state = services['instances'][instance_num]['status']
            port = services['instances'][instance_num]['port']
            mem_used = services['instances'][instance_num]['mem_used']
        else:
            instance_state = 'critical'
            port = None
            mem_used = None

        image_name = None
        image_id = None
        if instance_num in containers['instances']:
            image_name = containers['instances'][instance_num]['docker_image_name']
            image_id = containers['instances'][instance_num]['docker_image_id']

        instances.append({'id': instance_id,
                          'name': name,
                          'addr': addr,
                          'port': port,
                          'type': type_str,
                          'host': host,
                          'state': state_to_dict(instance_state),
                          'docker_image_name': image_name,
                          'docker_image_id': image_id,
                          'mem_used': mem_used})

    result = {'name': blueprint['name'],
              'id': group_id,
              'memsize': blueprint['memsize'],
              'type': blueprint['type'],
              'creation_time': blueprint['creation_time'].isoformat(),
              'state': state_to_dict(state),
              'instances': instances}

    return result


class UpdateImagesTask(task.Task):
    task_type = "update_images"

    def __init__(self):
        super().__init__(self.task_type)

    def get_dict(self, index=None):
        obj = super().get_dict(index)
        return obj



class Group(Resource):
    def get(self, group_id):
        abort_if_group_doesnt_exist(group_id)
        return group_to_dict(group_id)

    def delete(self, group_id):
        abort_if_group_doesnt_exist(group_id)

        parser = reqparse.RequestParser(bundle_errors=True)
        parser.add_argument('async', type=bool, default=False)
        args = parser.parse_args()

        abort_if_group_doesnt_exist(group_id)

        blueprints = sense.Sense.blueprints()
        group = blueprints[group_id]

        if group['type'] == 'memcached':
            delete_task = memcached.DeleteTask(group_id)
            TASKS[delete_task.task_id] = delete_task

            memc = memcached.Memcached.get(group_id)
            gevent.spawn(memc.delete, delete_task)
        elif group['type'] == 'tarantino':
            delete_task = tarantino.DeleteTask(group_id)
            TASKS[delete_task.task_id] = delete_task

            tar = tarantino.Tarantino.get(group_id)
            gevent.spawn(tar.delete, delete_task)
        elif group['type'] == 'tarantool':
            delete_task = tarantool.DeleteTask(group_id)
            TASKS[delete_task.task_id] = delete_task

            tar = tarantool.Tarantool.get(group_id)
            gevent.spawn(tar.delete, delete_task)

        if args['async']:
            result = {'id': group_id,
                      'task_id': delete_task.task_id}
            return result, 202
        else:
            delete_task.wait_for_completion()
            return '', 204

    def put(self, group_id):
        abort_if_group_doesnt_exist(group_id)

        parser = reqparse.RequestParser(bundle_errors=True)
        parser.add_argument('name', default='')
        parser.add_argument('memsize', type=int)
        parser.add_argument('async', type=bool, default=False)
        parser.add_argument('heal', type=bool, default=False)
        parser.add_argument('password', type=str)
        parser.add_argument('docker_image_name')
        parser.add_argument('config',
                            type=werkzeug.datastructures.FileStorage,
                            location='files')
        parser.add_argument('config_is_dir', type=bool, default=False)
        parser.add_argument('backup_id', type=str)
        args = parser.parse_args()

        blueprints = sense.Sense.blueprints()
        group = blueprints[group_id]

        if not global_env.backup_storage:
            abort(500, message="Backup storage not configured")

        storage = global_env.backup_storage

        if group['type'] == 'memcached':
            memc = memcached.Memcached.get(group_id)

            update_task = memcached.UpdateTask(group_id)
            TASKS[update_task.task_id] = update_task

            gevent.spawn(memc.update,
                         args['name'],
                         args['memsize'],
                         args['password'],
                         args['docker_image_name'],
                         args['heal'],
                         args['backup_id'],
                         storage,
                         update_task)

        elif group['type'] == 'tarantino':
            tar = tarantino.Tarantino.get(group_id)

            update_task = tarantino.UpdateTask(group_id)
            TASKS[update_task.task_id] = update_task

            config_data = None
            if args['config']:
                stream = args['config'].stream
                config_data = stream.getvalue().decode(encoding='UTF-8')

            gevent.spawn(tar.update,
                         args['name'],
                         args['memsize'],
                         args['password'],
                         config_data,
                         args['docker_image_name'],
                         update_task)
        elif group['type'] == 'tarantool':
            tar = tarantool.Tarantool.get(group_id)

            update_task = tarantool.UpdateTask(group_id)
            TASKS[update_task.task_id] = update_task

            config_data = None
            config_filename = None
            if args['config']:
                stream = args['config'].stream
                config_data = stream.getvalue()
                config_filename = args['config'].filename

            gevent.spawn(tar.update,
                         args['name'],
                         args['memsize'],
                         args['password'],
                         config_data,
                         config_filename,
                         args['docker_image_name'],
                         args['heal'],
                         args['backup_id'],
                         storage,
                         update_task)
        else:
            raise RuntimeError("Unknown group type: %s" % group['type'])

        if args['async']:
            result = {'id': update_task.group_id,
                      'task_id': update_task.task_id}
            return result, 202

        else:
            update_task.wait_for_completion()
            return group_to_dict(group_id), 201


class GroupList(Resource):
    def get(self):
        blueprints = sense.Sense.blueprints()

        result = {}
        for group_id in blueprints:
            result[group_id] = group_to_dict(group_id)
        return result

    def post(self):
        parser = reqparse.RequestParser(bundle_errors=True)
        parser.add_argument('type', required=True)
        parser.add_argument('name', required=True)
        parser.add_argument('memsize', type=int, default=500)
        parser.add_argument('password', type=str, default=None)
        parser.add_argument('async', type=bool, default=False)

        logging.info("Creating instance")

        args = parser.parse_args()
        args['name'] = args['name'] or ''

        group_id = uuid.uuid4().hex

        if args['type'] == 'memcached':
            create_task = memcached.CreateTask(group_id)
            TASKS[create_task.task_id] = create_task

            gevent.spawn(memcached.Memcached.create,
                         create_task,
                         args['name'],
                         args['memsize'],
                         args['password'],
                         10)
        elif args['type'] == 'tarantino':
            create_task = tarantino.CreateTask(group_id)
            TASKS[create_task.task_id] = create_task

            gevent.spawn(tarantino.Tarantino.create,
                         create_task,
                         args['name'],
                         args['memsize'],
                         args['password'],
                         10)
        elif args['type'] == 'tarantool':
            create_task = tarantool.CreateTask(group_id)
            TASKS[create_task.task_id] = create_task

            gevent.spawn(tarantool.Tarantool.create,
                         create_task,
                         args['name'],
                         args['memsize'],
                         args['password'],
                         10)
        else:
            raise RuntimeError('No such instance type: %s' % args['type'])

        if args['async']:
            result = {'id': create_task.group_id,
                      'task_id': create_task.task_id}
            return result, 202

        else:
            create_task.wait_for_completion()
            return group_to_dict(create_task.group_id), 201

class Task(Resource):
    def get(self, task_id):
        parser = reqparse.RequestParser(bundle_errors=True)
        parser.add_argument('index', type=int)

        args = parser.parse_args()

        if task_id not in TASKS:
            abort(404, message="task {} doesn't exist".format(task_id))

        if args['index']:
            TASKS[task_id].wait(args['index'])

        return TASKS[task_id].get_dict(args['index'])


class TaskList(Resource):
    def get(self):
        result = {}

        for task_id, task in TASKS.items():
            result[task_id] = task.get_dict().copy()
            del result[task_id]['logs']

        return result


class ServerList(Resource):
    def get(self):
        result = {}

        for entry in sense.Sense.docker_hosts():
            result[entry['addr']] = {
                'addr': entry['addr'],
                'state': state_to_dict(entry['status']),
                'tags': entry['tags'],
                'cpus': entry['cpus'],
                'memory': entry['memory']
            }

        return result


class Backup(Resource):
    def get(self, backup_id):
        abort_if_backup_doesnt_exist(backup_id)
        result = {}
        result[backup_id] = backup_to_dict(backup_id)
        return result

    def delete(self, backup_id):
        parser = reqparse.RequestParser(bundle_errors=True)
        parser.add_argument('async', type=bool, default=False)
        args = parser.parse_args()

        abort_if_backup_doesnt_exist(backup_id)

        delete_task = backup_storage.DeleteTask(backup_id)
        TASKS[delete_task.task_id] = delete_task

        if not global_env.backup_storage:
            abort(500, message="Backup storage not configured")

        storage = global_env.backup_storage
        gevent.spawn(storage.unregister_backup, backup_id, delete_task)

        if args['async']:
            result = {'id': backup_id,
                      'task_id': delete_task.task_id}
            return result, 202
        else:
            delete_task.wait_for_completion()
            return '', 204


class BackupData(Resource):
    def get(self, backup_id):
        abort_if_backup_doesnt_exist(backup_id)
        backup = backup_to_dict(backup_id)
        archive_id = backup['archive_id']

        storage = global_env.backup_storage
        fobj = storage.get_archive(archive_id, decompress=False)

        def download_backup():
            chunk_size = 8192
            while True:
                chunk = fobj.read(chunk_size)

                if len(chunk) == 0:
                    return

                yield chunk

        return Response(download_backup(),
                        mimetype="application/gzip",
                        headers={"Content-Disposition":
                                 "attachment;filename=backup.tar.gz",
                                 "Content-Length": backup['size']})


class BackupList(Resource):
    def get(self):
        backups = sense.Sense.backups()

        result = {}
        for backup_id in backups.keys():
            result[backup_id] = backup_to_dict(backup_id)

        return result

    def post(self):
        parser = reqparse.RequestParser(bundle_errors=True)
        parser.add_argument('async', type=bool, default=False)
        parser.add_argument('group_id', default='')
        parser.add_argument('type', required=True)
        parser.add_argument('file',
                            type=werkzeug.datastructures.FileStorage,
                            location='files',
                            required=True)

        args = parser.parse_args()

        group_id = args['group_id']
        group_type = args['type']
        stream = args['file'].stream

        if not global_env.backup_storage:
            abort(500, message="Backup storage not configured")

        storage = global_env.backup_storage

        if group_type not in ['memcached', 'tarantino', 'tarantool']:
            raise RuntimeError("Unknown group type: %s" % group_type)

        digest, total_size = storage.put_archive(stream, compress=False)

        backup_id = uuid.uuid4().hex

        upload_task = backup_storage.UploadTask(backup_id)
        TASKS[upload_task.task_id] = upload_task

        def upload_backup(upload_task, storage, group_type, digest, total_size):
            backup_id = upload_task.backup_id

            try:
                upload_task.log("Validating backup")
                if group_type == 'memcached':
                    backup_is_valid = memcached.backup_is_valid(storage, digest)
                elif group_type == 'tarantino':
                    backup_is_valid = tarantino.backup_is_valid(storage, digest)
                elif group_type == 'tarantool':
                    backup_is_valid = tarantool.backup_is_valid(storage, digest)

                if not backup_is_valid:
                    upload_task.set_status(task.STATUS_CRITICAL,
                                           "Backup is not valid")
                    return
                storage.register_backup(backup_id, digest, group_id,
                                        group_type, total_size, 0)

                sense.Sense.update()
                upload_task.set_status(task.STATUS_SUCCESS)
            except Exception as ex:
                logging.exception("Failed to upload backup '%s'", backup_id)
                upload_task.set_status(task.STATUS_CRITICAL, str(ex))
                raise

        gevent.spawn(upload_backup, upload_task, storage, group_type,
                     digest, total_size)

        if args['async']:
            result = {'id': upload_task.backup_id,
                      'task_id': upload_task.task_id}
            return result, 202

        else:
            upload_task.wait_for_completion()
            return backup_to_dict(backup_id), 201



class InstanceBackup(Resource):
    def get(self, group_id, backup_id):
        return {}


class InstanceBackupList(Resource):
    def get(self):
        return {}

    def post(self, group_id):
        abort_if_group_doesnt_exist(group_id)

        parser = reqparse.RequestParser(bundle_errors=True)
        parser.add_argument('async', type=bool, default=False)

        args = parser.parse_args()

        blueprints = sense.Sense.blueprints()
        group = blueprints[group_id]

        args = parser.parse_args()
        backup_id = uuid.uuid4().hex

        if not global_env.backup_storage:
            abort(500, message="Backup storage not configured")

        storage = global_env.backup_storage

        if group['type'] == 'memcached':
            backup_task = memcached.BackupTask(group_id, backup_id)
            TASKS[backup_task.task_id] = backup_task
            memc = memcached.Memcached.get(group_id)

            gevent.spawn(memc.backup,
                         backup_task,
                         storage)
        elif group['type'] == 'tarantool':
            backup_task = memcached.BackupTask(group_id, backup_id)
            TASKS[backup_task.task_id] = backup_task
            tar = tarantool.Tarantool.get(group_id)

            gevent.spawn(tar.backup,
                         backup_task,
                         storage)
        else:
            raise RuntimeError('Instance type unsupported: %s' % args['type'])

        if args['async']:
            result = {'id': backup_task.backup_id,
                      'task_id': backup_task.task_id}
            return result, 202

        else:
            backup_task.wait_for_completion()
            return backup_to_dict(backup_id), 201


class StateList(Resource):
    def get(self):
        return {'1': {'id': '1', 'name': 'OK', 'type': 'passing'},
                '2': {'id': '2', 'name': 'Degraded', 'type': 'warning'},
                '3': {'id': '3', 'name': 'Down', 'type': 'critical'}}


class Instance(Resource):
    def get(self, instance_id):
        abort_if_instance_doesnt_exist(instance_id)

        return instance_to_dict(instance_id)


class InstanceList(Resource):
    def get(self):
        instances = {}

        result = {}
        for group_id, group in sense.Sense.blueprints().items():
            for instance_num in group['instances']:
                instance_id = group_id + '_' + instance_num

                result[instance_id] = instance_to_dict(instance_id)

        return result


def update_images(update_task):
    try:
        update_task.log("Updating docker images")
        docker_hosts = sense.Sense.docker_hosts()

        for docker_host in docker_hosts:
            docker_addr = docker_host['addr']
            update_task.log("Updating tarantool image on host %s",
                            docker_addr)
            tarantool.Tarantool.ensure_image(docker_addr, force=True)
            update_task.log("Updating memcached image on host %s",
                            docker_addr)
            memcached.Memcached.ensure_image(docker_addr, force=True)

        update_task.set_status(task.STATUS_SUCCESS)
    except Exception as ex:
        logging.exception("Failed to update images")
        update_task.set_status(task.STATUS_CRITICAL, str(ex))


class UpdateImages(Resource):
    def post(self):
        parser = reqparse.RequestParser(bundle_errors=True)
        parser.add_argument('async', type=bool, default=False)
        args = parser.parse_args()

        update_task = UpdateImagesTask()
        TASKS[update_task.task_id] = update_task
        gevent.spawn(update_images, update_task)

        if args['async']:
            result = {'task_id': update_task.task_id}
            return result, 202

        else:
            update_task.wait_for_completion()
            return {}, 201


def setup_routes():
    api.add_resource(GroupList, '/api/groups')
    api.add_resource(Group, '/api/groups/<group_id>')

    api.add_resource(InstanceList, '/api/instances')
    api.add_resource(Instance, '/api/instances/<instance_id>')

    api.add_resource(InstanceBackupList,
                     '/api/groups/<group_id>/backups')
    api.add_resource(InstanceBackup,
                     '/api/groups/<group_id>/backups/<backup_id>')

    api.add_resource(StateList, '/api/states')

    api.add_resource(TaskList, '/api/tasks')
    api.add_resource(Task, '/api/tasks/<task_id>')

    api.add_resource(BackupList, '/api/backups')
    api.add_resource(Backup, '/api/backups/<backup_id>')
    api.add_resource(BackupData, '/api/backups/<backup_id>/data')

    api.add_resource(ServerList, '/api/servers')

    api.add_resource(UpdateImages, '/api/update_images')


@app.route('/servers')
def list_servers():
    servers = sense.Sense.docker_hosts()
    blueprints = sense.Sense.blueprints()
    allocations = sense.Sense.allocations()

    result = []

    for server in servers:
        addr = server['addr'].split(':')[0]
        used_mem = 0
        for group_id, allocation in allocations.items():
            blueprint = blueprints[group_id]
            for instance in allocation['instances'].values():
                if addr == instance['host']:
                    used_mem = used_mem + blueprint['memsize']

        result.append({'status': server['status'],
                       'cpus': server['cpus'],
                       'memory': server['memory'],
                       'used_memory': used_mem,
                       'addr': server['addr'],
                       'consul_host': server['consul_host']})

    return flask.render_template('server_list.html', servers=result)

@app.route('/groups', methods=['GET'])
@app.route('/', methods=['GET'])
def list_groups():
    blueprints = sense.Sense.blueprints()
    services = sense.Sense.services()
    result = {}
    for group_id in blueprints:
        result[group_id] = group_to_dict(group_id)
        mem = 0
        if group_id in services:
            mem = max([i['mem_used']
                       for i in services[group_id]['instances'].values()])
        result[group_id]['mem_used'] = mem

    return flask.render_template('group_list.html', groups=result.values())

@app.route('/groups/<group_id>', methods=['GET'])
def show_group(group_id):
    services = sense.Sense.services()
    mem = 0
    if group_id in services:
        mem = max([i['mem_used']
                   for i in services[group_id]['instances'].values()])
    group = group_to_dict(group_id)
    group['mem_used'] = mem

    return flask.render_template('group.html', group=group)

@app.route('/groups', methods=['POST'])
def create_group():
    name=flask.request.form['name']

    try:
        memsize=int(flask.request.form['memsize'])
    except ValueError:
        memsize = 500

    group_id = uuid.uuid4().hex
    create_task = memcached.CreateTask(group_id)
    TASKS[create_task.task_id] = create_task

    memcached.Memcached.create(create_task, name, memsize, None, 10)

    return flask.redirect("/groups")

@app.route('/groups/<group_id>/resize', methods=['POST'])
def resize_group(group_id):
    memsize = None
    try:
        memsize=int(flask.request.form['memsize'])
    except ValueError:
        return flask.redirect("/groups")

    update_task = memcached.UpdateTask(group_id)
    TASKS[update_task.task_id] = update_task

    memc = memcached.Memcached.get(group_id)
    memc.resize(memsize, update_task)

    return flask.redirect("/groups")


@app.route('/groups/<group_id>/delete', methods=['POST'])
def delete_group(group_id):
    memc = memcached.Memcached.get(group_id)

    delete_task = memcached.DeleteTask(group_id)
    memc.delete(delete_task)

    return flask.redirect("/groups")

@app.route('/network', methods=['GET', 'POST'])
def network_settings():
    consul_obj = consul.Consul(host=global_env.consul_host,
                               token=global_env.consul_acl_token)
    kv = consul_obj.kv.get('tarantool_settings', recurse=True)[1] or []
    default = global_env.default_network_settings
    settings = {'network_name': None, 'subnet': None}
    for item in kv:
        if item['Key'].endswith('/network_name'):
            settings['network_name'] = item['Value'].decode('ascii')
        if item['Key'].endswith('/subnet'):
            settings['subnet'] = item['Value'].decode('ascii')

    settings['network_name'] = settings['network_name'] or default['network_name']
    settings['subnet'] = settings['subnet'] or default['subnet']

    if flask.request.method == 'POST':
        error = None
        network_name = flask.request.form.get('network_name')
        subnet = flask.request.form.get('subnet')

        try:
            decoded_subnet = ipaddress.ip_network(subnet)
        except ValueError:
            decoded_subnet = None

        if network_name == None:
            error = 'Network name not specified'
        elif subnet == None:
            error = 'Subnet not specified'
        elif not decoded_subnet:
            error = 'Subnet is invalid'

        if not error:
            consul_obj.kv.put('tarantool_settings/network_name', network_name)
            consul_obj.kv.put('tarantool_settings/subnet', str(decoded_subnet))

        return flask.redirect(flask.url_for('network_settings',
                                            error=error))
    else:
        error = flask.request.args.get("error")
        return flask.render_template('network.html',
                                     settings=settings, error=error)



def get_config(config_file):
    cfg = {}
    if config_file:
        with open(config_file, 'r') as stream:
            try:
                cfg = yaml.load(stream)
            except yaml.YAMLError as exc:
                print("Failed to parse config file:\n" + str(exc))
                sys.exit(1)

    opts = ['CONSUL_HOST', 'DOCKER_CLIENT_CERT',
            'DOCKER_SERVER_CERT', 'DOCKER_CLIENT_KEY',
            'CONSUL_ACL_TOKEN', 'HTTP_BASIC_USERNAME',
            'HTTP_BASIC_PASSWORD', 'LISTEN_ADDR', 'LISTEN_PORT',
            'IPALLOC_RANGE', 'DOCKER_NETWORK',
            'CREATE_NETWORK_AUTOMATICALLY', 'GATEWAY_IP',
            'BACKUP_STORAGE_TYPE', 'BACKUP_BASE_DIR',
            'BACKUP_HOST', 'BACKUP_IDENTITY', 'BACKUP_USER',
            'SSL_KEYFILE', 'SSL_CERTFILE']

    for opt in opts:
        if opt in os.environ:
            cfg[opt] = os.environ[opt]

    return cfg


def main():
    # Don't spam with HTTP connection logs from 'requests' module
    logging.getLogger("requests").setLevel(logging.WARNING)

    logging.basicConfig(format='%(levelname)s: %(message)s',
                        level=logging.INFO)

    parser = argparse.ArgumentParser()
    parser.add_argument('-c', '--config')

    args = parser.parse_args()

    cfg = get_config(args.config)

    listen_addr = cfg.get('LISTEN_ADDR', None)
    listen_port = cfg.get('LISTEN_PORT', None)

    if not listen_addr and not listen_port:
        listen_addr = 'unix://' + os.path.expanduser("~/.taas.sock")
        listen_port = None
    elif listen_port:
        listen_addr = ''
    else:
        listen_port = '5000'

    global_env.consul_host = cfg.get('CONSUL_HOST', None)
    global_env.consul_acl_token = cfg.get('CONSUL_ACL_TOKEN', None)

    docker_client_cert = None
    docker_server_cert = None

    if 'HTTP_BASIC_USERNAME' in cfg and 'HTTP_BASIC_PASSWORD' in cfg:
        app.config['BASIC_AUTH_USERNAME'] = cfg['HTTP_BASIC_USERNAME']
        app.config['BASIC_AUTH_PASSWORD'] = cfg['HTTP_BASIC_PASSWORD']
        app.config['BASIC_AUTH_FORCE'] = True

    if 'DOCKER_CLIENT_CERT' in cfg and 'DOCKER_CLIENT_KEY' in cfg:
        docker_client_cert = (os.path.expanduser(cfg['DOCKER_CLIENT_CERT']),
                              os.path.expanduser(cfg['DOCKER_CLIENT_KEY']))

    if 'DOCKER_SERVER_CERT' in cfg:
        if not docker_client_cert:
            sys.exit("Please specify DOCKER_CLIENT_CERT")
        docker_server_cert = os.path.expanduser(cfg['DOCKER_SERVER_CERT'])

    if 'IPALLOC_RANGE' in cfg:
        global_env.default_network_settings['subnet'] = cfg['IPALLOC_RANGE']

    if 'GATEWAY_IP' in cfg:
        global_env.default_network_settings['gateway_ip'] = cfg['GATEWAY_IP']

    if 'DOCKER_NETWORK' in cfg:
        global_env.default_network_settings['network_name'] = cfg['DOCKER_NETWORK']

    if 'CREATE_NETWORK_AUTOMATICALLY' in cfg:
        global_env.default_network_settings['create_automatically'] = True

    if 'BACKUP_STORAGE_TYPE' in cfg:
        backup_config = {'base_dir': cfg.get('BACKUP_BASE_DIR', None),
                         'host': cfg.get('BACKUP_HOST', None),
                         'user': cfg.get('BACKUP_USER', None),
                         'identity': cfg.get('BACKUP_IDENTITY', None)}
        global_env.backup_storage = backup_storage.create(
            cfg['BACKUP_STORAGE_TYPE'], backup_config)

    ssl_args = {}

    if 'SSL_KEYFILE' in cfg:
        ssl_args['keyfile'] = cfg['SSL_KEYFILE']
        ssl_args['certfile'] = cfg['SSL_CERTFILE']

    docker_tls_config = None
    if docker_client_cert or docker_server_cert:
        docker_tls_config = docker.tls.TLSConfig(
            client_cert=docker_client_cert,
            verify=docker_server_cert
        )
    global_env.docker_tls_config = docker_tls_config

    setup_routes()

    gevent.spawn(sense.Sense.timer_update)
    gevent.spawn(ip_pool.ip_cache_invalidation_loop)

    if listen_addr.startswith('unix:/'):
        listen_on = (listen_addr,)
    else:
        listen_on = (listen_addr, int(listen_port))

    http_server = WSGIServer(listen_on, app, **ssl_args)

    logging.info("Listening on: %s", listen_on)

    http_server.serve_forever()



if __name__ == '__main__':
    main()
