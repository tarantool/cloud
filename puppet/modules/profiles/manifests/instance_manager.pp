class profiles::instance_manager {
  include docker

  $tls_dir = '/etc/tarantool_cloud/tls'
  $acl_token = hiera('private::tarantool_cloud::consul::acl_token')
  $advertise_addr = "${::external_ip}"


  file { '/etc/im':
    ensure => 'directory',
  }

  $config = "
---
CONSUL_HOST: ${advertise_addr}
LISTEN_PORT: 8080
DOCKER_CLIENT_KEY: /tls/client.key
DOCKER_CLIENT_CERT: /tls/client.crt
DOCKER_SERVER_CERT: /tls/ca.crt
CONSUL_ACL_TOKEN: ${acl_token}
  "

  file { '/etc/im/config.yml':
    content => $config
  }



  docker::image { 'tarantool/cloud':
    image_tag => 'latest'
  }
  docker::run { 'instance_manager':
    image   => 'tarantool/cloud',
    volumes => ["${tls_dir}:/tls:ro",
                "/etc/im:/im/config:ro"],
    ports => ['5061:8080'],
    extra_parameters => [ '--restart=always' ],
    command => "python3 /im/srv.py -c /im/config/config.yml"
  }
}
