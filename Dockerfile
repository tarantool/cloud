FROM alpine:3.5

ENV PYTHONUNBUFFERED=1

RUN set -x \
    && apk add --no-cache --virtual .run-deps \
        python3 \
        libffi \
        openssl \
        ca-certificates \
    && apk add --no-cache --virtual .build-deps \
        python3-dev \
        musl-dev \
        gcc \
        libffi-dev \
        openssl-dev \
        make \
    && pip3 install --upgrade pip \
    && pip3 install \
        tarantool \
        ipaddress \
        docker-py \
        python-consul \
        python-dateutil \
        gevent flask \
        flask-restful \
        flask-bootstrap \
        flask-basicauth \
        fabric3 \
    && : "---------- remove build deps ----------" \
    && apk del .build-deps \
    && mkdir /im \
    && mkdir /im/templates \
    && mkdir /im/docker

COPY *.py /im/
COPY templates/ /im/templates/
COPY docker/ /im/docker/

VOLUME /im/config
WORKDIR /im

CMD ["python3", "/im/srv.py"]
