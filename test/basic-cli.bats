#!/usr/bin/env bats

load "consul_helper"
load "docker_helper"

export PATH=$BATS_TEST_DIRNAME/..:$PATH

[ -z "$CONSUL_HOST" ] && echo "Please set CONSUL_HOST" && exit 1;

TARANTOOL_KEY_PREFIX=tarantool
TARANTOOL_IMAGE=tarantool/tarantool:latest

get_container_id()
{
    instance_id=$1

    for docker_host in $(consul_get_healthy_docker_hosts $CONSUL_HOST); do
        id=$(docker_get_container_id "$docker_host:2375" "$instance_id")
        if [ ! -z "$id" ]; then
            echo $id
            return
        fi
    done
}

get_docker_host()
{
    instance_id=$1
    for docker_host in $(consul_get_healthy_docker_hosts $CONSUL_HOST); do
        id=$(docker_get_container_id "$docker_host:2375" "$instance_id")
        if [ ! -z "$id" ]; then
            echo $docker_host
            return
        fi
    done
}

delete_container()
{
    instance_id=$1

    for docker_host in $(consul_get_healthy_docker_hosts $CONSUL_HOST); do
        docker_delete_instance $docker_host:2375 "$instance_id"
    done
}

teardown()
{
    consul_delete_kv $CONSUL_HOST $TARANTOOL_KEY_PREFIX
    consul_delete_services $CONSUL_HOST memcached

    for docker_host in $(consul_get_healthy_docker_hosts $CONSUL_HOST); do
        docker_delete_instances $docker_host:2375 $TARANTOOL_IMAGE
    done
}

@test "starting new group" {
    [ -z "$(taas.py -v ps -q)" ]

    id=$(taas.py -v run foobar|tail -1)

    [ ! -z "$id" ]

    [ ! -z "$(taas.py -v ps -q)" ]
}


@test "removing running group" {
    [ -z "$(taas.py -v ps -q)" ]

    id=$(taas.py -v run foobar|tail -1)

    [ ! -z "$id" ]

    [ ! -z "$(taas.py -v ps -q)" ]

    taas.py -v rm $id

    [ -z "$(taas.py -v ps -q)" ]

}

@test "heal group without running containers" {
    id=$(taas.py -v run foobar|tail -1)

    ip=$(consul_get_service_ip $CONSUL_HOST memcached "${id}_1")

    ping -c1 -t1 $ip

    delete_container "${id}_1"
    delete_container "${id}_2"

    ! ping -c1 -t1 $ip

    ./taas.py -v heal

    ping -c1 -t1 $ip
}

@test "delete group with missing blueprint" {
    id=$(taas.py -v run foobar|tail -1)

    ip=$(consul_get_service_ip $CONSUL_HOST memcached "${id}_1")

    ping -c1 -t1 $ip

    consul_delete_kv $CONSUL_HOST $TARANTOOL_KEY_PREFIX/$id

    ./taas.py -v heal

    ! ping -c1 -t1 $ip
}

@test "delete container with missing blueprint and allocation" {
    id=$(taas.py -v run foobar|tail -1)

    ip=$(consul_get_service_ip $CONSUL_HOST memcached "${id}_1")

    ping -c1 -t1 $ip

    consul_delete_kv $CONSUL_HOST $TARANTOOL_KEY_PREFIX/$id/blueprint
    consul_delete_service $CONSUL_HOST memcached "${id}_1"
    consul_delete_service $CONSUL_HOST memcached "${id}_2"

    ./taas.py -v heal

    ! ping -c1 -t1 $ip
}


@test "recreate instances of group with missing allocation" {
    id=$(taas.py -v run foobar|tail -1)

    cid1=$(get_container_id "${id}_1")
    cid2=$(get_container_id "${id}_2")

    consul_delete_kv $CONSUL_HOST $TARANTOOL_KEY_PREFIX/$id/allocation

    ./taas.py -v heal

    cid1_new=$(get_container_id "${id}_1")
    cid2_new=$(get_container_id "${id}_2")

    [ "$cid1" != "$cid1_new" ]
    [ "$cid2" != "$cid2_new" ]

}

