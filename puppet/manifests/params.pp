# == Class: tarantool_cloud::params
#
# Default parameter values for the tarantool_cloud module
#
class tarantool_cloud::params {
  $datacenter          = 'dc1'
  $bootstrap_address   = undef
  $gossip_key          = undef
  $acl_master_token    = undef
  $acl_token           = undef
  $num_servers         = undef
  $advertise_addr      = undef
  $agent               = false
  $instance_manager    = false
  $tls_dir             = '/etc/tarantool_cloud/tls'
  $ca_generator        = '/opt/tarantool_cloud/ca.py'
  $ca_dir              = '/var/tarantool_cloud/ca'
  $consul_data_dir     = '/var/lib/consul'
  $elasticsearch       = false
  $elasticsearch_host  = undef
  $elasticsearch_port  = 9200
  $elasticsearch_index = 'fluentd'
  $elasticsearch_type  = 'fluentd'
  $ca_cert             = undef
  $server_cert         = undef
  $server_key          = undef
  $client_cert         = undef
  $client_key          = undef
}
