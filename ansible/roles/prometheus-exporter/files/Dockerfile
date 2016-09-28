FROM nginx:1.11.3

RUN apt-get update \
 && apt-get install -y -q --no-install-recommends \
    ca-certificates \
    openssl \
    wget \
 && apt-get clean \
 && rm -r /var/lib/apt/lists/*

ADD https://github.com/jwilder/forego/releases/download/v0.16.1/forego /usr/local/bin/forego
RUN chmod u+x /usr/local/bin/forego

ADD https://github.com/prometheus/node_exporter/releases/download/0.12.0/node_exporter-0.12.0.linux-amd64.tar.gz /node_exporter.tar.gz

RUN set -e \
    && tar -xvf /node_exporter.tar.gz \
    && mv /node_exporter-0.12.0.linux-amd64/node_exporter /bin/ \
    && rm -rf /node_exporter* \
    && chmod a+x /bin/node_exporter

VOLUME /host/proc
VOLUME /host/sys

COPY Procfile /app/Procfile
WORKDIR /app/

COPY default.conf /etc/nginx/conf.d/default.conf
RUN echo "daemon off;" >> /etc/nginx/nginx.conf

COPY docker-entrypoint.sh /usr/local/bin/
RUN chmod a+x /usr/local/bin/docker-entrypoint.sh
RUN ln -s /usr/local/bin/docker-entrypoint.sh /entrypoint.sh # backwards compat
ENTRYPOINT ["docker-entrypoint.sh"]

EXPOSE 9100
CMD ["forego", "start", "-r"]
