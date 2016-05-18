#!/bin/bash

sudo tee /etc/yum.repos.d/docker.repo <<-'EOF'
[dockerrepo]
name=Docker Repository
baseurl=https://yum.dockerproject.org/repo/main/centos/$releasever/
enabled=1
gpgcheck=1
gpgkey=https://yum.dockerproject.org/gpg
EOF

sudo yum -y install docker-engine

sudo mkdir -p /etc/systemd/system/docker.service.d
sudo tee /etc/systemd/system/docker.service.d/docker.conf <<-'EOF'
[Service]
ExecStart=
ExecStart=/usr/bin/docker daemon -H fd:// -H tcp://0.0.0.0:2375
EOF

sudo systemctl enable docker
sudo systemctl restart docker

MY_IP=$(hostname -I | cut -d' ' -f2)

sudo docker pull consul
sudo docker pull swarm

sudo docker stop consul_server
sudo docker rm consul_server


sudo docker run -d --net=host -e \
       'CONSUL_LOCAL_CONFIG={"skip_leave_on_interrupt": true}'\
       --name consul_server\
       consul agent -server -bootstrap-expect=3\
       -advertise=$MY_IP\
       -ui\
       -client 0.0.0.0\
       -retry-join=172.20.20.10\
       -retry-join=172.20.20.20\
       -retry-join=172.20.20.30

sudo docker stop swarm_server
sudo docker rm swarm_server

sudo docker run -d -p 4000:4000 \
     --name swarm_server\
     swarm manage -H :4000 \
     --replication \
     --advertise $MY_IP:4000\
     consul://$MY_IP:8500

sudo docker stop swarm_node
sudo docker rm swarm_node

docker run -d --name swarm_node swarm join \
       --advertise=$MY_IP:2375 consul://$MY_IP:8500
