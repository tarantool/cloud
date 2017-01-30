# == Class: profiles::tls
#
# Generates TLS certificates for the current node.
# The purpose is to satisfy both Docker and Consul authentication,
# so it has a few interesting bits:
#
# * client keys are created with 'extendedKeyUsage = clientAuth'
# * server keys are created with 'extendedKeyUsage = serverAuth, clientAuth'
# * all server keys contain <hostname>.<datacenter>.consul altname
# * all server keys include all their IP addresses in altnames
#
# All this is required to make encryption work properly. If you still want
# to generate TLS certs yourself, study the code of ca.py in the cloud/ repo.
#
class tarantool_cloud::tls {
  $ca_generator = $tarantool_cloud::ca_generator
  $ca_dir = $tarantool_cloud::ca_dir
  $tls_dir = $tarantool_cloud::tls_dir
  $datacenter = $tarantool_cloud::datacenter
  $interface_names = split($::interfaces, ',')
  $interface_ips = $interface_names.map |$ifname| {
    getvar("ipaddress_${ifname}")
  }
  # this hostname will be used as subjectName in TLS certificates
  $server_hostname = $::hostname
  $altnames = concat([$::fqdn,
    "${::hostname}.${datacenter}.consul"],
    $interface_ips)

  $altnames_str = join($altnames, ' ')

  exec { "Create '${tls_dir}'":
    creates => $tls_dir,
    command => "mkdir -p '${tls_dir}'",
    path    => $::path
    } -> file { $tls_dir : }

    if ($tarantool_cloud::ca_cert == undef)
    {
      file { "${tls_dir}/ca.pem":
        ensure  => file,
        content => generate($ca_generator, '-d', $ca_dir, 'ca', '--cert')
      }
    }
    else
    {
      file { "${tls_dir}/ca.pem":
        ensure => file,
        source => $tarantool_cloud::ca_cert
      }
    }

    if ($tarantool_cloud::server_key == undef)
    {
      file { "${tls_dir}/server_key.pem":
        ensure  => file,
        content => generate($ca_generator, '-d', $ca_dir, 'server', '--key',
        $server_hostname, $altnames_str)
      }
    }
    else
    {
      file { "${tls_dir}/server_key.pem":
        ensure => file,
        source => $tarantool_cloud::server_key
      }
    }

    if ($tarantool_cloud::server_cert == undef)
    {
      file { "${tls_dir}/server_cert.pem":
        ensure  => file,
        content => generate($ca_generator, '-d', $ca_dir, 'server', '--cert',
        $server_hostname, $altnames_str)
      }
    }
    else
    {
      file { "${tls_dir}/server_cert.pem":
        ensure => file,
        source => $tarantool_cloud::server_cert
      }
    }

    if ($tarantool_cloud::client_key == undef)
    {
      file { "${tls_dir}/key.pem":
        ensure  => file,
        content => generate($ca_generator, '-d', $ca_dir, 'client', '--key')
      }
    }
    else
    {
      file { "${tls_dir}/key.pem":
        ensure => file,
        source => $tarantool_cloud::client_key
      }
    }

    if ($tarantool_cloud::client_cert == undef)
    {
      file { "${tls_dir}/cert.pem":
        ensure  => file,
        content => generate($ca_generator, '-d', $ca_dir, 'client', '--cert')
      }
    }
    else
    {
      file { "${tls_dir}/cert.pem":
        ensure => file,
        source => $tarantool_cloud::client_cert
      }
    }
}
