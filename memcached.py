#!/usr/bin/env python3

import global_env
import group
import consul
from sense import Sense
import ip_pool
import random
import logging
import docker
import uuid
import time
import tarantool
import allocate

class Memcached(group.Group):
    def __init__(self, consul_host, group_id):
        super(Memcached, self).__init__(consul_host, group_id)

    @classmethod
    def get(cls, group_id):
        memc = Memcached(global_env.consul_host, group_id)

        return memc

    @classmethod
    def create(cls, name, memsize, check_period):
        group_id = uuid.uuid4().hex

        consul_obj = consul.Consul(host=global_env.consul_host,
                                   token=global_env.consul_acl_token)
        kv = consul_obj.kv

        ip1 = ip_pool.allocate_ip()
        ip2 = ip_pool.allocate_ip()

        kv.put('tarantool/%s/blueprint/type' % group_id, 'memcached')
        kv.put('tarantool/%s/blueprint/name' % group_id, name)
        kv.put('tarantool/%s/blueprint/memsize' % group_id, str(memsize))
        kv.put('tarantool/%s/blueprint/check_period' % group_id, str(check_period))
        kv.put('tarantool/%s/blueprint/instances/1/addr' % group_id, ip1)
        kv.put('tarantool/%s/blueprint/instances/2/addr' % group_id, ip2)

        Sense.update()

        memc = Memcached(global_env.consul_host, group_id)

        memc.allocate()
        Sense.update()

        memc.register()
        Sense.update()

        memc.create_containers()
        Sense.update()

        memc.enable_replication()

        return memc

    def delete(self):
        self.unallocate()
        self.unregister()
        self.remove_containers()
        self.remove_blueprint()
        Sense.update()

    def allocate(self):
        consul_obj = consul.Consul(host=global_env.consul_host,
                                   token=global_env.consul_acl_token)
        kv = consul_obj.kv

        blueprint = self.blueprint

        host1 = allocate.allocate(blueprint['memsize'])
        host2 = allocate.allocate(blueprint['memsize'], anti_affinity=[host1])

        kv.put('tarantool/%s/allocation/instances/1/host' %
               self.group_id, host1)
        kv.put('tarantool/%s/allocation/instances/2/host' %
               self.group_id, host2)

    def unallocate(self):
        consul_obj = consul.Consul(host=global_env.consul_host,
                                   token=global_env.consul_acl_token)
        kv = consul_obj.kv

        logging.info("Unallocating '%s'", self.group_id)

        kv.delete("tarantool/%s/allocation" % self.group_id,
                  recurse=True)

    def register(self):
        self.register_instance("1")
        self.register_instance("2")

    def unregister(self):
        self.unregister_instance("1")
        self.unregister_instance("2")

    def create_containers(self):
        self.create_container("1")
        self.create_container("2")

    def remove_containers(self):
        self.remove_container("1")
        self.remove_container("2")

    def remove_blueprint(self):
        consul_obj = consul.Consul(host=global_env.consul_host,
                                   token=global_env.consul_acl_token)
        kv = consul_obj.kv

        logging.info("Removing blueprint '%s'", self.group_id)

        kv.delete("tarantool/%s/blueprint" % self.group_id,
                  recurse=True)

    def enable_replication(self):
        port = 3301

        blueprint = self.blueprint
        allocation = self.allocation

        for instance_num in allocation['instances']:
            other_instances = \
                set(allocation['instances'].keys()) - set([instance_num])

            addr = blueprint['instances'][instance_num]['addr']
            other_addrs = [blueprint['instances'][i]['addr']
                           for i in other_instances]
            docker_host = allocation['instances'][instance_num]['host']
            docker_hosts = Sense.docker_hosts()

            logging.info("Enabling replication between '%s' and '%s'",
                         addr, str(other_addrs))

            docker_addr = None
            for host in docker_hosts:
                if host['addr'].split(':')[0] == docker_host or \
                   host['consul_host'] == docker_host:
                    docker_addr = host['addr']


            docker_obj = docker.Client(base_url=docker_addr,
                                       tls=global_env.docker_tls_config)

            cmd = "tarantool_set_config.lua TARANTOOL_REPLICATION_SOURCE " + \
                  ",".join(other_addrs)

            exec_id = docker_obj.exec_create(self.group_id + '_' + instance_num,
                                             cmd)
            docker_obj.exec_start(exec_id)
            ret = docker_obj.exec_inspect(exec_id)

            if ret['ExitCode'] != 0:
                raise RuntimeError("Failed to enable replication for group " +
                                   self.group_id)


    def register_instance(self, instance_num):
        blueprint = self.blueprint
        allocation = self.allocation

        instance_id = self.group_id + '_' + instance_num
        consul_host = allocation['instances'][instance_num]['host']
        addr = blueprint['instances'][instance_num]['addr']
        check_period = blueprint['check_period']

        consul_obj = consul.Consul(host=consul_host,
                                   token=global_env.consul_acl_token)

        replication_check = {
            'docker_container_id': instance_id,
            'shell': "/bin/sh",
            'script': "/var/lib/mon.d/tarantool_replication.sh",
            'interval': "%ds" % check_period,
            'status' : 'warning'
        }

        memory_check = {
            'docker_container_id': instance_id,
            'shell': "/bin/sh",
            'script': "/var/lib/mon.d/tarantool_memory.sh",
            'interval': "%ds" % check_period,
            'status' : 'warning'
        }

        logging.info("Registering instance '%s' on '%s'",
                     instance_id,
                     consul_host)

        ret = consul_obj.agent.service.register("memcached",
                                                service_id=instance_id,
                                                address=addr,
                                                port=3301,
                                                check=replication_check,
                                                tags=['tarantool'])

        ret = consul_obj.agent.check.register("Memory Utilization",
                                              check=memory_check,
                                              check_id=instance_id + '_memory',
                                              service_id=instance_id)


    def unregister_instance(self, instance_num):
        services = self.services

        if instance_num not in services['instances']:
            return

        instance_id = self.group_id + '_' + instance_num

        consul_hosts = [h['addr'].split(':')[0] for h in Sense.consul_hosts()
                        if h['status'] == 'passing']

        print("Consul hosts: ", consul_hosts)
        if services:
            consul_host = services['instances'][instance_num]['host']

            if consul_host in consul_hosts:
                logging.info("Unregistering instance '%s' from '%s'",
                             instance_id,
                             consul_host)

                consul_obj = consul.Consul(host=consul_host,
                                           token=global_env.consul_acl_token)
                consul_obj.agent.service.deregister(instance_id)
        else:
            logging.info("Not unregistering '%s', as it's not registered",
                         instance_id)


    def create_container(self, instance_num):
        blueprint = self.blueprint
        allocation = self.allocation

        instance_id = self.group_id + '_' + instance_num
        addr = blueprint['instances'][instance_num]['addr']
        memsize = blueprint['memsize']
        network_settings = Sense.network_settings()
        network_name = network_settings['network_name']
        if not network_name:
            raise RuntimeError("Network name is not specified in settings")

        docker_host = allocation['instances'][instance_num]['host']
        docker_hosts = Sense.docker_hosts()

        docker_addr = None
        for host in docker_hosts:
            if host['addr'].split(':')[0] == docker_host or \
               host['consul_host'] == docker_host:
                docker_addr = host['addr']

        if not docker_addr:
            raise RuntimeError("No such Docker host: '%s'" % docker_host)

        replica_ip = None
        if instance_num == '2':
            replica_ip = blueprint['instances']['1']['addr']

        docker_obj = docker.Client(base_url=docker_addr,
                                   tls=global_env.docker_tls_config)

        if not replica_ip:
            logging.info("Creating memcached '%s' on '%s' with ip '%s'",
                         instance_id, docker_obj.base_url, addr)
        else:
            logging.info("Creating memcached '%s' on '%s' with ip '%s'" +
                         " and replication source: '%s'",
                         instance_id, docker_obj.base_url, addr, replica_ip)

        host_config = docker_obj.create_host_config(
            restart_policy =
            {
                "MaximumRetryCount": 0,
                "Name": "unless-stopped"
            })

        cmd = 'tarantool /opt/tarantool/app.lua'

        networking_config = {
            'EndpointsConfig':
            {
                network_name:
                {
                    'IPAMConfig':
                    {
                        "IPv4Address": addr,
                        "IPv6Address": ""
                    },
                    "Links": [],
                    "Aliases": []
                }
            }
        }

        environment = {}

        environment['TARANTOOL_SLAB_ALLOC_ARENA'] = memsize

        if replica_ip:
            environment['TARANTOOL_REPLICATION_SOURCE'] = replica_ip + ':3301'

        container = docker_obj.create_container(image='tarantool-cloud-memcached',
                                                name=instance_id,
                                                command=cmd,
                                                host_config=host_config,
                                                networking_config=networking_config,
                                                environment=environment,
                                                labels=['tarantool'])

        docker_obj.connect_container_to_network(container.get('Id'),
                                                network_name,
                                                ipv4_address=addr)
        docker_obj.start(container=container.get('Id'))


    def remove_container(self, instance_num):
        containers = self.containers

        if instance_num not in containers['instances']:
            return

        instance_id = self.group_id + '_' + instance_num
        docker_hosts = [h['addr'].split(':')[0] for h in Sense.docker_hosts()
                        if h['status'] == 'passing']

        if containers:
            docker_host = containers['instances'][instance_num]['host']
            docker_hosts = Sense.docker_hosts()

            docker_addr = None
            for host in docker_hosts:
                if host['addr'].split(':')[0] == docker_host or \
                   host['consul_host'] == docker_host:
                    docker_addr = host['addr']
            if not docker_addr:
                raise RuntimeError("No such Docker host: '%s'" % docker_host)

            logging.info("Removing container '%s' from '%s'",
                         instance_id,
                         docker_host)

            docker_obj = docker.Client(base_url=docker_addr,
                                       tls=global_env.docker_tls_config)
            docker_obj.stop(container=instance_id)
            docker_obj.remove_container(container=instance_id)
        else:
            logging.info("Not removing container '%s', as it doesn't exist",
                         instance_id)
