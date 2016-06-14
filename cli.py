#!/usr/bin/env python3

import argparse
import api
import os
import sys
import logging
import time

def create_instance(host, name, check_period):
    a = api.Api(host)
    instance_id = a.create_memcached_pair(name, check_period)

    print(instance_id)

def delete_instance(host, instances):
    a = api.Api(host)
    for instance in instances:
        a.delete_memcached_pair(instance)

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
        ('type', 'TYPE'),
        ('state', 'STATE'),
        ('addr', 'ADDRESS'),
        ('node', 'NODE')
    ]

    if not quiet:
        print_table(header, instances)
    else:
        groups = set([i['group'] for i in instances])
        print('\n'.join(groups))

def heal(host):
    a = api.Api(host)
    a.heal()

def wait(host, instance_or_group_id, passing, warning, critical):
    a = api.Api(host)
    if '_' in instance_or_group_id:
        a.wait_instance(instance_or_group_id, passing, warning, critical)
    else:
        a.wait_group(instance_or_group_id, passing, warning, critical)

def watch(host):
    while True:
        time.sleep(1)


def main():
    logging.basicConfig(format='%(levelname)s: %(message)s',level=logging.INFO)
    parser = argparse.ArgumentParser()
    parser.add_argument('-H', '--host', default = None)
    subparsers = parser.add_subparsers(dest="subparser_name")
    ps_parser = subparsers.add_parser('ps')
    ps_parser.add_argument('-q', '--quiet', action='store_true')
    run_parser = subparsers.add_parser('run')
    run_parser.add_argument('--check-period', '-p', type=int, default=10)
    run_parser.add_argument('name')
    rm_parser = subparsers.add_parser('rm')
    rm_parser.add_argument('instance_id', nargs='+')

    heal_parser = subparsers.add_parser('heal')
    wait_parser = subparsers.add_parser('wait')
    wait_parser.add_argument('--passing', action='store_true', default=False)
    wait_parser.add_argument('--warning', action='store_true', default=False)
    wait_parser.add_argument('--critical', action='store_true', default=False)
    wait_parser.add_argument('instance_or_group_id')
    watch_parser = subparsers.add_parser('watch')

    args = parser.parse_args()

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
        create_instance(host, args.name, args.check_period)
    elif args.subparser_name == 'rm':
        delete_instance(host, args.instance_id)
    elif args.subparser_name == 'heal':
        heal(host)
    elif args.subparser_name == 'wait':
        wait(host, args.instance_or_group_id, args.passing, args.warning, args.critical)
    elif args.subparser_name == 'watch':
        watch(host)


if __name__ == '__main__':
    main()
