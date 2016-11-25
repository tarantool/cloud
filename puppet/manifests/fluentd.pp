# == Class: tarantool_cloud::fluentd
#
# Installs and configures td-agent (fluentd)
#
class tarantool_cloud::fluentd {
  include fluentd

  if $::osfamily == 'debian' {
    Apt::Source[$fluentd::repo_name] -> Class['apt::update'] -> Package[$fluentd::package_name]
  }

  fluentd::plugin { 'fluent-plugin-elasticsearch': }

  if $tarantool_cloud::elasticsearch {
    $store = {
      'logstash_format' => true,
      'type'            => 'elasticsearch',
      'logstash_prefix' => $tarantool_cloud::logstash_prefix,
      'host'            => $tarantool_cloud::elasticsearch_host,
      'port'            => $tarantool_cloud::elasticsearch_port,
      'index_name'      => $tarantool_cloud::elasticsearch_index,
      'type_name'       => $tarantool_cloud::elasticsearch_type
    }
  }
  else {
    $store = {
      'type'       => 'stdout'
    }
  }


  fluentd::config { '500_elasticsearch.conf':
    config => {
      'source' => [
        {
        'type' => 'forward',
        'port' => 24224,
        'bind' => '127.0.0.1'
        }
      ],
      'filter' => {
          'tag_pattern' => '**',
          'type'        => 'record_transformer',
          'record'      => {'hostname'=> '${hostname}'}
      },
      'match'  => {
        'tag_pattern' => '**',
        'type'        => 'copy',
        'store'       => [
          $store,
          {
          'type' => 'file',
          'path' => '/var/log/td-agent/docker'
          }]
      }
    }
  }
}
