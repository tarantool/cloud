class profiles::tls {
  $tls_dir = '/etc/tarantool_cloud/tls'
  $datacenter = hiera('private::tarantool_cloud::consul::datacenter')

  # CA generator and its files live on puppet master
  $ca_generator = '/opt/tarantool_cloud/ca.py'
  $ca_dir = '/var/tarantool_cloud/ca'

  $server_fqdn = $::hostname
  $interface_names = split($::interfaces, ',')
  $interface_ips = $interface_names.map |$ifname| {
    getvar("ipaddress_${ifname}")
  }
  $altnames = concat([$::fqdn,
    "${::hostname}.${datacenter}.consul"],
    $interface_ips)

  $altnames_str = join($altnames, ' ')

  notice("hostname: ${server_fqdn}")
  notice("altnames: ${altnames_str}")

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
      content => generate($ca_generator, "-d", $ca_dir, 'server', '--key',
      $server_fqdn, $altnames_str)
    }

    file { "$tls_dir/server.crt":
      ensure => file,
      content => generate($ca_generator, '-d', $ca_dir, 'server', '--cert',
      $server_fqdn, $altnames_str)
    }

    file { "$tls_dir/client.key":
      ensure => file,
      content => generate($ca_generator, "-d", $ca_dir, 'client', '--key')
    }

    file { "$tls_dir/client.crt":
      ensure => file,
      content => generate($ca_generator, '-d', $ca_dir, 'client', '--cert')
    }
}
