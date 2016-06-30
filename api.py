#!/usr/bin/env python3

import os
import sys
import re
import docker
import consul
import uuid
import random
import ipaddress
import tarantool
import time
import logging

from contextlib import contextmanager

THIS_FILE_DIR = os.path.dirname(os.path.realpath(__file__))


def combine_consul_statuses(statuses):
    total = "passing"
    for status in statuses:
        if status == 'critical':
            total = 'critical'
        elif status == 'warning' and total == 'passing':
            total = 'warning'
    return total

def consul_kv_to_dict(consul_kv_list):
    result = {}
    for item in consul_kv_list:
        result[item['Key']] = item['Value'].decode("ascii")
    return result



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
            match = re.match('tarantool/.*/blueprint/instances/.*', entry['Key'])
            if match:
                allocated_ips.add(entry['Value'].decode("ascii"))
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
            statuses = [check['Status'] for check in entry['Checks']]
            status = combine_consul_statuses(statuses)

            service_addr = entry['Service']['Address'] or entry['Node']['Address']
            port = entry['Service']['Port']

            if status == 'passing':
                result.append((entry['Node']['Address'],
                               service_addr+':'+str(port)))



        return result

    def ensure_docker_image(self, docker, image_name):
        images = docker.images()

        for image in images:
            if image['RepoTags'][0] == image_name:
                return

        logging.info("Image '%s' not found on '%s'. Building.",
                     image_name, docker.base_url)

        result = docker.pull(image_name, stream=True)

        for line in result:
            logging.info(line)

    def create_memcached_blueprint(self, pair_id, name, memsize,
                                   ip1, ip2, check_period):
        kv = self.consul.kv

        kv.put('tarantool/%s/blueprint/type' % pair_id, 'memcached')
        kv.put('tarantool/%s/blueprint/name' % pair_id, name)
        kv.put('tarantool/%s/blueprint/memsize' % pair_id, str(memsize))
        kv.put('tarantool/%s/blueprint/check_period' % pair_id, str(check_period))
        kv.put('tarantool/%s/blueprint/instances/1/addr' % pair_id, ip1)
        kv.put('tarantool/%s/blueprint/instances/2/addr' % pair_id, ip2)


    def create_memcached(self, docker_host, instance_id,
                         memsize, instance_ip, replica_ip):
        docker_obj = docker.Client(base_url=docker_host+':2375')

        if not replica_ip:
            logging.info("Creating memcached '%s' on '%s' with ip '%s'",
                         instance_id, docker_obj.base_url, instance_ip)
        else:
            logging.info("Creating memcached '%s' on '%s' with ip '%s'" +
                         " and replication source: '%s'",
                         instance_id, docker_obj.base_url, instance_ip, replica_ip)


        target_app ='/var/lib/tarantool/app.lua'
        src_app = '/opt/tarantool_cloud/app.lua'

        target_mon = '/var/lib/mon.d'
        src_mon = '/opt/tarantool_cloud/mon.d'

        host_config = docker_obj.create_host_config(
            binds =
            {
                src_app : {
                    'bind' : target_app,
                    'mode' : 'ro'
                },
                src_mon : {
                    'bind' : target_mon,
                    'mode' : 'ro'
                }
            })

        cmd = 'tarantool /var/lib/tarantool/app.lua'

        self.ensure_docker_image(docker_obj, 'tarantool/tarantool:latest')

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

        environment = {}

        environment['ARENA'] = memsize

        if replica_ip:
            environment['REPLICA'] = replica_ip + ':3302'

        container = docker_obj.create_container(image='tarantool/tarantool:latest',
                                                name=instance_id,
                                                command=cmd,
                                                host_config=host_config,
                                                networking_config=networking_config,
                                                environment=environment,
                                                labels=['memcached'])

        docker_obj.connect_container_to_network(container.get('Id'),
                                                'macvlan',
                                                ipv4_address=instance_ip)
        docker_obj.start(container=container.get('Id'))

        return instance_id

    def delete_container(self, instance_id, docker_host=None):

        if not docker_host:
            _, docker_host = \
                self.locate_tarantool_service(instance_id)

        healthy_docker_nodes = [n[1] for n in self.get_healthy_docker_nodes()]

        if docker_host not in healthy_docker_nodes:
            logging.info(
                "Not deleting instance '%s' from '%s' because the latter is down",
                instance_id,
                docker_host)
            return

        logging.info("Deleting instance '%s' from '%s'",
                     instance_id,
                     docker_host)

        docker_obj = docker.Client(base_url=docker_host)

        docker_obj.stop(container=instance_id)
        docker_obj.remove_container(container=instance_id)

    def stop_container(self, instance_id, docker_host=None):

        if not docker_host:
            _, docker_host = \
                self.locate_tarantool_service(instance_id)

        healthy_docker_nodes = [n[1] for n in self.get_healthy_docker_nodes()]

        if docker_host not in healthy_docker_nodes:
            logging.info(
                "Not stopping instance '%s' on '%s' because the latter is down",
                instance_id,
                docker_host)
            return

        logging.info("Stopping instance '%s' on '%s'",
                     instance_id,
                     docker_host)

        docker_obj = docker.Client(base_url=docker_host)

        docker_obj.stop(container=instance_id)

    def start_container(self, instance_id, docker_host=None):

        if not docker_host:
            _, docker_host = \
                self.locate_tarantool_service(instance_id)

        healthy_docker_nodes = [n[1] for n in self.get_healthy_docker_nodes()]

        if docker_host not in healthy_docker_nodes:
            logging.info(
                "Not starting instance '%s' on '%s' because the latter is down",
                instance_id,
                docker_host)
            return

        logging.info("Starting instance '%s' on '%s'",
                     instance_id,
                     docker_host)

        docker_obj = docker.Client(base_url=docker_host)

        docker_obj.start(container=instance_id)



    def register_tarantool_service(self, consul_host, ipaddr, instance_id, name, check_period):
        consul_obj = consul.Consul(host=consul_host)
        #check = consul.Check.http("http://%s:8080/ping" % ipaddr, "10s")
        check = {
            'docker_container_id': instance_id,
            'shell': "/bin/bash",
            'script': "/var/lib/mon.d/tarantool_replication.sh",
            'interval': "%ds" % check_period,
            'status' : 'warning'
        }

        ret = consul_obj.agent.service.register("memcached",
                                                service_id=instance_id,
                                                address=ipaddr,
                                                port=3301,
                                                check=check)

    def unallocate_tarantool_service(self, instance_id):
        kv = self.consul.kv

        group, instance = instance_id.split('_')

        kv.delete("tarantool/%s/allocation/instances/%s" % (group, instance),
                  recurse=True)



    def unregister_tarantool_service(self, instance_id, consul_host=None):
        nodes = self.consul.catalog.nodes()

        if not consul_host:
            consul_host, _ = \
                self.locate_tarantool_service(instance_id)

        healthy_consul_nodes = self.get_healthy_consul_nodes()

        logging.info("Unregistering instance '%s' from '%s'",
                     instance_id,
                     consul_host)

        if not consul_host:
            logging.info("Not unregistering '%s', as it's not registered",
                         instance_id)
            return

        if consul_host in healthy_consul_nodes:
            consul_obj = consul.Consul(host=consul_host)
            consul_obj.agent.service.deregister(instance_id)
        else:
            nodename = None
            consul_health = self.consul.health.service("consul")[1]

            for entry in consul_health:
                if entry['Service']['Address'] == consul_host or\
                   entry['Node']['Address'] == consul_host:
                    nodename = entry['Node']['Node']
            assert(nodename)

            self.consul.catalog.deregister(nodename, instance_id)

    def get_healthy_consul_nodes(self):
        consul_health = self.consul.health.service("consul")[1]
        healthy_consul_nodes = []
        for service in consul_health:
            statuses = [check['Status'] for check in service['Checks']]
            status = combine_consul_statuses(statuses)
            if status == 'passing':
                service_addr = service['Service']['Address'] or \
                               service['Node']['Address']
                healthy_consul_nodes += [service_addr]
        return healthy_consul_nodes


    def locate_tarantool_service(self, instance_id):
        memcached_health = self.consul.health.service("memcached")[1]
        docker_health = self.consul.health.service("docker")[1]

        agent_addr = None

        for service in memcached_health:
            if service['Service']['ID'] == instance_id:
                agent_addr = service['Node']['Address']
                local = consul.Consul(host=agent_addr)

        if not agent_addr:
            return None, None

        for service in docker_health:
            if service['Node']['Address'] == agent_addr:
                docker_addr = service['Service']['Address'] or service['Node']['Address']
                docker_port = service['Service']['Port']

        assert(agent_addr)
        assert(docker_addr)
        assert(docker_port)
        docker_host = docker_addr + ':' + str(docker_port)

        return agent_addr, docker_host


    def get_blueprints(self):
        """
        returns a list of registered groups:
        {
            'type': 'memcached',
            'name': '<group name>',
            'memsize': <amount of memory>,
            'instances': {
                '1': {'addr': '<ip addr>'},
                '2': {'addr': '<ip addr>'}
            }
        }
        """
        kv = self.consul.kv
        tarantool_kv = consul_kv_to_dict(kv.get('tarantool', recurse=True)[1] or [])

        groups = {}
        for key, value in tarantool_kv.items():
            match = re.match('tarantool/(.*)/blueprint/type', key)
            if match:
                groups[match.group(1)] = {'type': value,
                                          'instances': {}}

        for key, value in tarantool_kv.items():
            match = re.match('tarantool/(.*)/blueprint/memsize', key)
            if match:
                groups[match.group(1)]['memsize'] = float(value)

        for key, value in tarantool_kv.items():
            match = re.match('tarantool/(.*)/blueprint/instances/(.*)/addr', key)
            if match:
                groups[match.group(1)]['instances'][match.group(2)] = \
                    {'addr': None}

        for key, value in tarantool_kv.items():
            match = re.match('tarantool/(.*)/blueprint/name', key)
            if match:
                groups[match.group(1)]['name'] = value

            match = re.match('tarantool/(.*)/blueprint/check_period', key)
            if match:
                groups[match.group(1)]['check_period'] = int(value)

            match = re.match('tarantool/(.*)/blueprint/instances/(.*)/addr', key)
            if match:
                group = match.group(1)
                instance_id = match.group(2)

                groups[group]['instances'][instance_id]['addr'] = \
                    value

        return groups


    def get_allocations(self):
        kv = self.consul.kv
        tarantool_kv = consul_kv_to_dict(kv.get('tarantool', recurse=True)[1] or [])

        groups = {}
        for key, value in tarantool_kv.items():
            match = re.match('tarantool/(.*)/allocation/instances/(.*)/host',
                             key)
            if match:
                group = match.group(1)
                instance_id = match.group(2)
                if group not in groups:
                    groups[group] = {'instances': {}}
                if instance_id not in groups[group]['instances']:
                    groups[group]['instances'][instance_id] = {}

                groups[group]['instances'][instance_id]['host'] = \
                    value

        return groups


    def get_registered_services(self):
        """
        returns a list of allocated groups:
        {
            'type': 'memcached',
            'name': '<group name>',
            'instances': {
                '1': {'addr': '<ip addr>', 'host': '<host addr>'},
                '2': {'addr': '<ip addr>', 'host': '<host addr>'}
            }
        }
        """
        groups = {}

        health = self.consul.health.service('memcached')[1]
        for entry in health:
            group, instance_id = entry['Service']['ID'].split('_')
            host = entry['Service']['Address'] or entry['Node']['Address']
            port = entry['Service']['Port']
            addr = '%s:%s' % (host, port)
            node = entry['Node']['Address']

            statuses = [check['Status'] for check in entry['Checks']]
            status = combine_consul_statuses(statuses)

            if group not in groups:
                groups[group] = {}
                groups[group]['type'] = 'memcached'
                groups[group]['name'] = ''
                groups[group]['instances'] = {}

            if instance_id not in groups[group]['instances']:
                groups[group]['instances'][instance_id] = {
                    'addr': addr,
                    'entries': []}

            groups[group]['instances'][instance_id]['entries'].append({
                'host': node,
                'status': status})

        return groups


    def get_emergent_state(self):
        """
        returns a list of actual groups:
        {
            'type': 'memcached',
            'name': '<group name>',
            'instances': {
                '1': {'addr': '<ip addr>', 'host': '<host addr>'},
                '2': {'addr': '<ip addr>', 'host': '<host addr>'}
            }
        }
        """

        docker_nodes = self.get_healthy_docker_nodes()

        groups = {}

        for node in docker_nodes:
            docker_obj = docker.Client(base_url=node[1])

            for container in docker_obj.containers(all=True,
                                                   filters={'label': 'memcached'}):

                instance_name = container['Names'][0].lstrip('/')
                group, instance_id = instance_name.split('_')
                macvlan = container['NetworkSettings']['Networks']['macvlan']
                addr = macvlan['IPAMConfig']['IPv4Address']
                host = node[0]
                is_running = container['State'] == 'running'


                if group not in groups:
                    groups[group] = {}
                    groups[group]['type'] = 'memcached'
                    groups[group]['name'] = ''
                    groups[group]['instances'] = {}

                groups[group]['instances'][instance_id] = {
                    'addr': addr + ':3301',
                    'host': host,
                    'is_running': is_running
                }

        return groups

    def cleanup_stale_registrations(self, emergent_states):
        health = self.consul.health.service('memcached')[1]

        groups = {}

        result = False

        for entry in health:
            group, instance_id = entry['Service']['ID'].split('_')

            node = entry['Node']['Address']
            statuses = [check['Status'] for check in entry['Checks']]
            status = combine_consul_statuses(statuses)

            if group not in groups:
                groups[group] = set()

            groups[group].add((instance_id, node, status))

        for group in groups:
            instance_ids = set([a[0] for a in groups[group]])

            for instance_id in instance_ids:
                if group not in emergent_states or \
                   instance_id not in emergent_states[group]['instances']:
                    continue

                instance = emergent_states[group]['instances'][instance_id]
                allocations = [a for a in groups[group] if a[0] == instance_id]

                if len(allocations) > 1:
                    for alloc in allocations:
                        if alloc[1] != instance['host']:
                            logging.info("Will unregister '%s' from '%s'",
                                         group+'_'+instance_id,
                                         alloc[1])
                            result = True
                            self.unregister_tarantool_service(
                                group+'_'+instance_id,
                                alloc[1])

        return result

    def unallocate_instances_from_failing_nodes(self, group, blueprints,
                                                allocations, registrations,
                                                emergent_states):
        healthy_docker_nodes = [n[1] for n in self.get_healthy_docker_nodes()]


        try:
            allocation_instances = allocations[group]['instances'].keys()
        except:
            allocation_instances = []

        try:
            emergent_instances = emergent_states[group]['instances'].keys()
        except:
            emergent_instances = []

        for instance_id in allocation_instances:
            instance = allocations[group]['instances'][instance_id]
            if instance_id not in emergent_instances and \
               instance['host']+':2375' not in healthy_docker_nodes:
                logging.info("Unregistering '%s' because its node failed" %
                             (group+'_'+instance_id))
                self.unallocate_tarantool_service(group+'_'+instance_id)
                self.unregister_tarantool_service(group+'_'+instance_id)
                return True

        return False


    def cleanup_lost_containers(self, group, blueprints,
                                allocations, registrations,
                                emergent_states):
        # clean up "lost" containers
        if group in emergent_states and \
           group not in blueprints:
            logging.info("Removing '%s' because there is no blueprint" %
                         group)

            state = emergent_states[group]
            for instance_id in state['instances']:

                instance = state['instances'][instance_id]
                host = instance['host']

                self.delete_container(group+'_'+instance_id,
                                      host+':2375')

            # also clean up service registrations
            if group in allocations:
                alloc = allocations[group]
                for instance_id in alloc['instances']:
                    self.unallocate_tarantool_service(group+'_'+instance_id)

            if group in registrations:
                registration = registrations[group]
                for instance_id in registration['instances']:
                    self.unregister_tarantool_service(group+'_'+instance_id)

            return True

        return False

    def allocate_non_existing_groups(self, group, blueprints,
                                     allocations, registrations,
                                     emergent_states):
        # allocate groups that don't exist
        if group in blueprints and \
           group not in allocations:
            logging.info("Allocating '%s' because it's not allocated" %
                         group)

            # if there were any existing states, they must be destroyed
            if group in emergent_states:
                state = emergent_states[group]
                for instance_id in state['instances']:
                    instance = state['instances'][instance_id]
                    host = instance['host']

                    self.delete_container(group+'_'+instance_id,
                                          host+':2375')

            # if there were any existing registrations, they must be destroyed
            if group in registrations:
                state = registrations[group]
                for instance_id in state['instances']:
                    instance = state['instances'][instance_id]

                    assert(len(instance['entries']) == 1)
                    for entry in instance['entries']:
                        host = entry['host']
                        self.unregister_tarantool_service(group+'_'+instance_id,
                                                          host)

            alloc = self.allocate_group(group, blueprints[group])
            self.run_group(group, blueprints[group], alloc)
            self.register_group(group, blueprints[group], alloc)

            return True
        return False

    def rerun_stopped_groups(self, group, blueprints,
                             allocations, registrations,
                             emergent_states):
        # start group that is not running
        if group in blueprints and \
           group in allocations and \
           group not in emergent_states:
            logging.info("Rerunning '%s' because it's stopped" %
                         group)

            cleanup_allocations = False

            for instance_id in blueprints[group]['instances']:
                if instance_id in allocations[group]['instances']:
                    cleanup_allocations = True

            if group in registrations:
                for instance_id in registrations[group]['instances']:
                    self.unregister_tarantool_service(group+'_'+instance_id)

            if cleanup_allocations:
                for instance_id in blueprints[group]['instances']:
                    self.unallocate_tarantool_service(group+'_'+instance_id)
                alloc = self.allocate_group(group, blueprints[group])
            else:
                alloc = allocations[group]

            self.run_group(group, blueprints[group], alloc)
            self.register_group(group, blueprints[group], alloc)
            return True
        return False


    def recreate_missing_allocation(self, group, blueprints,
                                    allocations, registrations,
                                    emergent_states):

        try:
            blueprint_instances = blueprints[group]['instances'].keys()
        except:
            blueprint_instances = []

        try:
            allocation_instances = allocations[group]['instances'].keys()
        except:
            allocation_instances = []

        try:
            emergent_instances = emergent_states[group]['instances'].keys()
        except:
            emergent_instances = []

        for instance_id in blueprint_instances:
            # if there is a running container and no allocation, kill the
            # container, reallocate and recreate it
            if instance_id not in allocation_instances:
                logging.info("Reallocating '%s' because it's not allocated" %
                         (group+'_'+instance_id))

                if instance_id in emergent_instances:
                    instance = emergent_states[group]['instances'][instance_id]
                    host = instance['host']

                    self.delete_container(group+'_'+instance_id,
                                          host+':2375')

                if instance_id in registrations:
                    instance = emergent_states[group]['instances'][instance_id]
                    host = instance['host']

                    self.unregister_tarantool_service(group+'_'+instance_id, host)

                alloc = self.allocate_instance(group,
                                               blueprints[group],
                                               allocations[group],
                                               instance_id)

                # if we got here, it means other instance is allocated
                combined_allocation = allocations[group].copy()
                combined_allocation['instances'][instance_id] = alloc
                self.run_instance(group,
                                  blueprints[group],
                                  combined_allocation,
                                  instance_id)
                self.register_instance(group,
                                       blueprints[group],
                                       combined_allocation,
                                       instance_id)
                return True

        return False

    def rerun_missing_instance(self, group, blueprints,
                               allocations, registrations,
                               emergent_states):
        try:
            blueprint_instances = blueprints[group]['instances'].keys()
        except:
            blueprint_instances = []

        try:
            allocation_instances = allocations[group]['instances'].keys()
        except:
            allocation_instances = []

        try:
            emergent_instances = emergent_states[group]['instances'].keys()
        except:
            emergent_instances = []


        for instance_id in blueprint_instances:
            # if there is a running container and no allocation, kill the
            # container, reallocate and recreate it
            if instance_id in allocation_instances and \
               instance_id not in emergent_instances:
                logging.info("Creating '%s' because it is missing" %
                             (group+'_'+instance_id))

                self.run_instance(group,
                                  blueprints[group],
                                  allocations[group],
                                  instance_id)

                return True

        return False


    def register_unregistered_instance(self, group, blueprints,
                                       allocations, registrations,
                                       emergent_states):
        try:
            blueprint_instances = blueprints[group]['instances'].keys()
        except:
            blueprint_instances = []

        try:
            allocation_instances = allocations[group]['instances'].keys()
        except:
            allocation_instances = []

        try:
            registered_instances = registrations[group]['instances'].keys()
        except:
            registered_instances = []

        for instance_id in blueprint_instances:
            # if there is a running container and no allocation, kill the
            # container, reallocate and recreate it
            if instance_id in allocation_instances and \
               instance_id not in registered_instances:
                logging.info("Registering '%s' because it is not registered" %
                             (group+'_'+instance_id))



                self.register_instance(group,
                                       blueprints[group],
                                       allocations[group],
                                       instance_id)

                return True

        return False


    def migrate_instance_to_correct_host(self, group, blueprints,
                                         allocations, registrations,
                                         emergent_states):
        try:
            allocation_instances = allocations[group]['instances'].keys()
        except:
            allocation_instances = []

        try:
            emergent_instances = emergent_states[group]['instances'].keys()
        except:
            emergent_instances = []

        for instance_id in allocation_instances:
            if instance_id in emergent_instances:
                # if instance is located on different host than expected,
                # it should be removed and recreated
                allocation = allocations[group]['instances'][instance_id]
                emergent = emergent_states[group]['instances'][instance_id]

                if allocation['host'] != emergent['host']:
                    logging.info("Migrating '%s' to '%s'" %
                                 (group+'_'+instance_id, allocation['host']))

                    self.delete_container(group+'_'+instance_id,
                                          emergent['host']+':2375')

                    self.run_instance(group,
                                      blueprints[group],
                                      allocations[group],
                                      instance_id)

                    return True
        return False

    def register_instance_on_correct_host(self, group, blueprints,
                                         allocations, registrations,
                                         emergent_states):
        try:
            allocation_instances = allocations[group]['instances'].keys()
        except:
            allocation_instances = []

        try:
            registration_instances = registrations[group]['instances'].keys()
        except:
            registration_instances = []

        for instance_id in allocation_instances:
            if instance_id in registration_instances:
                # if instance is located on different host than expected,
                # it should be removed and recreated
                allocation = allocations[group]['instances'][instance_id]
                registration = registrations[group]['instances'][instance_id]

                assert(len(registration['entries']) == 1)
                for entry in registration['entries']:
                    if allocation['host'] != entry['host']:
                        logging.info("Registering '%s' on '%s'" %
                                     (group+'_'+instance_id, allocation['host']))

                        self.unregister_tarantool_service(group+'_'+instance_id,
                                                          entry['host'])
                        self.register_instance(group,
                                               blueprints[group],
                                               allocations[group],
                                               instance_id)

                        return True
        return False


    def recreate_and_reallocate_failed_instance(self, group, blueprints,
                                                allocations, registrations,
                                                emergent_states):
        try:
            emergent_instances = emergent_states[group]['instances'].keys()
        except:
            emergent_instances = []
        try:
            registration_instances = registrations[group]['instances'].keys()
        except:
            registration_instances = []

        for instance_id in registration_instances:

            registration = registrations[group]['instances'][instance_id]
            assert(len(registration['entries']) == 1)
            for entry in registration['entries']:
                # failed instances must be destroyed and re-allocated
                if entry['status'] not in ('passing', 'warning'):
                    logging.info("Recreating '%s' because it has failed" %
                                 (group+'_'+instance_id))

                    if instance_id in emergent_instances:
                        emergent = emergent_states[group]['instances'][instance_id]
                        self.delete_container(group+'_'+instance_id,
                                              emergent['host']+':2375')

                    self.unallocate_tarantool_service(group+'_'+instance_id)
                    self.unregister_tarantool_service(group+'_'+instance_id)

                    alloc = self.allocate_instance(group,
                                                   blueprints[group],
                                                   allocations[group],
                                                   instance_id)

                    # if we got here, it means other instance is allocated
                    combined_allocation = allocations[group].copy()
                    combined_allocation['instances'][instance_id] = alloc
                    self.run_instance(group,
                                      blueprints[group],
                                      combined_allocation,
                                      instance_id)

                    return True
        return False


    def heal_groups(self, blueprints, allocations, emergent_states):
        healing_functions = [
            self.cleanup_lost_containers,
            self.allocate_non_existing_groups,
            self.rerun_stopped_groups,
            self.recreate_missing_allocation,
            self.unallocate_instances_from_failing_nodes,
            self.rerun_missing_instance,
            self.register_unregistered_instance,
            self.migrate_instance_to_correct_host,
            self.register_instance_on_correct_host,
            self.recreate_and_reallocate_failed_instance
        ]


        repeat = True
        while repeat:
            repeat = False

            blueprints = self.get_blueprints()
            allocations = self.get_allocations()
            registrations = self.get_registered_services()
            emergent_states = self.get_emergent_state()

            groups = set()
            groups.update(blueprints.keys())
            groups.update(allocations.keys())
            groups.update(registrations.keys())
            groups.update(emergent_states.keys())


            result = self.cleanup_stale_registrations(emergent_states)
            if result:
                repeat=True
                break

            for group in groups:
                for function in healing_functions:
                    result = function(group, blueprints,
                                      allocations, registrations,
                                      emergent_states)
                    if result:
                        repeat=True
                        break

            if repeat:
                logging.info("Will retry healing, as there were changes to system")


    def allocate_group(self, group, blueprint):
        kv = self.consul.kv
        healthy_nodes = self.get_healthy_docker_nodes()
        if len(healthy_nodes) >= 2:
            pick = random.sample(healthy_nodes, 2)
        elif len(healthy_nodes) == 1:
            pick = healthy_nodes * 2
        else:
            raise RuntimeError("There are no healthy docker nodes")

        name = blueprint['name']
        instance_type = blueprint['type']

        result = {'name': name,
                  'type': instance_type,
                  'instances': {},
                  'check_period': blueprint['check_period']}

        for i, instance_id in enumerate(blueprint['instances']):
            consul_host = pick[i][0]
            instance = blueprint['instances'][instance_id]
            addr = instance['addr']

            result['instances'][instance_id] = {
                'host': consul_host,
                'addr': addr,
            }
            kv.put('tarantool/%s/allocation/instances/%s/host' % (group, instance_id),
                   consul_host)

        return result

    def register_group(self, group, blueprint, allocation):
        for instance_id in allocation['instances']:
            consul_host = allocation['instances'][instance_id]['host']
            addr = blueprint['instances'][instance_id]['addr']
            name = blueprint['name']
            self.register_tarantool_service(consul_host, addr,
                                            group+'_'+instance_id, name,
                                            allocation['check_period'])


    def allocate_instance(self, group, blueprint, allocation, instance_id):
        kv = self.consul.kv

        other_instance_id = [i for i in allocation['instances']
                             if i != instance_id][0]
        other_instance = allocation['instances'][other_instance_id]

        healthy_nodes = self.get_healthy_docker_nodes()
        nodes_to_pick = [n for n in healthy_nodes if n[0] != other_instance['host']]

        pick = random.choice(nodes_to_pick)

        consul_host = pick[0]
        instance = blueprint['instances'][instance_id]
        addr = instance['addr']
        name = blueprint['name']

        kv.put('tarantool/%s/allocation/instances/%s/host' % (group, instance_id),
                   consul_host)

        return {
            'host': consul_host,
            'addr': addr,
            'name': name,
            'check_period': blueprint['check_period']
        }


    def register_instance(self, group, blueprint, allocation, instance_id):
        consul_host = allocation['instances'][instance_id]['host']
        addr = blueprint['instances'][instance_id]['addr']
        name = blueprint['name']

        self.register_tarantool_service(consul_host, addr,
                                        group+'_'+instance_id, name,
                                        blueprint['check_period'])


    def run_group(self, group, blueprint, allocation):
        name = blueprint['name']

        instance_ids = list(allocation['instances'].keys())

        instances = allocation['instances']
        for i, instance_id in enumerate(instances):
            other_instance_id = instance_ids[1-i]

            bp = blueprint['instances'][instance_id]
            other_bp = blueprint['instances'][other_instance_id]
            alloc = allocation['instances'][instance_id]

            host = alloc['host']

            if i == 0:
                self.create_memcached(host,
                                      group+'_'+instance_id,
                                      blueprint['memsize'],
                                      bp['addr'].split(':')[0],
                                      None)

            else:
                self.create_memcached(host,
                                      group+'_'+instance_id,
                                      blueprint['memsize'],
                                      bp['addr'].split(':')[0],
                                      other_bp['addr'].split(':')[0])
        self.enable_memcached_replication(
            instances[instance_ids[0]]['addr'],
            instances[instance_ids[1]]['addr'])


    def run_instance(self, group, blueprint, allocation, instance_id):
        other_instance_id = [i for i in allocation['instances']
                             if i != instance_id][0]

        bp = blueprint['instances'][instance_id]
        other_bp = blueprint['instances'][other_instance_id]
        alloc = allocation['instances'][instance_id]
        host = alloc['host']

        self.create_memcached(host,
                              group+'_'+instance_id,
                              blueprint['memsize'],
                              bp['addr'].split(':')[0],
                              other_bp['addr'].split(':')[0])



    def create_memcached_pair(self, name, memsize, check_period):
        pair_id = self.generate_id()

        ip1 = self.allocate_ip()
        ip2 = self.allocate_ip(skip=[ip1])

        self.create_memcached_blueprint(pair_id, name, memsize,
                                        ip1, ip2, check_period)

        blueprints = self.get_blueprints()
        allocations = self.get_allocations()
        emergent_states = self.get_emergent_state()
        self.heal_groups(blueprints, allocations, emergent_states)

        #self.enable_memcached_replication(ip1+':3301', ip2+':3301')

        return pair_id

    def delete_memcached_pair(self, pair_id):
        kv = self.consul.kv

        instance_type = kv.get("tarantool/%s/blueprint/type" % pair_id)

        if instance_type[1] == None:
            raise RuntimeError("Pair '%s' doesn't exist" % pair_id)

        instance1 = pair_id + '_1'
        instance2 = pair_id + '_2'

        consul1_host, docker1_host = \
            self.locate_tarantool_service(instance1)
        consul2_host, docker2_host = \
            self.locate_tarantool_service(instance2)

        if consul1_host and docker1_host:
            consul1 = consul.Consul(host=consul1_host)
            docker1 = docker.Client(base_url=docker1_host)
            try:
                self.delete_container(instance1)
            except docker.errors.NotFound:
                pass
            self.unregister_tarantool_service(instance1)

        if consul2_host and docker2_host:
            consul2 = consul.Consul(host=consul2_host)
            docker2 = docker.Client(base_url=docker2_host)
            try:
                self.delete_container(instance2)
            except docker.errors.NotFound:
                pass
            self.unregister_tarantool_service(instance2)

        kv.delete("tarantool/%s" % pair_id, recurse=True)

    def list_memcached_pairs(self):
        kv = self.consul.kv

        health = self.consul.health.service('memcached')[1]

        tarantool_kv = kv.get('tarantool', recurse=True)[1] or []


        blueprints = self.get_blueprints()
        allocations = self.get_allocations()
        registrations = self.get_registered_services()
        emergent_states = self.get_emergent_state()

        groups = set()
        groups.update(blueprints.keys())


        result = []

        for group in sorted(groups):
            blueprint = blueprints[group]
            for instance_id in blueprint['instances']:
                if group in allocations:
                    node = allocations[group]['instances'][instance_id]['host']
                else:
                    node = 'N/A'

                if group in registrations and \
                   instance_id in registrations[group]['instances']:
                    registration = registrations[group]

                    if group in emergent_states and \
                       instance_id in emergent_states[group]['instances'] and\
                       not emergent_states[group]['instances'][instance_id] \
                           ['is_running']:
                        status = 'stopped'
                    else:
                        status = combine_consul_statuses(
                            [e['status'] for e in
                             registration['instances'][instance_id]['entries']])
                else:
                    if group in emergent_states and \
                       instance_id in emergent_states[group]['instances']:

                       if emergent_states[group]['instances'][instance_id] \
                          ['is_running']:
                           status = 'unregistered'
                       else:
                           status = 'stopped'
                    else:
                        status = 'missing'


                result.append({'group': group,
                               'instance': instance_id,
                               'type': blueprint['type'],
                               'name': blueprint['name'],
                               'size': str(blueprint['memsize']),
                               'state': status,
                               'addr': blueprint['instances'][instance_id]['addr'],
                               'node': node})

        return result

    def enable_memcached_replication(self, memcached1, memcached2):
        memc1_host = memcached1.split(':')[0]
        memc1_port = 3302
        memc2_host = memcached2.split(':')[0]
        memc2_port = 3302

        logging.info("Enabling replication between '%s' and '%s'",
                     memc1_host, memc2_host)

        timeout = time.time() + 10
        while time.time() < timeout:
            try:
                memc1 = tarantool.Connection(memc1_host, 3302)
                memc2 = tarantool.Connection(memc2_host, 3302)
                break
            except:
                pass
            time.sleep(0.5)

        if time.time() > timeout:
            raise RuntimeError("Failed to enable replication between '%s' and '%s'" %
                               (memc1_host, memc2_host))

        cmd = "box.cfg{replication_source=\"%s:%d\"}"

        memc1_repl_status = memc1.eval("return box.info.replication['status']")
        memc2_repl_status = memc2.eval("return box.info.replication['status']")

        if 'follow' not in memc1_repl_status:
            memc1.eval(cmd % (memc2_host, memc2_port))

        if 'follow' not in memc2_repl_status:
            memc2.eval(cmd % (memc1_host, memc1_port))

        timeout = time.time() + 10
        while time.time() < timeout:
            memc1_repl_status = memc1.eval("return box.info.replication['status']")
            memc2_repl_status = memc2.eval("return box.info.replication['status']")

            if 'follow' in memc1_repl_status and 'follow' in memc2_repl_status:
                break
            time.sleep(0.5)

        if 'follow' not in memc1_repl_status:
            raise RuntimeError("Failed to enable replication on '%s'" % memcached1)

        if 'follow' not in memc2_repl_status:
            raise RuntimeError("Failed to enable replication on '%s'" % memcached2)

    def heal(self):
        blueprints = self.get_blueprints()
        allocations = self.get_allocations()
        emergent_states = self.get_emergent_state()
        self.heal_groups(blueprints, allocations, emergent_states)

    def wait_instance(self, instance_id, passing, warning, critical):
        expected_statuses = []
        if passing:
            expected_statuses += ["passing"]

        if warning:
            expected_statuses += ["warning"]

        if critical:
            expected_statuses += ["critical"]


        while True:
            health = self.consul.health.service("memcached")[1]

            for entry in health:
                if entry['Service']['ID'] == instance_id:
                    statuses = [check['Status'] for check in entry['Checks']]
                    status = combine_consul_statuses(statuses)

                    if status in expected_statuses:
                        return
            time.sleep(0.5)

    def wait_group(self, group_id, passing, warning, critical):
        blueprints = self.get_blueprints()

        blueprint = blueprints[group_id]

        for instance in blueprint['instances']:
            self.wait_instance(group_id+'_'+instance, passing, warning, critical)

    def heal_loop(self, watch_period):
        logging.info("Watching for changes in health")
        index_old = None

        while True:
            index_new, health = self.consul.health.service(
                'memcached', index_old, wait='%ds'%watch_period)

            if index_old == index_new:
                # There is a 5-minute timeout for this to happen
                # It is quite safe to run healing during such periods
                logging.info("Running periodic healing")
                self.heal()
            else:
                heal = False
                for entry in health:
                    statuses = [check['Status'] for check in entry['Checks']]
                    status = combine_consul_statuses(statuses)

                    if status == 'critical':
                        heal = True

                if heal:
                    logging.info("One of the services failed. Running healing.")
                    self.heal()

            index_old=index_new

    def watch(self, watch_period):
        logging.info("Watching for changes in health")
        index_old = None

        blueprints_old = self.get_blueprints()
        allocations_old = self.get_allocations()
        registrations_old = self.get_registered_services()
        emergent_states_old = self.get_emergent_state()

        while True:
            index_new, health = self.consul.health.service(
                'memcached', index_old, wait='%ds'%watch_period)

            blueprints = self.get_blueprints()
            allocations = self.get_allocations()
            registrations = self.get_registered_services()
            emergent_states = self.get_emergent_state()

            for group in blueprints:
                if group not in blueprints_old:
                    print("Created group '%s'" % group)
            for group in allocations:
                if group not in allocations_old:
                    print("Allocated group '%s'" % group)
            for group in registrations:
                if group not in registrations_old:
                    print("Registered group '%s'" % group)
            for group in emergent_states:
                if group not in emergent_states_old:
                    print("Started containers for group '%s'" % group)

            for group in blueprints_old:
                if group not in blueprints:
                    print("Deleted group '%s'" % group)
            for group in allocations_old:
                if group not in allocations:
                    print("Unallocated group '%s'" % group)
            for group in registrations_old:
                if group not in registrations:
                    print("Unregistered group '%s'" % group)
            for group in emergent_states_old:
                if group not in emergent_states:
                    print("Stopped containers for group '%s'" % group)



            for group in registrations:
                if group in registrations_old:
                    instances = set(list(registrations[group]['instances'].keys()) +
                                    list(registrations_old[group]['instances'].keys()))
                    for instance_id in instances:
                        if instance_id in registrations[group]['instances'] and \
                           instance_id in registrations_old[group]['instances']:
                            reg = registrations[group]['instances'][instance_id]
                            reg_old = registrations_old[group]['instances'][instance_id]

                            statuses = [e['status'] for e in reg['entries']]
                            statuses_old = [e['status'] for e in reg_old['entries']]

                            status = combine_consul_statuses(statuses)
                            status_old = combine_consul_statuses(statuses_old)

                            if status == 'passing' and status != status_old:
                                print("Instance '%s' is passing" %
                                      (group + '_' + instance_id))
                            elif status == 'warning' and status != status_old:
                                print("Instance '%s' is warning" %
                                      (group + '_' + instance_id))
                            elif status == 'critical' and status != status_old:
                                print("Instance '%s' is critical" %
                                      (group + '_' + instance_id))

            blueprints_old = blueprints
            allocations_old = allocations
            registrations_old = registrations
            emergent_states_old = emergent_states

            index_old=index_new

    def stop(self, group_id):
        kv = self.consul.kv
        tarantool_kv = consul_kv_to_dict(kv.get('tarantool', recurse=True)[1] or [])

        instance_ids = set()
        for key, value in tarantool_kv.items():
            match = re.match('tarantool/%s/blueprint/instances/(.*)/' % group_id,
                             key)
            if match:
                instance_ids.add(match.group(1))

        for instance_id in instance_ids:
            consul_host, docker_host = self.locate_tarantool_service(
                group_id+'_'+instance_id)

            if not docker_host:
                for entry in self.consul.kv.get('tarantool', recurse=True)[1] or []:
                    match = re.match('tarantool/%s/allocation/instances/%s/host' %
                                     (group_id, instance_id),
                                     entry['Key'])
                    if match:
                        docker_host = entry['Value'].decode("ascii") + ':2375'


            if docker_host:
                self.stop_container(group_id+'_'+instance_id, docker_host)

            if consul_host:
                self.unregister_tarantool_service(group_id+'_'+instance_id,
                                                  consul_host)

    def start(self, group_id):
        kv = self.consul.kv
        tarantool_kv = consul_kv_to_dict(kv.get('tarantool', recurse=True)[1] or [])

        instance_ids = set()
        for key, value in tarantool_kv.items():
            match = re.match('tarantool/%s/blueprint/instances/(.*)/' % group_id,
                             key)
            if match:
                instance_ids.add(match.group(1))

        blueprints = self.get_blueprints()
        allocations = self.get_allocations()
        emergent_states = self.get_emergent_state()

        blueprint = blueprints[group_id]
        allocation = allocations[group_id]
        state = emergent_states[group_id]

        for instance_id in instance_ids:
            consul_host, docker_host = self.locate_tarantool_service(
                group_id+'_'+instance_id)

            if not consul_host:
                consul_host = allocation['instances'][instance_id]['host']
                addr = blueprint['instances'][instance_id]['addr']
                name = blueprint['name']

                self.register_tarantool_service(consul_host, addr,
                                                group_id+'_'+instance_id,
                                                name,
                                                blueprint['check_period'])

            if not docker_host:
                consul_host, docker_host = self.locate_tarantool_service(
                    group_id+'_'+instance_id)

            if docker_host:
                self.start_container(group_id+'_'+instance_id)

        instance_ids = list(blueprint['instances'].keys())
        instances = blueprint['instances']

        self.enable_memcached_replication(
            instances[instance_ids[0]]['addr'],
            instances[instance_ids[1]]['addr'])
