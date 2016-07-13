#!/usr/bin/env python

import ipaddress
import gevent
import threading
import docker
from sense import Sense
import re
from gevent.lock import RLock

IP_CACHE = set()
CACHE_LOCK = RLock()

def invalidate_cache():
    global IP_CACHE
    global CACHE_LOCK

    with CACHE_LOCK:
        allocated_ips = set()
        for blueprint in Sense.blueprints().values():
            for instance in blueprint['instances'].values():
                allocated_ips.add(instance['addr'])
        IP_CACHE = IP_CACHE - allocated_ips



def allocate_ip(skip=[]):
    global IP_CACHE
    global CACHE_LOCK

    docker_nodes = [h for h in Sense.docker_hosts() if h['status'] == 'passing']

    alloc_ranges = []
    for node in docker_nodes:
        docker_obj = docker.Client(base_url=node['addr'])
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

    if len(set(alloc_ranges)) == 0:
        raise RuntimeError("Can't allocate IP address")

    if len(set(alloc_ranges)) > 1:
        raise RuntimeError('Different IP ranges set up on docker hosts: %s' %
                           str(set(alloc_ranges)))


    invalidate_cache()
    with CACHE_LOCK:
        allocated_ips = IP_CACHE.copy()
        # collect instances from blueprints
        for blueprint in Sense.blueprints().values():
            for instance in blueprint['instances'].values():
                allocated_ips.add(instance['addr'])
        subnet = alloc_ranges[0]
        net = ipaddress.ip_network(subnet)

        except_list = allocated_ips.union(set(skip))
        for addr in net:
            if str(addr) not in except_list:
                IP_CACHE.add(str(addr))
                return str(addr)

    raise RuntimeError('IP Address range exhausted')
