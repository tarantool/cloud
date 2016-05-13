# -*- mode: ruby -*-
Vagrant.configure(2) do |config|
  config.vm.box = 'bento/centos-7.2'

  config.vm.synced_folder '.', '/opt/tarantool/cloud'

  config.vm.provision 'ansible' do |ansible|
    ansible.playbook = 'deploy/site.yml'

    ansible.extra_vars = {
      'localdeploy' => true
    }
  end
end
