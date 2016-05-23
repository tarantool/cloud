#!/bin/bash

MY_IP=$(hostname -I | cut -d' ' -f2)

PEERS="172.20.20.10 172.20.20.20 172.20.20.30"

sudo tee /etc/yum.repos.d/docker.repo <<-'EOF'
[dockerrepo]
name=Docker Repository
baseurl=https://yum.dockerproject.org/repo/main/centos/$releasever/
enabled=1
gpgcheck=1
gpgkey=https://yum.dockerproject.org/gpg
EOF

if ! rpm -q --quiet docker-engine; then
   sudo yum -y install docker-engine
fi

if [ ! -f /usr/bin/weave ]; then
    sudo curl -L git.io/weave -o /usr/bin/weave
fi

sudo chmod a+x /usr/bin/weave


sudo mkdir -p /etc/systemd/system/docker.service.d
sudo tee /etc/systemd/system/docker.service.d/docker.conf <<-EOF
[Service]
ExecStart=
ExecStart=/usr/bin/docker daemon -H fd:// -H tcp://0.0.0.0:2375 --cluster-advertise="$MY_IP:8500" --cluster-store="consul://$MY_IP:8500"
EOF

mkdir -p /opt/tarantool_cloud
cp /vagrant/docker_wrapper.sh /opt/tarantool_cloud/docker_wrapper.sh
cp /vagrant/systemd/consul.service /etc/systemd/system/consul.service
cp /vagrant/systemd/weave.service /etc/systemd/system/weave.service
cp /vagrant/systemd/weaveproxy.service /etc/systemd/system/weaveproxy.service
cp /vagrant/systemd/swarm.service /etc/systemd/system/swarm.service
cp /vagrant/systemd/swarm_client.service /etc/systemd/system/swarm_client.service

sudo tee /etc/consul.env <<-EOF
OPTIONS=-server -bootstrap-expect=3\
       -advertise=$MY_IP\
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
SWARM_CLIENT_OPTIONS=-advertise=$MY_IP:12375\
        consul://$MY_IP:8500
EOF

sudo tee /etc/weave.env <<-EOF
WEAVE_ROUTER_ARGS=--ipalloc-range 172.21.0.0/16
WEAVE_PROXY_ARGS=-H tcp://0.0.0.0:12375
PEERS=172.20.20.10 172.20.20.20 172.20.20.30
EOF


sudo systemctl daemon-reload

sudo systemctl enable docker
sudo systemctl enable consul
sudo systemctl enable weave
sudo systemctl enable weaveproxy
sudo systemctl enable swarm
sudo systemctl enable swarm_client

sudo systemctl restart docker
sudo systemctl restart consul
sudo systemctl restart weave
sudo systemctl restart weaveproxy
sudo systemctl restart swarm
sudo systemctl restart swarm_client
