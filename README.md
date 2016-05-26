### Tarantool Cloud

Tarantool Cloud is a service that allows you to run a self-healing, replicated set of tarantool instances. It is built on top of Consul and is resilient to some of the typical hardware and network problems.

It provides the following key features:

- **REST API**: for programmatic creation and destruction of tarantool instances
- **WEB UI**: to allow human agents create single on-demand instances and get an overview of the system
- **Failover**: to automatically recover from node failures or degraded storage

Read more on the wiki: [Documentation](https://github.com/tarantool/cloud/wiki)

**NB**: the system is in its inception stages, so don't expect much from it at this point.

#### Getting Started

To get youself a development environment, you will need [Vagrant](https://www.vagrantup.com).

To prepare an environment, do:

```sh
vagrant up
```

Please note, that while there is no real provisioning, the consul server is bootstrapped using static IPs, thus Vagrant is forced to pin those static IPs to VMs. If something doesn't work for you, it is likely because of IP address clash. See `Vagrantfile` for details.

To create a tarantool-memcached instance, do this:

```sh
export CONSUL_HOST=172.20.20.10
./cli.py run myinstance

./cli.py ps
```

After running `./cli.py ps` you will get a list of running memcached instances and their IP addresses. Now you can connect to them and use them.
