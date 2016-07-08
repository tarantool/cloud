#!/usr/bin/env python3

import uuid
import ipaddress
from gevent.wsgi import WSGIServer
from flask import Flask
from flask_restful import reqparse, abort, Api, Resource

ALLOC_SUBNET=u"172.20.0.0/16"
GROUPS = {}

app = Flask(__name__)
app.config['DEBUG'] = True
api = Api(app)

def abort_if_group_doesnt_exist(group_id):
    if group_id not in GROUPS:
        abort(404, message="group {} doesn't exist".format(group_id))

def abort_if_instance_doesnt_exist(instance_id):
    for _, group in GROUPS.items():
        for instance in group['instances']:
            if instance['id'] == instance_id:
                return

    abort(404, message="instance {} doesn't exist".format(instance_id))


def allocate_ip(skip=[]):
    allocated_ips = set([ALLOC_SUBNET.split('/')[0]])

    for _, group in GROUPS.items():
        for instance in group['instances']:
            allocated_ips.add(instance['addr'])

    net = ipaddress.ip_network(ALLOC_SUBNET)

    except_list = allocated_ips.union(set(skip))
    for addr in net:
        if str(addr) not in except_list:
            return str(addr)


class Group(Resource):
    def get(self, group_id):
        abort_if_group_doesnt_exist(group_id)
        return GROUPS[group_id]

    def delete(self, group_id):
        abort_if_group_doesnt_exist(group_id)
        del GROUPS[group_id]
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

def create_group(name, memsize):
    group_id = uuid.uuid4().hex

    ip1 = allocate_ip()
    ip2 = allocate_ip([ip1])

    group = {'name': name,
             'id': group_id,
             'memsize': memsize,
             'type': 'memcached',
             'state': {'id': '1', 'name': 'OK', 'type': 'passing'},
             'instances': [{'id': group_id+'_1',
                            'name': '1',
                            'addr': ip1,
                            'type': 'memcached',
                            'host': 'localhost'},
                           {'id': group_id+'_2',
                            'name': '2',
                            'addr': ip2,
                            'type': 'memcached',
                            'host': 'localhost'}]
    }

    return group


class GroupList(Resource):
    def get(self):
        return GROUPS

    def post(self):
        parser = reqparse.RequestParser()
        parser.add_argument('name', required=True)
        parser.add_argument('memsize', type=float, default=0.5)

        args = parser.parse_args()
        group = create_group(args['name'], args['memsize'])

        GROUPS[group['id']] = group
        return group, 201


class StateList(Resource):
    def get(self):
        return {'1': {'id': '1', 'name': 'OK', 'type': 'passing'},
                '2': {'id': '2', 'name': 'Degraded', 'type': 'warning'},
                '3': {'id': '3', 'name': 'Down', 'type': 'critical'}}

class Instance(Resource):
    def get(self, instance_id):
        abort_if_instance_doesnt_exist(instance_id)

        for _, group in GROUPS.items():
            for instance in group['instances']:
                if instance['id'] == instance_id:
                    return instance


class InstanceList(Resource):
    def get(self):
        instances = {}
        for _, group in GROUPS.items():
            for instance in group['instances']:
                instances[instance['id']] = instance

        return instances



api.add_resource(GroupList, '/api/groups')
api.add_resource(Group, '/api/groups/<group_id>')

api.add_resource(InstanceList, '/api/instances')
api.add_resource(Instance, '/api/instances/<instance_id>')

api.add_resource(StateList, '/api/states')



group1 = create_group('memcached for Bob', 0.5)
GROUPS[group1['id']] = group1
group2 = create_group('memcached for Alice', 1.2)
GROUPS[group2['id']] = group2


@app.route('/')
def index():
    return 'Hello World\n'

http_server = WSGIServer(('', 5000), app)
http_server.serve_forever()
