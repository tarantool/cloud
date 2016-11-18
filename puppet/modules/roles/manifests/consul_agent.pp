class roles::consul_agent {
  include profiles::tls
  include profiles::consul::agent
}
