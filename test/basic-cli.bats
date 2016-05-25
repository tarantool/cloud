#!/usr/bin/env bats

load "consul_helper"
load "docker_helper"

export PATH=$BATS_TEST_DIRNAME/..:$PATH
export CONSUL_HOST=172.20.20.10

TARANTOOL_KEY_PREFIX=tarantool
TARANTOOL_IMAGE=tarantool/tarantool:latest

teardown()
{
    consul_delete_kv $CONSUL_HOST $TARANTOOL_KEY_PREFIX
    consul_delete_services $CONSUL_HOST memcached

    for docker_host in $(consul_get_docker_hosts $CONSUL_HOST); do
        docker_delete_instances $docker_host $TARANTOOL_IMAGE
    done
}

@test "starting new group" {
    [ -z "$(cli.py ps -q)" ]

    id=$(cli.py run foobar|tail -1)

    [ ! -z "$id" ]

    [ ! -z "$(cli.py ps -q)" ]
}


@test "removing running group" {
    [ -z "$(cli.py ps -q)" ]

    id=$(cli.py run foobar|tail -1)

    [ ! -z "$id" ]

    [ ! -z "$(cli.py ps -q)" ]

    cli.py rm $id

    [ -z "$(cli.py ps -q)" ]

}
