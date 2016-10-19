FROM alpine:3.4

ENV PYTHONUNBUFFERED=1

RUN set -x \
    && apk add --no-cache --virtual .run-deps \
        python3 \
    && apk add --no-cache --virtual .build-deps \
        python3-dev \
        musl-dev \
        gcc \
    && pip3 install \
        tarantool \
        ipaddress \
        docker-py \
        "python-consul==0.6.1" \
        python-dateutil \
        gevent flask \
        flask-restful \
        flask-bootstrap \
        flask-basicauth \
    && : "---------- remove build deps ----------" \
    && apk del .build-deps \
    && mkdir /im \
    && mkdir /im/templates \
    && mkdir /im/docker

COPY python_consul_token.patch /
RUN set -x \
    && cd /usr/lib/python3.5/site-packages \
    && patch -p1 < /python_consul_token.patch \
    && rm /python_consul_token.patch


COPY *.py /im/
COPY templates/ /im/templates/
COPY docker/ /im/docker/

VOLUME /im/config
WORKDIR /im

CMD ["python3", "/im/srv.py"]
