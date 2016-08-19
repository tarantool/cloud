#!/usr/bin/env python

import ipaddress
import gevent
import threading
import docker
from sense import Sense
import re
from gevent.lock import RLock
import datetime
import logging
import time

IP_CACHE = {}
CACHE_LOCK = RLock()
CACHE_EXPIRATION_TIME = 30

def invalidate_cache():
    global IP_CACHE
    global CACHE_LOCK

    now = datetime.datetime.now()
    with CACHE_LOCK:
        for addr, created_time in list(IP_CACHE.items()):
            if (now - created_time).seconds > CACHE_EXPIRATION_TIME:
                logging.info("Expiring cached address: %s", addr)
                del IP_CACHE[addr]


def allocate_ip(skip=[]):
    global IP_CACHE
    global CACHE_LOCK

    docker_nodes = [h for h in Sense.docker_hosts() if h['status'] == 'passing']
    network_settings = Sense.network_settings()
    subnet = network_settings['subnet']
    gateway_ip = network_settings['gateway_ip']
    if gateway_ip:
        skip += [gateway_ip]
    if not subnet:
        raise RuntimeError("Subnet is not specified in settings")

    invalidate_cache()
    with CACHE_LOCK:
        allocated_ips = set(IP_CACHE.keys())
        # collect instances from blueprints
        for blueprint in Sense.blueprints().values():
            for instance in blueprint['instances'].values():
                allocated_ips.add(instance['addr'])
        net = ipaddress.ip_network(subnet)

        except_list = allocated_ips.union(set(skip))
        for addr in net:
            if str(addr) not in except_list and\
               not str(addr).endswith('.0'):
                IP_CACHE[str(addr)] = datetime.datetime.now()
                return str(addr)

    raise RuntimeError('IP Address range exhausted')

def ip_cache_invalidation_loop():
    while True:
        try:
            invalidate_cache()
            time.sleep(10)
        except Exception:
            time.sleep(10)
