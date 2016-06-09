#!/bin/bash

docker_delete_instances()
{
    docker_host=$1
    image_name=$2

    containers=$(docker -H "$docker_host" ps -a --format "{{.Image}} {{.ID}}" |
                        grep  "^$image_name " |
                        sed "s#^$image_name ##g")
    for container in $containers; do
        docker -H "$docker_host" stop $container > /dev/null
        docker -H "$docker_host" rm $container > /dev/null
    done
}

docker_delete_instance()
{
    docker_host=$1
    instance_id=$2

    docker -H "$docker_host" stop $instance_id > /dev/null || true
    docker -H "$docker_host" rm $instance_id > /dev/null || true
}

docker_get_container_id()
{
    docker_host=$1
    instance_id=$2

    id=$(docker -H "$docker_host" inspect --format="{{.Id}}" "$instance_id" 2>/dev/null || true)
    if [ ! -z "$id" ]; then
        echo $id
    fi
}
