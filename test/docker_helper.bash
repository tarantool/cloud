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
