# Tarantool Cloud

Tarantool Cloud is a service that allows you to run a self-healing, replicated set of tarantool instances. It is built on top of Consul and is resilient to some of the typical hardware and network problems.

It provides the following key features:

- **REST API**: for programmatic creation and destruction of tarantool instances
- **WEB UI**: to allow human agents create single on-demand instances and get an overview of the system
- **Failover**: to automatically recover from node failures or degraded storage

Read more on the wiki: [Documentation](https://github.com/tarantool/cloud/wiki)

## Getting Started

To prepare an environment, do:

```sh
docker-compose up
```

Then go to [http://localhost:5061](http://localhost:5061) to access web UI.

*Note*: first-time creation and launch of tarantool instances may take a long time, as the instance manager is building docker images.

## Managing Tarantool instances via command-line client

### Create new instance:

```sh
./taas -H localhost:5061 run --name myinstance 0.3
```

This will create an instance named `myinstance`, with 0.3 GiB memory limit and return its ID.

### List instances:

```sh
./taas -H localhost:5061 ps
```

It will produce output like this:

```sh
GROUP                             INSTANCE #     NAME        TYPE       SIZE     STATE     ADDRESS       NODE
37c82b4a32344b0cae1143b5d017b204  2              myinstance  memcached  0.3      Down      172.55.128.3  docker1
37c82b4a32344b0cae1143b5d017b204  1              myinstance  memcached  0.3      Down      172.55.128.2  docker1
```

### Inspect an instance

This is a command that shows low-level details about an instance. Make sure to put your own instance ID instead of `37c82b4a32344b0cae1143b5d017b204`

```sh
./taas -H localhost:5061 inspect 37c82b4a32344b0cae1143b5d017b204
```

Will show output like this:

``` bash
[
  {
    "id": "37c82b4a32344b0cae1143b5d017b204",
    "creation_time": "2016-08-16T13:30:24.827509+00:00",
    "name": "myinstance",
    "type": "memcached",
    "memsize": 0.3,
    "instances": [
      ...
    ],
    ...
  }
]
```

### Remove an instance

Make sure to put your own instance ID instead of `37c82b4a32344b0cae1143b5d017b204`

```sh
./taas -H localhost:5061 rm 37c82b4a32344b0cae1143b5d017b204
```

On success, returns nothing.

### Rename/Resize an instance

Make sure to put your own instance ID instead of `37c82b4a32344b0cae1143b5d017b204`

``` bash
./taas -H localhost:5061 update --memsize 1.2 --name newname 37c82b4a32344b0cae1143b5d017b204
```

This will set memory limit to 1.2 GiB and rename instance to 'newname'.

## Creating Tarantool instances via REST API

```sh
curl -X POST -F 'name=myinstance' -F 'memsize=0.2' localhost:5061/api/groups
```

This will create an instance named `myinstance`, with 0.2 GiB memory limit.

## License

BSD (see LICENSE file)
