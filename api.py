#!/usr/bin/env python3

import os
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

        logging.info("Image '%s' not found on '%s'. Building.",
                     image_name, docker.base_url)

        result = docker.pull(image_name, stream=True)

        for line in result:
            logging.info(line)

    def create_memcached_blueprint(self, pair_id, name, ip1, ip2, check_period):
        kv = self.consul.kv

        kv.put('tarantool/%s/type' % pair_id, 'memcached')
        kv.put('tarantool/%s/name' % pair_id, name)
        kv.put('tarantool/%s/check_period' % pair_id, str(check_period))
        kv.put('tarantool/%s/instances/1' % pair_id, ip1)
        kv.put('tarantool/%s/instances/2' % pair_id, ip2)


    def create_memcached(self, docker_host, instance_id, instance_ip, replica_ip):
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

    def delete_container(self, instance_id):
        _, docker_host = \
            self.locate_tarantool_service(instance_id)

        logging.info("Deleting instance '%s' from '%s'",
                     instance_id,
                     docker_host)

        docker_obj = docker.Client(base_url=docker_host)

        docker_obj.stop(container=instance_id)
        docker_obj.remove_container(container=instance_id)

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


    def unregister_tarantool_service(self, instance_id):
        consul_host, docker_host = \
            self.locate_tarantool_service(instance_id)

        consul_obj = consul.Consul(host=consul_host)
        consul_obj.agent.service.deregister(instance_id)

    def locate_tarantool_service(self, instance_id):
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


    def get_blueprints(self):
        """
        returns a list of registered groups:
        {
            'type': 'memcached',
            'name': '<group name>',
            'instances': {
                '1': {'addr': '<ip addr>'},
                '2': {'addr': '<ip addr>'}
            }
        }
        """
        kv = self.consul.kv
        tarantool_kv = kv.get('tarantool', recurse=True)[1] or []

        groups = {}
        for entry in tarantool_kv:
            match = re.match('tarantool/(.*)/type', entry['Key'])
            if match:
                groups[match.group(1)] = {'type': entry['Value'].decode("ascii"),
                                          'instances': {}}

        for entry in tarantool_kv:
            match = re.match('tarantool/(.*)/name', entry['Key'])
            if match:
                groups[match.group(1)]['name'] = entry['Value'].decode("ascii")

            match = re.match('tarantool/(.*)/check_period', entry['Key'])
            if match:
                groups[match.group(1)]['check_period'] = int(entry['Value'])

            match = re.match('tarantool/(.*)/instances/(.*)', entry['Key'])
            if match:
                group = match.group(1)
                instance_id = match.group(2)

                groups[group]['instances'][instance_id] = {
                    'addr': entry['Value'].decode("ascii")
                }

        return groups


    def get_allocations(self):
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
        health = self.consul.health.service('memcached')[1]

        groups = {}
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

            groups[group]['instances'][instance_id] = {
                'addr': addr,
                'host': node,
                'status': status
            }

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

                if group not in groups:
                    groups[group] = {}
                    groups[group]['type'] = 'memcached'
                    groups[group]['name'] = ''
                    groups[group]['instances'] = {}

                groups[group]['instances'][instance_id] = {
                    'addr': addr + ':3301',
                    'host': host
                }


        return groups

    def cleanup_lost_containers(self, group, blueprints,
                                allocations, emergent_states):
        # clean up "lost" containers
        if group in emergent_states and \
           group not in blueprints:
            state = emergent_states[group]
            for instance_id in state['instances']:
                logging.info("Removing '%s' because there is no blueprint" %
                             (group+'_'+instance_id))

                instance = state['instances'][instance_id]
                host = instance['host']

                docker_obj = docker.Client(base_url=host+':2375')
                docker_obj.stop(container=group+'_'+instance_id)
                docker_obj.remove_container(container=group+'_'+instance_id)

            # also clean up service registrations
            if group in allocations:
                alloc = allocations[group]
                for instance_id in alloc['instances']:
                    self.unregister_tarantool_service(group+'_'+instance_id)

            return True

        return False

    def allocate_non_existing_groups(self, group, blueprints,
                                     allocations, emergent_states):
        # allocate groups that don't exist
        if group in blueprints and \
           group not in allocations:
            alloc = self.allocate_group(group, blueprints[group])

            # if there were any existing states, they must be destroyed
            if group in emergent_states:
                state = emergent_states[group]
                for instance_id in state['instances']:
                    instance = state['instances'][instance_id]
                    host = instance['host']

                    docker_obj = docker.Client(base_url=host+':2375')
                    docker_obj.stop(container=group+'_'+instance_id)
                    docker_obj.remove_container(container=group+'_'+instance_id)

            self.run_group(group, alloc)
            return True
        return False

    def rerun_stopped_groups(self, group, blueprints,
                             allocations, emergent_states):
        # start group that is not running
        if group in blueprints and \
           group in allocations and \
           group not in emergent_states:
            alloc = allocations[group]
            self.run_group(group, alloc)
            return True
        return False


    def recreate_missing_allocation(self, group, blueprints,
                                     allocations, emergent_states):

        blueprint_instances = blueprints[group]['instances'].keys()

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
                if instance_id in emergent_instances:
                    instance = emergent_states[group]['instances'][instance_id]
                    host = instance['host']

                    docker_obj = docker.Client(base_url=host+':2375')
                    docker_obj.stop(container=group+'_'+instance_id)
                    docker_obj.remove_container(container=group+'_'+instance_id)

                alloc = self.allocate_instance(group,
                                               blueprints[group],
                                               allocations[group],
                                               instance_id)

                # if we got here, it means other instance is allocated
                combined_allocation = allocations[group].copy()
                combined_allocation['instances'][instance_id] = alloc
                self.run_instance(group,
                                  combined_allocation,
                                  instance_id)
                return True

        return False

    def rerun_missing_instance(self, group, blueprints,
                                     allocations, emergent_states):
        blueprint_instances = blueprints[group]['instances'].keys()

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
                                  allocations[group],
                                  instance_id)

                return True

        return False

    def migrate_instance_to_correct_host(self, group, blueprints,
                                         allocations, emergent_states):
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
                    docker_obj = docker.Client(base_url=emergent['host']+':2375')
                    docker_obj.stop(container=group+'_'+instance_id)
                    docker_obj.remove_container(container=group+'_'+instance_id)

                    self.run_instance(group,
                                      allocations[group],
                                      instance_id)

                    return True
        return False

    def recreate_and_reallocate_failed_instance(self, group, blueprints,
                                                allocations, emergent_states):
        try:
            emergent_instances = emergent_states[group]['instances'].keys()
        except:
            emergent_instances = []

        for instance_id in emergent_instances:
            allocation = allocations[group]['instances'][instance_id]
            emergent = emergent_states[group]['instances'][instance_id]


            # failed instances must be destroyed and re-allocated
            if allocation['status'] not in ('passing', 'warning'):
                logging.info("Recreating '%s' because it has failed" %
                             (group+'_'+instance_id))

                docker_obj = docker.Client(base_url=emergent['host']+':2375')
                docker_obj.stop(container=group+'_'+instance_id)
                docker_obj.remove_container(container=group+'_'+instance_id)

                self.unregister_tarantool_service(group+'_'+instance_id)

                alloc = self.allocate_instance(group,
                                               blueprints[group],
                                               allocations[group],
                                               instance_id)

                # if we got here, it means other instance is allocated
                combined_allocation = allocations[group].copy()
                combined_allocation['instances'][instance_id] = alloc
                self.run_instance(group,
                                  combined_allocation,
                                  instance_id)

                return True

        return False


    def heal_group(self, group, blueprints, allocations, emergent_states):

        healing_functions = [
            self.cleanup_lost_containers,
            self.allocate_non_existing_groups,
            self.rerun_stopped_groups,
            self.recreate_missing_allocation,
            self.rerun_missing_instance,
            self.migrate_instance_to_correct_host,
            self.recreate_and_reallocate_failed_instance
        ]

        for function in healing_functions:
            result = function(group, blueprints,
                              allocations, emergent_states)
            if result:
                return True

        return False


    def heal_groups(self, blueprints, allocations, emergent_states):
        groups = set()

        groups.update(blueprints.keys())
        groups.update(allocations.keys())
        groups.update(emergent_states.keys())

        for group in groups:
            self.heal_group(group, blueprints, allocations, emergent_states)


    def allocate_group(self, group, blueprint):
        healthy_nodes = self.get_healthy_docker_nodes()
        if len(healthy_nodes) >= 2:
            pick = random.sample(healthy_nodes, 2)
        elif len(healthy_nodes) == 1:
            pick = healthy_nodes * 2
        else:
            raise RuntimeError("There are no healthy docker nodes")

        name = blueprint['name']
        instance_type = blueprint['type']

        result = {'name': name, 'type': instance_type, 'instances': {}}

        for i, instance_id in enumerate(blueprint['instances']):
            consul_host = pick[i][0]
            instance = blueprint['instances'][instance_id]
            addr = instance['addr']

            self.register_tarantool_service(consul_host, addr,
                                            group+'_'+instance_id, name,
                                            blueprint['check_period'])

            result['instances'][instance_id] = {
                'host': consul_host,
                'addr': addr
            }
        return result

    def allocate_instance(self, group, blueprint, allocation, instance_id):
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

        self.register_tarantool_service(consul_host, addr,
                                        group+'_'+instance_id, name,
                                        blueprint['check_period'])

        return {
            'host': consul_host,
            'addr': addr
        }


    def run_group(self, group, allocation):
        name = allocation['name']

        instance_ids = list(allocation['instances'].keys())

        instances = allocation['instances']
        for i, instance_id in enumerate(instances):
            instance = instances[instance_id]
            other_instance = instances[instance_ids[1-i]]

            host = instance['host']

            if i == 0:
                self.create_memcached(host,
                                      group+'_'+instance_id,
                                      instance['addr'].split(':')[0],
                                      None)

            else:
                self.create_memcached(host,
                                      group+'_'+instance_id,
                                      instance['addr'].split(':')[0],
                                      other_instance['addr'].split(':')[0])
        self.enable_memcached_replication(
            instances[instance_ids[0]]['addr'],
            instances[instance_ids[1]]['addr'])


    def run_instance(self, group, allocation, instance_id):
        other_instance_id = [i for i in allocation['instances']
                             if i != instance_id][0]

        instance = allocation['instances'][instance_id]
        other_instance = allocation['instances'][other_instance_id]
        host = instance['host']



        self.create_memcached(host,
                              group+'_'+instance_id,
                              instance['addr'].split(':')[0],
                              other_instance['addr'].split(':')[0])



    def create_memcached_pair(self, name, check_period):
        pair_id = self.generate_id()

        ip1 = self.allocate_ip()
        ip2 = self.allocate_ip(skip=[ip1])

        self.create_memcached_blueprint(pair_id, name, ip1, ip2, check_period)

        blueprints = self.get_blueprints()
        allocations = self.get_allocations()
        emergent_states = self.get_emergent_state()
        self.heal_groups(blueprints, allocations, emergent_states)

        #self.enable_memcached_replication(ip1+':3301', ip2+':3301')

        return pair_id

    def delete_memcached_pair(self, pair_id):
        kv = self.consul.kv

        instance_type = kv.get("tarantool/%s/type" % pair_id)

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
            self.delete_container(instance1)
            self.unregister_tarantool_service(instance1)

        if consul2_host and docker2_host:
            consul2 = consul.Consul(host=consul2_host)
            docker2 = docker.Client(base_url=docker2_host)
            self.delete_container(instance2)
            self.unregister_tarantool_service(instance2)

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
                groups[match.group(1)] = entry['Value'].decode("ascii")

        # collect instances from blueprints
        instances = {} # <instance id>: {'type': <type>, 'addr': <addr>}
        for entry in tarantool_kv:
            match = re.match('tarantool/(.*)/instances/(.*)', entry['Key'])
            if match:
                group = match.group(1)
                instance = match.group(2)
                instances[group + '_' + instance] = {
                    'type': groups[group],
                    'addr': entry['Value'].decode("ascii")}


        # collect instance statuses from registered services
        status = {}
        for entry in health:
            check_total = "passing"
            for check in entry['Checks']:
                if check['Status'] == 'critical':
                    check_total = 'critical'
                elif check['Status'] == 'warning' and check_total == 'passing':
                    check_total = 'warning'

            host = entry['Service']['Address'] or entry['Node']['Address']
            port = entry['Service']['Port']
            addr = '%s:%s' % (host, port)
            node = entry['Node']['Address']

            status[entry['Service']['ID']] = {'check': check_total,
                                              'addr': addr,
                                              'node': node}

        result = []
        for instance in instances.keys():

            if instance not in status:
                state = 'missing'
                addr = instances[instance]['addr']
                node = 'N/A'
            else:
                state = status[instance]['check']
                addr = status[instance]['addr']
                node = status[instance]['node']

            group, instance_no = instance.split('_')

            result.append({'group': group,
                           'instance': instance_no,
                           'type': instances[instance]['type'],
                           'state': state,
                           'addr': addr,
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

    def watch(self, watch_period):
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
                    self.heal()

            index_old=index_new