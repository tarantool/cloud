#!/usr/bin/env python3

import argparse
import api
import os
import sys
import logging
import time

def create_instance(host, name, memsize, check_period):
    a = api.Api(host)
    instance_id = a.create_memcached_pair(name, memsize, check_period)

    print(instance_id)

def delete_instance(host, instances):
    a = api.Api(host)
    for instance_or_group_id in instances:
        if '_' in instance_or_group_id:
            a.delete_container(instance_or_group_id)
        else:
            a.delete_memcached_pair(instance_or_group_id)

def print_table(header, data):
    lengths = [0] * len(header)

    for idx, field in enumerate(header):
        maxlen = max([len(d[field[0]])+1 for d in data] + [len(field[1]) + 4])
        lengths[idx] = maxlen

    fmt = " ".join('{!s:<%d}'%l for l in lengths)

    print(fmt.format(*[c[1] for c in header]))
    for entry in data:
        print(fmt.format(*[entry[c[0]] for c in header]))

def list_instances(host, quiet = False):
    a = api.Api(host)

    instances = a.list_memcached_pairs()

    header = [
        ('group', 'GROUP'),
        ('instance', 'INSTANCE #'),
        ('name', 'NAME'),
        ('type', 'TYPE'),
        ('size', 'SIZE'),
        ('state', 'STATE'),
        ('addr', 'ADDRESS'),
        ('node', 'NODE')
    ]

    if not quiet:
        print_table(header, instances)
    else:
        groups = set([i['group'] for i in instances])
        print('\n'.join(groups))

def heal(host, attach, heal_period):
    a = api.Api(host)
    if attach:
        try:
            a.heal_loop(heal_period)
        except KeyboardInterrupt:
            pass
    else:
        a.heal()

def wait(host, instance_or_group_id, passing, warning, critical):
    a = api.Api(host)
    if '_' in instance_or_group_id:
        a.wait_instance(instance_or_group_id, passing, warning, critical)
    else:
        a.wait_group(instance_or_group_id, passing, warning, critical)

def watch(host, watch_period):
    a = api.Api(host)
    try:
        a.watch(watch_period)
    except KeyboardInterrupt:
        pass

def stop(host, group_id):
    a = api.Api(host)
    a.stop(group_id)

def start(host, group_id):
    a = api.Api(host)
    a.start(group_id)

def main():
    # Don't spam with HTTP connection logs from 'requests' module
    logging.getLogger("requests").setLevel(logging.WARNING)

    parser = argparse.ArgumentParser()

    parser.add_argument('-H', '--host',
                        default = None,
                        help='specify consul host to connect to')
    parser.add_argument('-v', '--verbose',
                        action='store_true',
                        default=False,
                        help='enable verbose output')

    subparsers = parser.add_subparsers(title="commands", dest="subparser_name")

    ps_parser = subparsers.add_parser(
        'ps', help='show a list of running groups')
    ps_parser.add_argument('-q', '--quiet',
                           action='store_true',
                           help='only show group IDs')

    run_parser = subparsers.add_parser(
        'run', help='run a new group')
    run_parser.add_argument('--check-period', '-p', type=int, default=10,
                            help='how often to run consul checks')
    run_parser.add_argument('--memsize',
                            type=float,
                            help='amount of memory to allocate',
                            default=0.5)
    run_parser.add_argument('name',
                            help='name of the new group')

    rm_parser = subparsers.add_parser(
        'rm', help='remove one or more groups')
    rm_parser.add_argument('instance_or_group_id',
                           nargs='+',
                           help='group to remove')

    heal_parser = subparsers.add_parser(
        'heal', help='recover groups in failed state')

    heal_parser.add_argument(
        '--attach', '-a', action='store_true', default=False,
        help='attach to system and run healing continuously',)
    heal_parser.add_argument('--heal-period', '-p', type=int, default=300,
                              help='how often to query health checks')

    wait_parser = subparsers.add_parser(
        'wait', help='wait for group to get to certain state')
    wait_parser.add_argument('--passing', action='store_true', default=False,
                             help='wait until passing state')
    wait_parser.add_argument('--warning', action='store_true', default=False,
                             help='wait until warning state')
    wait_parser.add_argument('--critical', action='store_true', default=False,
                             help='wait until critical state')
    wait_parser.add_argument('instance_or_group_id',
                             help='ID of group or instance to wait for')

    watch_parser = subparsers.add_parser(
        'watch', help='monitor for state changes')
    watch_parser.add_argument('--watch-period', '-p', type=int, default=300,
                              help='how often to query health checks')


    stop_parser = subparsers.add_parser(
        'stop', help='stop group')
    stop_parser.add_argument('group_id',
                             help='group ID to stop')

    start_parser = subparsers.add_parser(
        'start', help='start group')
    start_parser.add_argument('group_id',
                             help='group ID to start')


    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(format='%(levelname)s: %(message)s',
                            level=logging.INFO)


    if args.host is None:
        if 'CONSUL_HOST' in os.environ:
            host = os.environ['CONSUL_HOST']
        else:
            sys.exit("Please specify --host or pass CONSUL_HOST via env")
    else:
        host = args.host

    if args.subparser_name == 'ps':
        list_instances(host, args.quiet)
    elif args.subparser_name == 'run':
        create_instance(host, args.name, args.memsize, args.check_period)
    elif args.subparser_name == 'rm':
        delete_instance(host, args.instance_or_group_id)
    elif args.subparser_name == 'heal':
        heal(host, args.attach, args.heal_period)
    elif args.subparser_name == 'wait':
        wait(host, args.instance_or_group_id, args.passing, args.warning, args.critical)
    elif args.subparser_name == 'watch':
        watch(host, args.watch_period)
    elif args.subparser_name == 'stop':
        stop(host, args.group_id)
    elif args.subparser_name == 'start':
        start(host, args.group_id)


if __name__ == '__main__':
    main()
