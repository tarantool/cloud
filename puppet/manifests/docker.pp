# == Class: profiles::docker
#
# Sets up Docker host with TLS auth and exposes an API endpoint on
# 0.0.0.0:2376
#
class tarantool_cloud::docker{
  file {'/etc/systemd/system/docker.service.d/service-env.conf':
    content => '[Service]
    EnvironmentFile=-/etc/default/docker_consul_acl'
  }

  file {'/etc/default/docker_consul_acl':
    content => "CONSUL_HTTP_TOKEN=${tarantool_cloud::acl_token}"
  }
  class { '::docker':
    tcp_bind         => ['tcp://0.0.0.0:2376'],
    tls_enable       => true,
    tls_cacert       => "${tarantool_cloud::tls_dir}/ca.pem",
    tls_cert         => "${tarantool_cloud::tls_dir}/server_cert.pem",
    tls_key          => "${tarantool_cloud::tls_dir}/server_key.pem",
    docker_users     => ['consul'],
    log_driver       => 'fluentd',
    log_opt          => ['fluentd-address=localhost:24224'],
    extra_parameters => "--cluster-store=consul://localhost:8500 \
      --cluster-advertise=${tarantool_cloud::advertise_addr}:2376"
  }


}
