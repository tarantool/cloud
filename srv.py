#!/usr/bin/env python3

from gevent import monkey
monkey.patch_all()

import os
import sys
import uuid
import ipaddress
import memcached
import sense
import global_env
import logging
from gevent.wsgi import WSGIServer
from flask import Flask
from flask_restful import reqparse, abort, Api, Resource

app = Flask(__name__)
app.config['DEBUG'] = True
api = Api(app)

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

    addr = blueprint['instances'][instance_num]['addr']
    host = allocation['instances'][instance_num]['host']
    type_str = blueprint['type']
    name = instance_num
    instance_id = group_id + '_' + instance_num

    return {'id': instance_id,
            'name': name,
            'addr': addr,
            'type': type_str,
            'host': host}


def group_to_dict(group_id):
    memc = memcached.Memcached.get(group_id)
    blueprint = memc.blueprint
    allocation = memc.allocation
    services = memc.services

    state = 'passing'

    states = [i['status'] for i in services['instances'].values()]
    state = sense.combine_consul_statuses(states)

    instances = []

    for instance_num in services['instances']:
        addr = blueprint['instances'][instance_num]['addr']
        host = allocation['instances'][instance_num]['host']
        type_str = blueprint['type']
        name = instance_num
        instance_id = group_id + '_' + instance_num

        instances.append({'id': instance_id,
                          'name': name,
                          'addr': addr,
                          'type': type_str,
                          'host': host})


    result = {'name': blueprint['name'],
              'id': group_id,
              'memsize': blueprint['memsize'],
              'type': blueprint['type'],
              'state': state_to_dict(state),
              'instances': instances}

    return result


class Group(Resource):
    def get(self, group_id):
        abort_if_group_doesnt_exist(group_id)
        return group_to_dict(group_id)

    def delete(self, group_id):
        abort_if_group_doesnt_exist(group_id)

        memc = memcached.Memcached.get(group_id)
        memc.delete()
        return '', 204

    def put(self, group_id):
        parser = reqparse.RequestParser()
        parser = reqparse.RequestParser()
        parser.add_argument('name')
        parser.add_argument('memsize', type=float, default=0.5)

        args = parser.parse_args()
        group = GROUPS[group_id]

        if args['name']:
            group['name'] = args['name']
        if args['memsize']:
            group['memsize'] = args['memsize']

        GROUPS[group_id] = group
        return group, 201


class GroupList(Resource):
    def get(self):
        blueprints = sense.Sense.blueprints()

        result = {}
        for group_id in blueprints:
            result[group_id] = group_to_dict(group_id)
        return result

    def post(self):
        parser = reqparse.RequestParser()
        parser.add_argument('name', required=True)
        parser.add_argument('memsize', type=float, default=0.5)


        args = parser.parse_args()
        memc = memcached.Memcached.create(args['name'], args['memsize'], 10)

        return group_to_dict(memc.group_id), 201


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



def setup_routes():
    api.add_resource(GroupList, '/api/groups')
    api.add_resource(Group, '/api/groups/<group_id>')

    api.add_resource(InstanceList, '/api/instances')
    api.add_resource(Instance, '/api/instances/<instance_id>')

    api.add_resource(StateList, '/api/states')


def main():
    # Don't spam with HTTP connection logs from 'requests' module
    logging.getLogger("requests").setLevel(logging.WARNING)

    logging.basicConfig(format='%(levelname)s: %(message)s',
                        level=logging.INFO)

    if 'CONSUL_HOST' in os.environ:
        global_env.consul_host = os.environ['CONSUL_HOST']
    else:
        sys.exit("Please specify CONSUL_HOST via env")

    setup_routes()

    sense.Sense.update()

    http_server = WSGIServer(('', 5000), app)
    http_server.serve_forever()


if __name__ == '__main__':
    main()
