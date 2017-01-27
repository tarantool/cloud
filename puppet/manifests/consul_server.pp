# == Class: tarantool_cloud::consul::server
#
# Sets up a server instance of Consul. The server participates in
# leader election and can be chosen as leaders.
#
class tarantool_cloud::consul_server{
  $config = {
    'data_dir'               => '/var/lib/consul',
    'bind_addr'              => '0.0.0.0',
    'client_addr'            => '0.0.0.0',
    'advertise_addr'         => $tarantool_cloud::advertise_addr,
    'ui'                     => true,
    'datacenter'             => $tarantool_cloud::datacenter,
    'log_level'              => 'INFO',
    'retry_join'             => [$tarantool_cloud::bootstrap_address],
    'ca_file'                => "${tarantool_cloud::tls_dir}/ca.pem",
    'cert_file'              => "${tarantool_cloud::tls_dir}/server_cert.pem",
    'key_file'               => "${tarantool_cloud::tls_dir}/server_key.pem",
    'verify_incoming'        => true,
    'verify_outgoing'        => true,
    'verify_server_hostname' => false,
    'encrypt'                => $tarantool_cloud::gossip_key,
    'acl_datacenter'         => $tarantool_cloud::datacenter,
    'acl_master_token'       => $tarantool_cloud::acl_master_token,
    'acl_token'              => 'anonymous',
    'acl_default_policy'     => 'deny',
    'server'                 => true,
    'bootstrap_expect'       => $tarantool_cloud::num_servers
  }

  package { 'unzip':
    ensure => installed,
    name   => 'unzip',
  }

  file { '/etc/systemd/system/consul.service.d':
    ensure => directory
  }
  file { '/etc/systemd/system/consul.service.d/consul-docker.conf':
    content => '[Service]
    EnvironmentFile=-/etc/default/consul_docker'
  }

  file {'/etc/default/consul_docker':
    content => "DOCKER_HOST=tcp://${tarantool_cloud::advertise_addr}:2376
    DOCKER_TLS_VERIFY=1
    DOCKER_CERT_PATH=${tarantool_cloud::tls_dir}"
  }

  class { '::consul':
    config_hash => $config
  }

  consul_acl { 'Consul agent access token':
    ensure        => 'present',
    id            => $tarantool_cloud::acl_token,
    rules         => {
      'service' => {'' => {'policy' => 'write'}},
      'key'     => {'' => {'policy' => 'write'}}},
    type          => 'client',
    acl_api_token => $tarantool_cloud::acl_master_token
  }

  ::consul::service { 'docker':
    checks => [
      {
      script   => "docker -H ${tarantool_cloud::advertise_addr}:2376 --tlsverify info",
      interval => '10s'
      }
    ],
    port   => 2376,
    tags   => ['im'],
    token  => $tarantool_cloud::acl_token
  }
}
