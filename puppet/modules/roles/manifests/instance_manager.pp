# == Class: roles::instance_manager
#
# Runs tarantool cloud Instance Manager in a Docker container.
#
class roles::instance_manager {
  include profiles::tls
  include profiles::instance_manager
}
