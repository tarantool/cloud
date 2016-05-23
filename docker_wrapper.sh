#!/bin/bash

usage() {
    cat >&2 <<EOF
Usage:
    docker_wrapper.sh start  <container_name> <docker_args>
                      stop   <container_name>
EOF
    exit 1
}


start_if_needed()
{
    name=$1
    shift 1

    RUN_STATUS=$(docker inspect --format='{{.State.Running}}' $name 2>/dev/null) || true

    case ${RUN_STATUS} in
        "true")
            CONTAINER_ID=$(docker inspect --format='{{.Id}}' $name 2>/dev/null)
            echo $CONTAINER_ID
        ;;
        "false")
            CONTAINER_ID=$(docker inspect --format='{{.Id}}' $name 2>/dev/null)
            docker start $CONTAINER_ID
        ;;
        "")
            docker run -d --name=$name "$@"
        ;;
    esac
}

stop() {
    docker stop $1 >/dev/null 2>&1 || echo "$2 is not running." >&2
}

[ $# -gt 0 ] || usage
COMMAND=$1
shift 1


case "$COMMAND" in
    start)
        name=$1
        shift 1
        start_if_needed $name "$@"
    ;;
    stop)
        stop $1
    ;;
    *)
        usage
    ;;
esac
