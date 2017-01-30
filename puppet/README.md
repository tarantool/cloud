# Tarantool Cloud puppet manifest

This manifest helps you deploy an Instance Manager (the integral part of
Tarantool Cloud). The instance manager itself is not complicated, but
it requires Consul to be set up in clustered mode and both Consul and
Docker to have TLS-based client authentication enabled and configured
properly.

*NB:* You must set the `external_ip` fact on every node, otherwise the
system will not work.

*NB:* If you bootstrap the cluster for the first time, initial runs
of this manifest will fail, as it will fail to set ACLs unless the
cluster has choosen a leader. Just restart provisioning until it
succeeds.

## Dependencies

* [docker](https://forge.puppet.com/garethr/docker) from puppet forge
* [consul](https://forge.puppet.com/KyleAnderson/consul) from puppet forge

## Platforms

* Centos 7
* Ubuntu 16.04
* Ubuntu 14.04

## Design

Since we need to have TLS certificates generated and distribute them to
every server node, I made a decision to generate certificates on puppet
master.

To do it, there is a script called `ca.py` in the root of this repo. It
should be put to `/opt/tarantool_cloud/ca.py` and made executable and
accessible by puppet master.

The `ca.py` script will generate every certificate only once and store
it in `/var/tarantool_cloud/ca` using a consistent naming convention.
Every subsequent call to generate the already present server certificate
will just result in `ca.py` returning previously generated certificate.

The root CA cert is also generated only once, so you can safely request
it multiple times.

This also means that if you want to regenerate a certificate, you should
delete it from puppet master.

Since we have TLS auth enabled, both Docker and Consul are safely
exposed to internal network, and they won't permit connections unless
the client has proper client certificate.

The Instance Manager uses TLS certificates and Consul API tokens to
authenticate.

If you want to generate certificates manually, e.g. when you have
multiple puppet masters, you should specify *_cert and *_key parameters
of tarantool_cloud.

## Usage

You can take a look at the example hiera config in test/shared, and at
.kitchen.yml to get a few practical ideas. Also, see the Testing section below.

To bootstrap the system, you will need 3 or 5 Consul nodes in server mode,
0 or more Consul nodes in agent mode, and a node with Tarantool Cloud
Instance Manager itself.

Every node that will run database instances or the instance manager should
also have Docker configured.

To use, include `tarantool_cloud` class. All its parameters can be tuned via
hiera. There should be one node where `instance_manager` parameter is set
to 'true'.


### Configurable Parameters

Every parameter below that is 'undef' you have to fill in before the deployment.

``` puppet
class { 'tarantool_cloud':
  agent              => false,
  instance_manager    => false,
  datacenter          => 'dc1',
  bootstrap_address   => undef,
  gossip_key          => undef,
  acl_master_token    => undef,
  acl_token           => undef,
  num_servers         => undef,
  advertise_addr      => undef,
  tls_dir             => '/etc/tarantool_cloud/tls',
  ca_generator        => '/opt/tarantool_cloud/ca.py',
  ca_dir              => '/var/tarantool_cloud/ca',
  consul_data_dir     => '/var/lib/consul',
  elasticsearch       => false
  elasticsearch_host  => undef
  elasticsearch_port  => 9200
  elasticsearch_index => 'fluentd'
  elasticsearch_type  => 'fluentd'
}
```

* agent -- If 'true', run Consul in agent mode. Otherwise in server mode.
* instance_manager -- If 'true', install and run Instance Manager.
* datacenter -- Consul datacenter name (may be arbitrary, but usually `dc1`)
* bootstrap_address -- Address of one of the Consul servers. Used for bootstrap.
* gossip_key -- Password to encrypt UDP gossip traffic
* acl_master_token -- UUID for bootstrapping ACL system
* acl_token -- UUID token for client access to Consul
* num_servers -- Number of Consul instances in server mode
* advertise_addr -- This IP address will be used to advertise the node in Consul and Docker
* tls_dir -- do not change if you rely on auto-generated TLS certificates
* ca_generator -- Full path to the 'ca.py' scrip on puppet master. This script generates TLS certificates.
* ca_dir -- Path to the directory on puppet master where TLS certificates will be stored.
* consul_data_dir -- The directory where Consul will store persistent data
* elasticsearch -- If 'true', send Docker logs to elasticsearch
* elasticsearch_host -- Address of elasticsearch instance to send logs to
* elasticsearch_port -- Port of the elasticsearch instance
* elasticsearch_index -- Elasticsearch index to write logs to
* elasticsearch_type -- Default type of entries sent to elasticsearch
* logstash_prefix -- Elasticsearch index prefix
* ca_cert -- Path to the TLS CA certificate
* server_cert -- Path to the server TLS certificate
* server_key -- Path to the server TLS key
* client_cert -- Path to the client TLS certificate
* client_key -- Path to the client TLS key

## Testing

This manifest has no integration tests, but there is a test-kitchen definition
that you can use to check that it converges.

``` bash
cd puppet
kitchen converge
```

To run it you will need:

* [test-kitchen](http://kitchen.ci) itself
* [vagrant](http://vagrantup.com)
* [puppet](https://puppet.com)
* [hiera](https://github.com/puppetlabs/hiera)
* [puppet plugin for test-kitchen](https://github.com/neillturner/kitchen-puppet)
* [librarian-puppet](http://librarian-puppet.com) to fetch dependencies

## Authors

* Konstantin Nazarov <mail@kn.am>
