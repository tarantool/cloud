# == Class: profiles::consul::server
#
# Sets up a server instance of Consul. The server participates in
# leader election and can be chosen as leaders.
#
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
  consul_acl { 'Consul agent access token':
    ensure        => 'present',
    id            => $::profiles::consul::acl_token,
    rules         => {
      'service' => {'' => {'policy' => 'write'}},
      'key'     => {'' => {'policy' => 'write'}}},
    type          => 'client',
    acl_api_token => $::profiles::consul::acl_master_token
  }

  ::consul::service { 'docker':
    checks => [
      {
      script   => 'docker info',
      interval => '10s'
      }
    ],
    port   => 2376,
    tags   => ['im'],
    token  => $::profiles::consul::acl_token
  }
}
