FROM centos:centos7

# add repo
RUN curl -s https://packagecloud.io/install/repositories/tarantool/1_6/script.rpm.sh | bash
RUN yum install -y tarantool tarantool-dev tarantool-memcached

# expose memcached and admin ports
EXPOSE 3301
EXPOSE 3302

# load lua script
ADD app.lua /var/lib/tarantool/
RUN chown -R tarantool:tarantool /var/lib/tarantool
USER tarantool
WORKDIR /var/lib/tarantool/
CMD tarantool app.lua
