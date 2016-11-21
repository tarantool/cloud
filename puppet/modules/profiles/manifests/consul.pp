# == Class: profiles::consul
#
# Base class that contains Consul configuration. To use it, you'll need
# to instantiate either profiles::consul::agent or profiles::consul:server,
# depending on your needs.
#
# === Parameters
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
# [*tls_dir*]
#   Place where TLS certificates are located. Do not change unless you've
#   generated them by hand. tls.pp provides a facility to automatically
#   generate the certificates
#
class profiles::consul(
  $datacenter,
  $bootstrap_address,
  $gossip_key,
  $acl_master_token,
  $acl_token,
  $num_servers,
  $tls_dir = '/etc/tarantool_cloud/tls'
) {
  $advertise_addr = $::external_ip

  $common_config = {
    'data_dir'               => '/var/lib/consul',
    'bind_addr'              => '0.0.0.0',
    'client_addr'            => '0.0.0.0',
    'advertise_addr'         => $advertise_addr,
    'ui'                     => true,
    'datacenter'             => $datacenter,
    'log_level'              => 'INFO',
    'retry_join'             => [$bootstrap_address],
    'ca_file'                => "${tls_dir}/ca.crt",
    'cert_file'              => "${tls_dir}/server.crt",
    'key_file'               => "${tls_dir}/server.key",
    'verify_incoming'        => true,
    'verify_outgoing'        => true,
    'verify_server_hostname' => false,
    'encrypt'                => $gossip_key,
    'acl_datacenter'         => $datacenter,
    'acl_master_token'       => $acl_master_token,
    'acl_token'              => 'anonymous',
    'acl_default_policy'     => 'deny'
  }

  package { 'unzip':
    ensure => installed,
    name   => 'unzip',
  }
}
