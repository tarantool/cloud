# == Class: tarantool_cloud
#
# Installs tarantool cloud
#
# === Parameters
#
# [*agent*]
#   If 'true', run consul in agent mode. Otherwise run consul in server mode.
#
# [*instance_manager*]
#   If 'true', install and run Tarantool Cloud Instance Manager on current
#   node.
#
# [*datacenter*]
#   Name of the datacenter. Usually "dc1".
#
# [*bootstrap_address*]
#   Address of one of the consul server nodes. Will beused to bootstrap
#   the cluster.
#
# [*gossip_key*]
#   An encryption key for UDP gossip traffic. It is a symmetrical cipher,
#   as there is no way to use TLS for connectionless protocols.
#   Can be generated with '$ consul keygen'
#   Example: W5n8F9+qEXMqMzeXBl38QQ==
#
# [*acl_master_token*]
#   UUID token to bootstrap ACL system. Should always be the same.
#   Can be generated with '$ uuidgen'
#   Example: F1DC3B5D-732F-4491-9841-340A512E6F9B
#
# [*acl_token*]
#   UUID token that will be used by clients to access consul servers.
#   Can be generated with '$ uuidgen'
#   Example: 77AE22F8-E328-4CE8-83E0-BD66F06FE9BA
#
# [*num_servers*]
#   Number of server instances of consul. Typically 3 or 5. It is not
#   recommended to use more than 5 server instances.
#   This should reflect your real configuration.
#
# [*advertise_addr*]
#   This IP address will be used to advertise the node in Consul and Docker.
#
# [*tls_dir*]
#   Place where TLS certificates are located. Do not change unless you've
#   generated them by hand. tls.pp provides a facility to automatically
#   generate the certificates
#
# [*ca_generator*]
#   Full path to the 'ca.py' scrip on puppet master. This script generates
#   TLS certificates.
#
# [*ca_dir*]
#   Path to the directory on puppet master where TLS certificates will be
#   stored. The user under which puppet muster runs, must have write
#   access to this directory
#
# [*consul_data_dir*]
#   The directory where Consul will store persistent data
#
# [*elasticsearch*]
#   If 'true', send Docker logs to elasticsearch
#
# [*elasticsearch_host*]
#   Address of elasticsearch instance to send logs to
#
# [*elasticsearch_port*]
#   Port of the elasticsearch instance
#
# [*elasticsearch_index*]
#   Elasticsearch index to write logs to
#
# [*elasticsearch_type*]
#   Default type of entries sent to elasticsearch
#
# [*logstash_prefix*]
#   Elasticsearch index prefix
#
# [*ca_cert*]
#   Path to the TLS CA cert file. Generated automatically if not specified.
#   Generate manually with ./ca.py ca
#
# [*server_cert*]
#   Path to the server TLS cert file. Generated automatically if not
#   specified. Generate manually with ./ca.py server <hostname>
#
# [*server_key*]
#   Path to the server TLS key file. Generated automatically if not
#   specified. Generate manually with ./ca.py server <hostname>
#
# [*client_cert*]
#   Path to the client TLS cert file. Generated automatically if not
#   specified. Generate manually with ./ca.py client
#
# [*client_key*]
#   Path to the client TLS key file. Generated automatically if not
#   specified. Generate manually with ./ca.py client
#
class tarantool_cloud(
  $agent               = $tarantool_cloud::params::agent,
  $instance_manager    = $tarantool_cloud::params::instance_manager,
  $datacenter          = $tarantool_cloud::params::datacenter,
  $bootstrap_address   = $tarantool_cloud::params::bootstrap_address,
  $gossip_key          = $tarantool_cloud::params::gossip_key,
  $acl_master_token    = $tarantool_cloud::params::acl_master_token,
  $acl_token           = $tarantool_cloud::params::acl_token,
  $num_servers         = $tarantool_cloud::params::num_servers,
  $advertise_addr      = $tarantool_cloud::params::advertise_addr,
  $tls_dir             = $tarantool_cloud::params::tls_dir,
  $ca_generator        = $tarantool_cloud::params::ca_generator,
  $ca_dir              = $tarantool_cloud::params::ca_dir,
  $consul_data_dir     = $tarantool_cloud::params::consul_data_dir,
  $elasticsearch       = $tarantool_cloud::params::elasticsearch,
  $elasticsearch_host  = $tarantool_cloud::params::elasticsearch_host,
  $elasticsearch_port  = $tarantool_cloud::params::elasticsearch_port,
  $elasticsearch_index = $tarantool_cloud::params::elasticsearch_index,
  $elasticsearch_type  = $tarantool_cloud::params::elasticsearch_type,
  $logstash_prefix     = $tarantool_cloud::params::logstash_prefix,
  $ca_cert             = $tarantool_cloud::params::ca_cert,
  $server_cert         = $tarantool_cloud::params::server_cert,
  $server_key          = $tarantool_cloud::params::server_key,
  $client_cert         = $tarantool_cloud::params::client_cert,
  $client_key          = $tarantool_cloud::params::client_key
) inherits tarantool_cloud::params {
  validate_bool($agent)
  validate_bool($instance_manager)
  validate_string($datacenter)
  validate_ip_address($bootstrap_address)
  validate_string($gossip_key)
  validate_string($acl_master_token)
  validate_string($acl_token)
  validate_integer($num_servers)
  validate_ip_address($advertise_addr)
  validate_absolute_path($ca_generator)
  validate_absolute_path($ca_dir)
  validate_absolute_path($tls_dir)
  validate_absolute_path($consul_data_dir)

  contain 'tarantool_cloud::tls'

  if ($agent) {
    contain 'tarantool_cloud::consul_agent'
  }
  else {
    contain 'tarantool_cloud::consul_server'
  }

  contain 'tarantool_cloud::docker'

  contain 'tarantool_cloud::fluentd'

  if ($instance_manager) {
    contain 'tarantool_cloud::instance_manager'
  }
}
