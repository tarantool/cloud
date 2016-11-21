# == Class: profiles::docker
#
# Sets up Docker host with TLS auth and exposes an API endpoint on
# 0.0.0.0:2376
#
# === Parameters
#
# [*tls_dir*]
#   Place where TLS certificates are located. Do not change unless you've
#   generated them by hand. tls.pp provides a facility to automatically
#   generate the certificates
#
class profiles::docker(
  $tls_dir = '/etc/tarantool_cloud/tls'
) {
  $advertise_addr = $::external_ip

  class { '::docker':
    tcp_bind         => ['tcp://0.0.0.0:2376'],
    tls_enable       => true,
    tls_cacert       => "${tls_dir}/ca.crt",
    tls_cert         => "${tls_dir}/server.crt",
    tls_key          => "${tls_dir}/server.key",
    docker_users     => ['consul'],
    extra_parameters => "--cluster-store=consul://localhost:8500 --cluster-advertise=${advertise_addr}:2376"
  }
}
