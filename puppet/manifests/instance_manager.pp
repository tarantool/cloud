# == Class: profiles::instance_manager
#
# Runs tarantool cloud Instance Manager in a Docker container and
# exposes it on port 5061.
#
class tarantool_cloud::instance_manager{
  include docker

  file { '/etc/im':
    ensure => 'directory',
  }

  $config = "
---
CONSUL_HOST: ${tarantool_cloud::advertise_addr}
LISTEN_PORT: 8080
DOCKER_CLIENT_KEY: /tls/key.pem
DOCKER_CLIENT_CERT: /tls/cert.pem
DOCKER_SERVER_CERT: /tls/ca.pem
CONSUL_ACL_TOKEN: ${tarantool_cloud::acl_token}
  "

  file { '/etc/im/config.yml':
    content => $config
  }



  docker::image { 'tarantool/cloud':
    image_tag => 'latest'
  }
  docker::run { 'instance_manager':
    image            => 'tarantool/cloud',
    volumes          => [
      "${tarantool_cloud::tls_dir}:/tls:ro",
      '/etc/im:/im/config:ro'],
    ports            => ['5061:8080'],
    extra_parameters => [ '--restart=always' ],
    command          => 'python3 /im/srv.py -c /im/config/config.yml'
  }
}
