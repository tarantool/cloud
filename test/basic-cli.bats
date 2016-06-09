#!/usr/bin/env bats

load "consul_helper"
load "docker_helper"

export PATH=$BATS_TEST_DIRNAME/..:$PATH
export CONSUL_HOST=172.20.20.10

TARANTOOL_KEY_PREFIX=tarantool
TARANTOOL_IMAGE=tarantool/tarantool:latest

get_container_id()
{
    instance_id=$1

    for docker_host in $(consul_get_docker_hosts $CONSUL_HOST); do
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
    for docker_host in $(consul_get_docker_hosts $CONSUL_HOST); do
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

    for docker_host in $(consul_get_docker_hosts $CONSUL_HOST); do
        docker_delete_instance $docker_host:2375 "$instance_id"
    done
}

teardown()
{
    consul_delete_kv $CONSUL_HOST $TARANTOOL_KEY_PREFIX
    consul_delete_services $CONSUL_HOST memcached

    for docker_host in $(consul_get_docker_hosts $CONSUL_HOST); do
        docker_delete_instances $docker_host:2375 $TARANTOOL_IMAGE
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

@test "heal group without running containers" {
    id=$(cli.py run foobar|tail -1)

    ip=$(consul_get_service_ip $CONSUL_HOST memcached "${id}_1")

    ping -c1 -t1 $ip

    delete_container "${id}_1"
    delete_container "${id}_2"

    ! ping -c1 -t1 $ip

    ./cli.py heal

    ping -c1 -t1 $ip
}

@test "delete group with missing blueprint" {
    id=$(cli.py run foobar|tail -1)

    ip=$(consul_get_service_ip $CONSUL_HOST memcached "${id}_1")

    ping -c1 -t1 $ip

    consul_delete_kv $CONSUL_HOST $TARANTOOL_KEY_PREFIX/$id

    ./cli.py heal

    ! ping -c1 -t1 $ip
}

@test "delete container with missing blueprint and allocation" {
    id=$(cli.py run foobar|tail -1)

    ip=$(consul_get_service_ip $CONSUL_HOST memcached "${id}_1")

    ping -c1 -t1 $ip

    consul_delete_kv $CONSUL_HOST $TARANTOOL_KEY_PREFIX/$id
    consul_delete_service $CONSUL_HOST memcached "${id}_1"
    consul_delete_service $CONSUL_HOST memcached "${id}_2"

    ./cli.py heal

    ! ping -c1 -t1 $ip
}


@test "recreate instances of group with missing allocation" {
    id=$(cli.py run foobar|tail -1)

    cid1=$(get_container_id "${id}_1")
    cid2=$(get_container_id "${id}_2")

    consul_delete_service $CONSUL_HOST memcached "${id}_1"
    consul_delete_service $CONSUL_HOST memcached "${id}_2"

    ./cli.py heal

    cid1_new=$(get_container_id "${id}_1")
    cid2_new=$(get_container_id "${id}_2")

    [ "$cid1" != "$cid1_new" ]
    [ "$cid2" != "$cid2_new" ]

}

@test "recreate missing allocation and container" {
    id=$(cli.py run foobar|tail -1)

    ip=$(consul_get_service_ip $CONSUL_HOST memcached "${id}_1")
    cid1=$(get_container_id "${id}_1")
    cid2=$(get_container_id "${id}_2")

    ping -c1 -t1 $ip

    consul_delete_service $CONSUL_HOST memcached "${id}_1"

    ./cli.py heal
    cid1_new=$(get_container_id "${id}_1")
    cid2_new=$(get_container_id "${id}_2")

    ping -c1 -t1 $ip

    [ "$cid1" != "$cid1_new" ]
    [ "$cid2" == "$cid2_new" ]
}

@test "recreate missing instance" {
    id=$(cli.py run foobar|tail -1)

    ip=$(consul_get_service_ip $CONSUL_HOST memcached "${id}_1")
    cid2=$(get_container_id "${id}_2")

    ping -c1 -t1 $ip

    delete_container "${id}_1"

    ! ping -c1 -t1 $ip

    ./cli.py heal

    ping -c1 -t1 $ip

    cid2_new=$(get_container_id "${id}_2")
    [ "$cid2" == "$cid2_new" ]
}

@test "recreate and reallocate instance from blueprint" {
    id=$(cli.py run foobar|tail -1)

    ip=$(consul_get_service_ip $CONSUL_HOST memcached "${id}_1")
    cid1=$(get_container_id "${id}_1")

    consul_delete_service $CONSUL_HOST memcached "${id}_1"
    delete_container "${id}_1"

    ! ping -c1 -t1 $ip

    ./cli.py heal
    cid2_new=$(get_container_id "${id}_2")

    ping -c1 -t1 $ip

    [ "$cid1" != "$cid1_new" ]
}


@test "migrate instance to correct docker host" {
    id=$(cli.py run foobar|tail -1)

    ip=$(consul_get_service_ip $CONSUL_HOST memcached "${id}_1")
    cid=$(get_container_id "${id}_1")

    docker_hosts=$(consul_get_docker_hosts $CONSUL_HOST)
    docker_host_array=($docker_hosts)
    num_docker_hosts=${#docker_host_array[@]}

    host=$(get_docker_host "${id}_1")

    echo "Containers: ${docker_host_array[@]}"
    echo "Current host: $host"

    host_idx=0
    # find out the index of current docker host in array
    for i in "${!docker_host_array[@]}"; do
        if [[ "${docker_host_array[$i]}" = "${host}" ]]; then
            host_idx=$i
            echo "Index of host: $i"
        fi
    done

    new_host_idx=$(bc <<< "($host_idx + 1) % $num_docker_hosts" )
    new_host="${docker_host_array[$new_host_idx]}"
    echo "New idx: $new_host_idx"
    echo "New host: $new_host"

    consul_delete_service $CONSUL_HOST memcached "${id}_1"

    consul_register_service $new_host memcached "${id}_1" "$ip" 3301

    ./cli.py heal

    cid_new=$(get_container_id "${id}_1")

    [ "$cid" != "$cid_new" ]

    host_check=$(get_docker_host "${id}_1")

    [ "$host_check" == "$new_host" ]
}
