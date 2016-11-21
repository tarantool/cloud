# == Class: roles::consul_server
#
# Sets up Consul in server mode. See profiles::consul for configuration details.
#
class roles::consul_server {
  include profiles::tls
  include profiles::consul::server
}
