#!/usr/bin/env python

import os
import re
import docker
import consul
import uuid
import random
import ipaddress

from contextlib import contextmanager

THIS_FILE_DIR = os.path.dirname(os.path.realpath(__file__))


class Api(object):
    def __init__(self, consul_host):
        self.consul = consul.Consul(host=consul_host)

    def generate_id(self):
        return uuid.uuid4().hex

    def allocate_ip(self, skip=[]):
        docker_nodes = self.get_healthy_docker_nodes()

        alloc_ranges = []
        for node in docker_nodes:
            docker_obj = docker.Client(base_url=node[1])
            try:
                network = docker_obj.inspect_network('macvlan')
            except:
                raise RuntimeError("Network 'macvlan' not found on '%s'" % node[1])

            try:
                iprange = network['IPAM']['Config'][0]['IPRange']
            except:
                raise RuntimeError(
                    "IP ranges not configured for 'macvlan' on '%s'" % node[1])
            alloc_ranges.append(iprange)

        if len(set(alloc_ranges)) != 1:
            raise RuntimeError('Different IP ranges set up on docker hosts: %s' %
                               str(set(alloc_ranges)))


        allocated_ips = set()

        # collect instances from blueprints
        instances = {} # <instance id>: <type>
        for entry in self.consul.kv.get('tarantool', recurse=True)[1] or []:
            match = re.match('tarantool/.*/instances/.*', entry['Key'])
            if match:
                allocated_ips.add(entry['Value'])
        subnet = alloc_ranges[0]
        net = ipaddress.ip_network(subnet)

        except_list = allocated_ips.union(set(skip))
        for addr in net:
            if str(addr) not in except_list:
                return str(addr)

        raise RuntimeError('IP Address range exhausted')

    def get_healthy_docker_nodes(self):
        health =  self.consul.health.service("docker", passing=True)[1]

        result = []
        for entry in health:
            service_addr = entry['Service']['Address'] or entry['Node']['Address']
            port = entry['Service']['Port']

            result.append((entry['Node']['Address'],
                           service_addr+':'+str(port)))

        return result

    def ensure_docker_image(self, docker, image_name):
        images = docker.images()

        for image in images:
            if image['RepoTags'][0] == image_name:
                return

        print "Image '%s' not found on '%s'. Building." % (image_name, docker.base_url)

        result = docker.pull(image_name, stream=True)

        for line in result:
            print line

    def create_memcached_blueprint(self, pair_id, name, ip1, ip2):
        kv = self.consul.kv

        kv.put('tarantool/%s/type' % pair_id, 'memcached')
        kv.put('tarantool/%s/instances/1' % pair_id, ip1)
        kv.put('tarantool/%s/instances/2' % pair_id, ip2)


    def create_memcached(self, docker, instance_id, instance_ip, replica_ip):
        #print "Creating memcached '%s' on '%s' with ip %s" % (instance_id, docker.base_url, instance_ip)

        target_app ='/var/lib/tarantool/app.lua'
        src_app = '/opt/tarantool_cloud/app.lua'

        host_config = docker.create_host_config(
            binds =
            {
                src_app : {
                    'bind' : target_app,
                    'mode' : 'ro'
                }
            })

        cmd = 'tarantool /var/lib/tarantool/app.lua'

        self.ensure_docker_image(docker, 'tarantool/tarantool:latest')

        networking_config = {
            'EndpointsConfig':
            {
                'macvlan':
                {
                    'IPAMConfig':
                    {
                        "IPv4Address": instance_ip,
                        "IPv6Address": ""
                    },
              #      "IPAddress": instance_ip,
                    #"IPPrefixLen": 24,
                    "Links": [],
                    "Aliases": []
                }
            }
        }

        container = docker.create_container(image='tarantool/tarantool:latest',
                                                 name=instance_id,
                                            command=cmd,
                                            host_config=host_config,
                                            networking_config=networking_config)

        docker.connect_container_to_network(container.get('Id'),
                                            'macvlan',
                                            ipv4_address=instance_ip)
        docker.start(container=container.get('Id'))

        return instance_id

    def delete_tarantool_service(self, consul_obj, docker_obj, instance_id):
        #print "Removing container '%s' from '%s'" % (instance_id, docker_obj.base_url)
        docker_obj.stop(container=instance_id)
        docker_obj.remove_container(container=instance_id)

    def register_memcached(self, instance_id, name):
        pass

    def register_tarantool_service(self, consul_obj, docker, instance_id, name):
        info = docker.inspect_container(instance_id)

        networks = info['NetworkSettings']['Networks']
        assert(len(networks)==1)

        ipaddr = networks.values()[0]['IPAddress']


        #check = consul.Check.http("http://%s:8080/ping" % ipaddr, "10s")
        #check = consul.Check.docker(instance_id, "/bin/sh", "/bin/ps", "10s")
        ret = consul_obj.agent.service.register("memcached",
                                                service_id=instance_id,
                                                address=ipaddr,
                                                port=3301)
                                                #check=check)


    def unregister_tarantool_service(self, consul_obj, docker, instance_id):
        consul_obj.agent.service.deregister(instance_id)

    def locate_tarantool_service(self, consul_obj, instance_id):
        health = self.consul.health.service("memcached")[1]

        for service in health:
            if service['Service']['ID'] == instance_id:
                agent_addr = service['Node']['Address']
                local = consul.Consul(host=agent_addr)

                docker_addr = None
                docker_port = None
                for local_service in local.agent.services().values():
                    if local_service['Service'] == 'docker':
                        docker_addr = local_service['Address'] or agent_addr
                        docker_port = local_service['Port']
                assert(docker_addr)
                assert(docker_port)
                docker_host = docker_addr + ':' + str(docker_port)

                return agent_addr, docker_host

        return None, None



    def create_memcached_pair(self, name):
        pair_id = self.generate_id()
        instance1 = None
        instance2 = None

        self.get_healthy_docker_nodes()

        healthy_nodes = self.get_healthy_docker_nodes()
        if len(healthy_nodes) >= 2:
            pick = random.sample(healthy_nodes, 2)
        elif len(healthy_nodes) == 1:
            pick = healthy_nodes * 2
        else:
            raise RuntimeError("There are no healthy docker nodes")
        consul1_host, docker1_host = pick[0]
        consul2_host, docker2_host = pick[1]
        docker1 = docker.Client(base_url=docker1_host)
        docker2 = docker.Client(base_url=docker2_host)
        consul1 = consul.Consul(host=consul1_host)
        consul2 = consul.Consul(host=consul2_host)

        ip1 = self.allocate_ip()
        ip2 = self.allocate_ip(skip=[ip1])

        self.create_memcached_blueprint(pair_id, name, ip1, ip2)

        instance1 = self.create_memcached(docker1, pair_id+'_1', ip1, ip2)
        instance2 = self.create_memcached(docker2, pair_id+'_2', ip2, ip1)

        self.register_tarantool_service(consul1, docker1, instance1, name)
        self.register_tarantool_service(consul2, docker2, instance2, name)

        return pair_id

    def delete_memcached_pair(self, pair_id):
        kv = self.consul.kv

        instance_type =  kv.get("tarantool/%s/type" % pair_id)

        if instance_type[1] == None:
            raise RuntimeError("Pair '%s' doesn't exist" % pair_id)

        instance1 = pair_id + '_1'
        instance2 = pair_id + '_2'

        consul1_host, docker1_host = \
            self.locate_tarantool_service(self.consul, instance1)
        consul2_host, docker2_host = \
            self.locate_tarantool_service(self.consul, instance2)

        if consul1_host and docker1_host:
            consul1 = consul.Consul(host=consul1_host)
            docker1 = docker.Client(base_url=docker1_host)
            self.unregister_tarantool_service(consul1, docker1, instance1)
            self.delete_tarantool_service(consul1, docker1, instance1)

        if consul2_host and docker2_host:
            consul2 = consul.Consul(host=consul2_host)
            docker2 = docker.Client(base_url=docker2_host)
            self.unregister_tarantool_service(consul2, docker2, instance2)
            self.delete_tarantool_service(consul2, docker2, instance2)


        kv.delete("tarantool/%s" % pair_id, recurse=True)

    def list_memcached_pairs(self):
        kv = self.consul.kv

        health = self.consul.health.service('memcached')[1]

        tarantool_kv = kv.get('tarantool', recurse=True)[1] or []

        # collect group list
        groups = {} # <group id>: <type>
        for entry in tarantool_kv:
            match = re.match('tarantool/(.*)/type', entry['Key'])
            if match:
                groups[match.group(1)] = entry['Value']

        # collect instances from blueprints
        instances = {} # <instance id>: <type>
        for entry in tarantool_kv:
            match = re.match('tarantool/(.*)/instances/(.*)', entry['Key'])
            if match:
                group = match.group(1)
                instance = match.group(2)
                instances[group + '_' + instance] = groups[group]


        # collect instance statuses from registered services
        status = {}
        for entry in health:
            passing = True
            for check in entry['Checks']:
                passing = passing and (check['Status'] == 'passing')

            host = entry['Service']['Address'] or entry['Node']['Address']
            port = entry['Service']['Port']
            addr = '%s:%s' % (host, port)
            node = entry['Node']['Address']

            status[entry['Service']['ID']] = {'check': passing,
                                              'addr': addr,
                                              'node': node}

        result = []
        for instance, instance_type in instances.iteritems():
            group, instance_no = instance.split('_')

            if status[instance]['check']:
                state = 'OK'
            else:
                state = 'Fail'

            result.append({'group': group,
                           'instance': instance_no,
                           'type': instance_type,
                           'state': state,
                           'addr': status[instance]['addr'],
                           'node': status[instance]['node']})

        return result