@test "recreate missing allocation and container" {
    id=$(taas.py -v run foobar|tail -1)

    ip=$(consul_get_service_ip $CONSUL_HOST memcached "${id}_1")
    cid1=$(get_container_id "${id}_1")
    cid2=$(get_container_id "${id}_2")

    ping -c1 -t1 $ip

    consul_delete_kv $CONSUL_HOST $TARANTOOL_KEY_PREFIX/$id/allocation/instances/1

    ./taas.py -v heal
    cid1_new=$(get_container_id "${id}_1")
    cid2_new=$(get_container_id "${id}_2")

    ping -c1 -t1 $ip

    [ "$cid1" != "$cid1_new" ]
    [ "$cid2" == "$cid2_new" ]
}

@test "recreate missing instance" {
    id=$(taas.py -v run foobar|tail -1)

    ip=$(consul_get_service_ip $CONSUL_HOST memcached "${id}_1")
    cid2=$(get_container_id "${id}_2")

    ping -c1 -t1 $ip

    delete_container "${id}_1"

    ! ping -c1 -t1 $ip

    ./taas.py -v heal

    ping -c1 -t1 $ip

    cid2_new=$(get_container_id "${id}_2")
    [ "$cid2" == "$cid2_new" ]
}

@test "recreate and reallocate instance from blueprint" {
    id=$(taas.py -v run foobar|tail -1)

    ip=$(consul_get_service_ip $CONSUL_HOST memcached "${id}_1")
    cid1=$(get_container_id "${id}_1")

    consul_delete_kv $CONSUL_HOST $TARANTOOL_KEY_PREFIX/$id/allocation/instances/1
    consul_delete_service $CONSUL_HOST memcached "${id}_1"
    delete_container "${id}_1"

    ! ping -c1 -t1 $ip

    ./taas.py -v heal
    cid2_new=$(get_container_id "${id}_2")

    ping -c1 -t1 $ip

    [ "$cid1" != "$cid1_new" ]
}


@test "migrate instance to correct docker host" {
    id=$(taas.py -v run foobar|tail -1)

    ip=$(consul_get_service_ip $CONSUL_HOST memcached "${id}_1")
    cid=$(get_container_id "${id}_1")

    docker_hosts=$(consul_get_healthy_docker_hosts $CONSUL_HOST)
    docker_host_array=($docker_hosts)
    num_docker_hosts=${#docker_host_array[@]}

    host=$(get_docker_host "${id}_1")

    host_idx=0
    # find out the index of current docker host in array
    for i in "${!docker_host_array[@]}"; do
        if [[ "${docker_host_array[$i]}" = "${host}" ]]; then
            host_idx=$i
        fi
    done

    new_host_idx=$(bc <<< "($host_idx + 1) % $num_docker_hosts" )
    new_host="${docker_host_array[$new_host_idx]}"

    consul_delete_kv $CONSUL_HOST $TARANTOOL_KEY_PREFIX/$id/allocation/instances/1

    consul_put_kv $CONSUL_HOST $TARANTOOL_KEY_PREFIX/$id/allocation/instances/1/host $new_host

    ./taas.py -v heal

    cid_new=$(get_container_id "${id}_1")

    [ "$cid" != "$cid_new" ]

    host_check=$(get_docker_host "${id}_1")

    [ "$host_check" == "$new_host" ]
}

@test "recreate failing container" {
    id=$(./taas.py -v run --check-period 1 foobar|tail -1)

    ip=$(consul_get_service_ip $CONSUL_HOST memcached "${id}_1")
    cid=$(get_container_id "${id}_1")

    host=$(get_docker_host "${id}_1")

    docker -H $host:2375 stop "${id}_1"

    ./taas.py -v wait --critical "${id}_1"

    ! ping -t1 -c1 $ip

    ./taas.py -v heal

    ./taas.py -v wait --warning --passing "${id}_1"

    cid_new=$(get_container_id "${id}_1")

    ping -t1 -c1 $ip

    [ "$cid" != "$cid_new" ]

}
