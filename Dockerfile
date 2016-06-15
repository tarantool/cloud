FROM centos:7

RUN printf '%s\n%s\n%s\n%s\n%s\n%s\n' \
        '[dockerrepo]' \
        'name=Docker Repository' \
        'baseurl=https://yum.dockerproject.org/repo/main/centos/$releasever/' \
        'enabled=1' \
        'gpgcheck=1' \
        'gpgkey=https://yum.dockerproject.org/gpg' > \
        /etc/yum.repos.d/docker.repo \
    && yum -y install docker-engine

RUN rpm -Uvh https://dl.fedoraproject.org/pub/epel/epel-release-latest-7.noarch.rpm


# Tests are written in BATS
RUN curl -fSL https://github.com/sstephenson/bats/archive/v0.4.0.tar.gz -o bats.tar.gz\
    && mkdir -p /usr/src/bats \
    && tar -xzf bats.tar.gz -C /usr/src/bats --strip-components=1 \
    && (cd /usr/src/bats; ./install.sh /usr) \
    && rm -rf /usr/src/bats \
    && rm bats.tar.gz


ENV PYTHON_VERSION 3.5.1
ENV PYTHON_PIP_VERSION 8.1.2
RUN yum -y install gcc make openssl-devel zlib-devel sqlite-devel bzip2-devel
RUN set -ex \
    && curl -fSL "https://www.python.org/ftp/python/${PYTHON_VERSION%%[a-z]*}/Python-$PYTHON_VERSION.tar.xz" -o python.tar.xz \
    && curl -fSL "https://www.python.org/ftp/python/${PYTHON_VERSION%%[a-z]*}/Python-$PYTHON_VERSION.tar.xz.asc" -o python.tar.xz.asc \
    && mkdir -p /usr/src/python \
    && tar -xJC /usr/src/python --strip-components=1 -f python.tar.xz \
    && rm python.tar.xz \
    \
    && cd /usr/src/python \
    && ./configure --enable-shared --enable-unicode=ucs4 \
       --prefix=/usr/local LDFLAGS="-Wl,-rpath /usr/local/lib" \
    && make -j$(nproc) \
    && make altinstall \
    && ldconfig \
    && ln -s /usr/local/bin/python3.5 /usr/local/bin/python3 \
    && pip3.5 install --no-cache-dir --upgrade --ignore-installed pip==$PYTHON_PIP_VERSION \
    && rm -rf /usr/src/python ~/.cache



RUN pip3 install tarantool ipaddress docker-py python-consul

ADD . /opt/tarantool/cloud
WORKDIR /opt/tarantool/cloud

CMD ["/opt/tarantool/cloud/cli.py", "watch"]
