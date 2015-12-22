FROM tarantool/build:el7

# add repo
curl -s https://packagecloud.io/install/repositories/tarantool/1_6/script.rpm.sh | bash
yum install -y tarantool tarantool-dev 

# expose memcached port
EXPOSE 3301

# load lua script
ADD app.lua /var/lib/tarantool/
RUN chown -R tarantool:tarantool /var/lib/tarantool
USER tarantool
WORKDIR /var/lib/tarantool/
CMD ./app.lua
