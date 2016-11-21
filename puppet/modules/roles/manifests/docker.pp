# == Class: roles::docker
#
# Sets up Docker host with TLS auth.
#
class roles::docker {
  include profiles::tls
  include profiles::docker
}
