#!/usr/bin/env python

import logging
from sense import Sense

def allocate(memory, anti_affinity = []):
    docker_hosts = [h for h in Sense.docker_hosts()
                    if (h['status'] == 'passing' and
                        'im' in h['tags'])]

    if not docker_hosts:
        raise RuntimeError("There are no healthy docker nodes")

    blueprints = Sense.blueprints()
    allocations = Sense.allocations()

    memory_used = {h['addr'].split(':')[0]: 0 for h in docker_hosts}

    for group_id, blueprint in blueprints.items():
        if group_id not in allocations:
            continue

        memsize = blueprint['memsize']

        for instance in allocations[group_id]['instances'].values():
            host = instance['host'].split(':')[0]
            memory_used[host] = memory_used.get(host, 0) + memsize

    scores = []

    for docker_host in docker_hosts:
        addr = docker_host['addr'].split(':')[0]

        free_mem = docker_host['memory'] - memory_used[addr]
        affinity = 0 if addr in anti_affinity else 1

        scores.append((affinity, free_mem, docker_host))



    sorted_scores = sorted(scores, reverse=True,
                           key=lambda k: k[0:2])

    for score in sorted_scores:
        docker_host = score[2]
        addr = docker_host['addr'].split(':')[0]
        free_mem = docker_host['memory'] - memory_used[addr]
        if free_mem > memory:
            logging.info("Allocating new instance with %d MiB memory at '%s'",
                         memory,
                         addr)
            return addr

    docker_host = sorted_scores[0][2]
    addr = docker_host['addr'].split(':')[0]

    logging.info("There were no hosts with %d MiB of free memory, " +
                 "so allocating instance on '%s'",
                 memory,
                 addr)

    return addr
