# == Class: roles::consul_agent
#
# Sets up Consul in agent mode. See profiles::consul for configuration details.
#
class roles::consul_agent {
  include profiles::tls
  include profiles::consul::agent
}
