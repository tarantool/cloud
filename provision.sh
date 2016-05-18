#!/bin/bash

sudo tee /etc/yum.repos.d/docker.repo <<-'EOF'
[dockerrepo]
name=Docker Repository
baseurl=https://yum.dockerproject.org/repo/main/centos/$releasever/
enabled=1
gpgcheck=1
gpgkey=https://yum.dockerproject.org/gpg
EOF

sudo systemctl enable docker
sudo systemctl restart docker

sudo yum -y install docker-engine

sudo docker pull consul

sudo docker stop consul_server
sudo docker rm consul_server
sudo docker run -d --net=host -e \
       'CONSUL_LOCAL_CONFIG={"skip_leave_on_interrupt": true}'\
       --name consul_server\
       consul agent -server -bootstrap-expect=3\
       -advertise=`hostname -I | cut -d' ' -f2`\
       -ui\
       -client 0.0.0.0\
       -retry-join=172.20.20.10\
       -retry-join=172.20.20.20\
       -retry-join=172.20.20.30
