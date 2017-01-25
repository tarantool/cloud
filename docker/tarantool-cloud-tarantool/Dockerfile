FROM tarantool/tarantool:1.7

RUN mkdir /var/lib/mon.d \
    && mkdir -p /opt/deploy/initial \
    && rm -rf /opt/tarantool \
    && ln -s /opt/deploy/initial /opt/tarantool

COPY tarantool_replication.sh /var/lib/mon.d
COPY tarantool_memory.sh /var/lib/mon.d

COPY app.lua /usr/local/bin/app_launcher.lua

VOLUME /opt/deploy

EXPOSE 3301

CMD ["tarantool", "/usr/local/bin/app_launcher.lua"]
