FROM alpine:3.4

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
        python-consul \
        python-dateutil \
        gevent flask \
        flask-restful \
        flask-bootstrap \
        flask-basicauth \
    && : "---------- remove build deps ----------" \
    && apk del .build-deps \
    && mkdir /im \
    && mkdir /im/templates

COPY *.py /im/
COPY templates/* /im/templates/

VOLUME /im/config

CMD ["python3", "/im/code/srv.py"]
