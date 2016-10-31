FROM tarantool/tarantool

RUN mkdir /var/lib/mon.d

COPY tarantool_replication.sh /var/lib/mon.d
COPY tarantool_memory.sh /var/lib/mon.d
COPY tarantool-memcached.conf /etc/sasl2/tarantool-memcached.conf

COPY app.lua /opt/tarantool

CMD ["tarantool", "/opt/tarantool/app.lua"]
