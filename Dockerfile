FROM alpine:3.4

RUN apk add --no-cache python3 python3-dev musl-dev gcc
RUN pip3 install tarantool ipaddress docker-py python-consul python-dateutil gevent flask flask-restful flask-bootstrap flask-basicauth

RUN mkdir /im

COPY *.py /im/
COPY templates /im/

VOLUME /im/config

CMD ["python3", "/im/code/srv.py"]
