#!/bin/bash

MY_IP=$(hostname -I | cut -d' ' -f2)

PEERS="172.20.20.10 172.20.20.20 172.20.20.30"

sudo tee /etc/yum.repos.d/docker.repo <<-'EOF'
[dockerrepo]
name=Docker Repository
# Docker experimental is required to support macvlan network driver
baseurl=https://yum.dockerproject.org/repo/experimental/centos/$releasever/
enabled=1
gpgcheck=1
gpgkey=https://yum.dockerproject.org/gpg
EOF

if ! rpm -q --quiet docker-engine; then
   sudo yum -y install docker-engine
fi

sudo mkdir -p /etc/systemd/system/docker.service.d
sudo tee /etc/systemd/system/docker.service.d/docker.conf <<-EOF
[Service]
ExecStart=
ExecStart=/usr/bin/docker daemon -H fd:// -H tcp://0.0.0.0:2375
EOF

mkdir -p /opt/tarantool_cloud
cp /vagrant/docker_wrapper.sh /opt/tarantool_cloud/docker_wrapper.sh
cp -r /vagrant/consul.d /opt/tarantool_cloud
cp /vagrant/app.lua /opt/tarantool_cloud/app.lua
cp -r /vagrant/mon.d /opt/tarantool_cloud/mon.d

cp /vagrant/systemd/consul.service /etc/systemd/system/consul.service
cp /vagrant/systemd/macvlan-settings.service /etc/systemd/system/macvlan-settings.service

sudo tee /etc/consul.env <<-EOF
DOCKER_HOST=localhost:2375
OPTIONS=-server -bootstrap-expect=3\
       -advertise=$MY_IP\
       -log-level=debug\
       -ui\
       -client 0.0.0.0\
       -retry-join=172.20.20.10\
       -retry-join=172.20.20.20\
       -retry-join=172.20.20.30\
       -bind $MY_IP
EOF

sudo tee /etc/swarm.env <<-EOF
PORT_MAP=-p 4000:4000
SWARM_SERVER_OPTIONS=-H :4000 \
     --replication \
     --advertise $MY_IP:4000\
     consul://$MY_IP:8500
SWARM_CLIENT_OPTIONS=-advertise=$MY_IP:2375\
        consul://$MY_IP:8500
EOF

sudo tee /etc/macvlan-settings.env <<-EOF
INTERFACE=eth1
EOF

sudo systemctl daemon-reload

sudo systemctl enable docker
sudo systemctl enable consul
sudo systemctl enable macvlan-settings

sudo systemctl start docker
sudo systemctl restart consul
sudo systemctl restart macvlan-settings

if ! docker network inspect macvlan 2>/dev/null >/dev/null; then
    docker network create -d macvlan --subnet=172.20.20.0/24 --gateway=172.20.20.1 --ip-range=172.20.20.128/25 -o parent=eth1 -o macvlan_mode=bridge macvlan
fi
