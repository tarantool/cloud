class roles::consul_server {
  include profiles::tls
  include profiles::consul::server
}
