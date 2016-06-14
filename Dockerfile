FROM centos:7

RUN yum -y install python

RUN printf '%s\n%s\n%s\n%s\n%s\n%s\n%s\n' \
         '[tarantool_1_6]' \
         'name=EnterpriseLinux-$releasever - Tarantool' \
         'baseurl=http://download.tarantool.org/tarantool/1.6/el/7/$basearch/' \
         'gpgkey=http://download.tarantool.org/tarantool/1.6/gpgkey' \
         'repo_gpgcheck=1' \
         'gpgcheck=0' \
         'enabled=1' > \
         /etc/yum.repos.d/tarantool_1_6.repo

RUN rpm -Uvh https://dl.fedoraproject.org/pub/epel/epel-release-latest-7.noarch.rpm
RUN yum -y install python-pip



RUN pip install tarantool ipaddress docker-py python-consul

ADD . /opt/tarantool/cloud

CMD ["/opt/tarantool/cloud/cli.py", "watch"]
