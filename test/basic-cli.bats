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

@test "heal missing instance" {
    id=$(cli.py run foobar|tail -1)

    ip=$(consul_get_service_ip $CONSUL_HOST memcached "${id}_1")

    ping -c1 -t1 $ip

    for docker_host in $(consul_get_docker_hosts $CONSUL_HOST); do
        docker_delete_instance $docker_host "${id}_1"
    done

    ! ping -c1 -t1 $ip

    ./cli.py heal

    ping -c1 -t1 $ip
}

@test "delete instance with missing blueprint" {
    id=$(cli.py run foobar|tail -1)

    ip=$(consul_get_service_ip $CONSUL_HOST memcached "${id}_1")

    ping -c1 -t1 $ip

    consul_delete_kv $CONSUL_HOST $TARANTOOL_KEY_PREFIX/$id

    ./cli.py heal

    ! ping -c1 -t1 $ip
}


@test "recreate missing allocations and containers" {


}
