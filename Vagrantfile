# -*- mode: ruby -*-
# vi: set ft=ruby :

Vagrant.configure(2) do |config|
  config.vm.box = 'bento/centos-7.2'

  config.vm.provider 'parallels' do |prl|
    prl.update_guest_tools = true
  end

  config.vm.define 'node1' do |node|
    config.vm.provision 'shell', path: 'provision.sh'

    node.vm.hostname = 'node1'
    node.vm.network 'private_network', ip: '172.20.20.10'
  end

  config.vm.define 'node2' do |node|
    config.vm.provision 'shell', path: 'provision.sh'

    node.vm.hostname = 'node2'
    node.vm.network 'private_network', ip: '172.20.20.20'
  end

  config.vm.define 'node3' do |node|
    config.vm.provision 'shell', path: 'provision.sh'

    node.vm.hostname = 'node3'
    node.vm.network 'private_network', ip: '172.20.20.30'
  end
end
