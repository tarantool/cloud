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
# === Parameters
#
# [*ca_generator*]
#   Full path to the 'ca.py' scrip on puppet master. This script generates
#   TLS certificates.
#
# [*ca_dir*]
#   Path to the directory on puppet master where TLS certificates will be
#   stored. The user under which puppet muster runs, must have write
#   access to this directory
#
# [*tls_dir*]
#   Place where TLS certificates are located. Do not change unless you've
#   generated them by hand.
#
# [*datacenter*]
#   datacenter name participates in TLS cert generation for servers. This
#   must be the same as consul datacenter name set in
#   profiles::consul:datacenter
#
class profiles::tls(
  $ca_generator = '/opt/tarantool_cloud/ca.py',
  $ca_dir = '/var/tarantool_cloud/ca',
  $tls_dir = '/etc/tarantool_cloud/tls',
  $datacenter = hiera('profiles::consul::datacenter')
) {
  $server_fqdn = $::hostname
  $interface_names = split($::interfaces, ',')
  $interface_ips = $interface_names.map |$ifname| {
    getvar("ipaddress_${ifname}")
  }
  $altnames = concat([$::fqdn,
    "${::hostname}.${datacenter}.consul"],
    $interface_ips)

  $altnames_str = join($altnames, ' ')

  exec { "Create '${tls_dir}'":
    creates => $tls_dir,
    command => "mkdir -p '${tls_dir}'",
    path    => $::path
    } -> file { $tls_dir : }

    file { "${tls_dir}/ca.crt":
      ensure  => file,
      content => generate($ca_generator, '-d', $ca_dir, 'ca', '--cert')
    }

    file { "${tls_dir}/server.key":
      ensure  => file,
      content => generate($ca_generator, '-d', $ca_dir, 'server', '--key',
      $server_fqdn, $altnames_str)
    }

    file { "${tls_dir}/server.crt":
      ensure  => file,
      content => generate($ca_generator, '-d', $ca_dir, 'server', '--cert',
      $server_fqdn, $altnames_str)
    }

    file { "${tls_dir}/client.key":
      ensure  => file,
      content => generate($ca_generator, '-d', $ca_dir, 'client', '--key')
    }

    file { "${tls_dir}/client.crt":
      ensure  => file,
      content => generate($ca_generator, '-d', $ca_dir, 'client', '--cert')
    }
}
