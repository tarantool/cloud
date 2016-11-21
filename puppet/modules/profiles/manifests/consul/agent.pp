# == Class: profiles::consul::agent
#
# Sets up an agent instance of Consul. The agent actively participates only
# in gossip traffic exchange. It can't be chosen as leader and doesn't
# participate in voting.
#
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
