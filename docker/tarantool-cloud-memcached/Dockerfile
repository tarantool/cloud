FROM tarantool/tarantool

RUN mkdir /var/lib/mon.d

COPY tarantool_replication.sh /var/lib/mon.d
COPY tarantool_memory.sh /var/lib/mon.d

COPY app.lua /opt/tarantool

CMD ["tarantool", "/opt/tarantool/app.lua"]
