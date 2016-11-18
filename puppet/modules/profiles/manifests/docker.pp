class profiles::docker {
  $tls_dir = '/etc/tarantool_cloud/tls'
  $advertise_addr = "${::external_ip}"

  class { "::docker":
    tcp_bind        => ['tcp://0.0.0.0:2376'],
    tls_enable      => true,
    tls_cacert      => "${tls_dir}/ca.crt",
    tls_cert        => "${tls_dir}/server.crt",
    tls_key         => "${tls_dir}/server.key",
    docker_users    => ['consul'],
    extra_parameters => "--cluster-store=consul://localhost:8500 --cluster-advertise=${advertise_addr}:2376"
  }
}
