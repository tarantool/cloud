$tls_dir = '/etc/tarantool_cloud/tls'

# CA generator and its files live on puppet master
$ca_generator = '/opt/tarantool_cloud/ca.py'
$ca_dir = '/var/tarantool_cloud/ca'


class { "docker":
  tcp_bind        => ['tcp://0.0.0.0:2376'],
  tls_enable      => true,
  tls_cacert      => "${tls_dir}/ca.crt",
  tls_cert        => "${tls_dir}/server.crt",
  tls_key         => "${tls_dir}/server.key",
}

include docker

$server_fqdn = 'myhost.com'
$altnames = ['foo', '127.0.0.1', 'bar']
$altnames_str = join($altnames, ' ')

exec { "Create '${tls_dir}'":
  creates => $tls_dir,
  command => "mkdir -p '${tls_dir}'",
  path => $::path
  } -> file { $tls_dir : }

file { "$tls_dir/ca.crt":
    ensure => file,
    content => generate($ca_generator, "-d", $ca_dir, 'ca', '--cert')
}

file { "$tls_dir/server.key":
  ensure => file,
  content => generate($ca_generator, "-d", $ca_dir, 'server', '--key', $server_fqdn, $altnames_str)
}

file { "$tls_dir/server.crt":
  ensure => file,
  content => generate($ca_generator, '-d', $ca_dir, 'server', '--cert', $server_fqdn, $altnames_str)
}

file { "$tls_dir/client.key":
  ensure => file,
  content => generate($ca_generator, "-d", $ca_dir, 'client', '--key')
}

file { "$tls_dir/client.crt":
  ensure => file,
  content => generate($ca_generator, '-d', $ca_dir, 'client', '--cert')
}


docker::image { 'alpine': }
