class profiles::consul {
  $tls_dir = '/etc/tarantool_cloud/tls'

  $datacenter = hiera('private::tarantool_cloud::consul::datacenter')
  $bootstrap_address = hiera('private::tarantool_cloud::consul::bootstrap_address')
  $gossip_key = hiera('private::tarantool_cloud::consul::gossip_key')
  $acl_master_token = hiera('private::tarantool_cloud::consul::acl_master_token')
  $acl_token = hiera('private::tarantool_cloud::consul::acl_token')
  $num_servers = hiera('private::tarantool_cloud::consul::num_servers')
  $advertise_addr = "${::external_ip}"

  $common_config = {
    'data_dir'         => '/var/lib/consul',
    'bind_addr'        => '0.0.0.0',
    'client_addr'      => '0.0.0.0',
    'advertise_addr'   => "${advertise_addr}",
    'ui'               => true,
    'datacenter'       => "${datacenter}",
    'log_level'        => 'INFO',
    #'node_name'        => 'server',
    'retry_join'       => ["${bootstrap_address}"],
    'ca_file'          => "${tls_dir}/ca.crt",
    'cert_file'        => "${tls_dir}/server.crt",
    'key_file'         => "${tls_dir}/server.key",
    'verify_incoming'  => true,
    'verify_outgoing'  => true,
    'verify_server_hostname' => false,
    'encrypt'          => "${gossip_key}",
    'acl_datacenter'   => "${datacenter}",
    'acl_master_token' => "${acl_master_token}",
    'acl_token'        => 'anonymous',
    'acl_default_policy' => 'deny'
  }

  package { 'unzip':
    ensure => installed,
    name   => 'unzip',
  }
}

class profiles::consul::server {
  require ::profiles::consul

  $config = merge($::profiles::consul::common_config,
    {
      'server' => true,
      'bootstrap_expect' => $::profiles::consul::num_servers
    })

  class { '::consul':
    config_hash => $config
  }
  consul_acl { "Consul agent access token":
    ensure => 'present',
    id     => $::profiles::consul::acl_token,
    rules  => {'service' => {'' => {'policy' => 'write'}},
               'key' => {'' => {'policy' => 'write'}}},
    type   => 'client',
    acl_api_token => $::profiles::consul::acl_master_token
  }

  ::consul::service { 'docker':
    checks  => [
      {
      script   => 'docker info',
      interval => '10s'
      }
    ],
      port    => 2376,
      tags    => ['im'],
      token   => $::profiles::consul::acl_token
  }
}

class profiles::consul::agent {
  require ::profiles::consul

  $config = merge($::profiles::consul::common_config,
    {
      'server' => false
    })

  class { '::consul':
    config_hash => $config
  }

  ::consul::service { 'docker':
    checks  => [
      {
      script   => 'docker info',
      interval => '10s'
      }
    ],
      port    => 2376,
      tags    => ['im'],
      token   => $::profiles::consul::acl_token
  }
}
