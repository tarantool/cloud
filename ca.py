#!/usr/bin/env python3

""" Generate certificates for Docker and Consul TLS auth.

This module allows you to maintain a simple CA and issue TLS
certificates for both Consul and Docker. In case of Tarantool
Cloud, Docker and Consul are two primary building blocks that
are exposed to internal network and as such can't usually be
left unsecured.

Dependencies: command line 'openssl' tool.

There are 2 different use cases: command line and Python API.

Command Line:
  Used by tools like puppet or other provisioners to prepare
  physical machines.

  Usage:

    python ca.py ca

    python ca.py client

    python ca.py server <fqdn> [altname1, altname2]

Python API:
  Used by python-based provisioners (either ansible or hand-rolled).
  See function docstrings below. The usage should be pretty obvious.
"""
from __future__ import print_function

import subprocess
import shlex
import os
import sys
import uuid
import socket
import argparse
import logging

def check_output(*popenargs, **kwargs):
    if 'stdout' in kwargs:
        raise ValueError('stdout argument not allowed, it will be overridden.')
    if 'stderr' in kwargs:
        raise ValueError('stderr argument not allowed, it will be overridden.')

    process = subprocess.Popen(stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               *popenargs, **kwargs)
    res = process.communicate()
    output = res[0]
    error = res[1]
    retcode = process.poll()
    if retcode:
        cmd = kwargs.get("args")
        if cmd is None:
            cmd = popenargs[0]
        ex = subprocess.CalledProcessError(retcode, cmd)
        # on Python 2.6 and older CalledProcessError does not accept 'output' argument
        ex.output = output
        ex.stderr = error
        raise ex
    return output


def is_key_encrypted(key):
    for line in key:
        if 'Proc-Type:' in line and 'ENCRYPTED' in line:
            return True
    return False


def is_ip_addr(addr_str):
    """Returns True if addr_str is a valid ipv4 or ipv6 address"""

    try:
        socket.inet_pton(socket.AF_INET, addr_str)
        return True
    except socket.error:
        pass

    try:
        socket.inet_pton(socket.AF_INET6, addr_str)
        return True
    except socket.error:
        pass

    return False


def generate_ca_private_key(password):
    password_in_fd, password_out_fd = os.pipe()
    try:
        os.write(password_out_fd, password.encode('utf-8'))
        os.close(password_out_fd)

        cmd = 'openssl genrsa -aes256 -passout fd:%d 4096' % \
              password_in_fd
        logging.info(cmd)

        args = {}
        if sys.version_info >= (3, 2):
            args = {'pass_fds': (password_in_fd,)}

        out = check_output(shlex.split(cmd), **args)
    finally:
        os.close(password_in_fd)

    return out.decode('utf-8')


def generate_ca_certificate(private_key, password, common_name):
    password_in_fd, password_out_fd = os.pipe()
    key_in_fd, key_out_fd = os.pipe()

    try:
        os.write(password_out_fd, password.encode('utf-8'))
        os.close(password_out_fd)
        os.write(key_out_fd, private_key.encode('utf-8'))
        os.close(key_out_fd)

        cmd = ('openssl req -new -x509 -days 3650 -key /dev/fd/%s -sha256 ' +
               '-passin fd:%d -subj "/CN=%s"') % \
            (key_in_fd, password_in_fd, common_name)

        logging.info(cmd)

        args = {}
        if sys.version_info >= (3, 2):
            args = {'pass_fds': (password_in_fd, key_in_fd)}

        out = check_output(shlex.split(cmd), **args)
    finally:
        os.close(password_in_fd)
        os.close(key_in_fd)

    return out.decode('utf-8')


def generate_client_key():
    cmd = 'openssl genrsa 4096'

    logging.info(cmd)

    out = check_output(shlex.split(cmd))

    return out.decode('utf-8')


def generate_client_csr(client_key):
    key_in_fd, key_out_fd = os.pipe()

    try:
        os.write(key_out_fd, client_key.encode('utf-8'))
        os.close(key_out_fd)

        cmd = 'openssl req -subj "/CN=client" -new -key /dev/fd/%d' % key_in_fd

        logging.info(cmd)

        args = {}
        if sys.version_info >= (3, 2):
            args = {'pass_fds': (key_in_fd,)}

        out = check_output(shlex.split(cmd), **args)
    finally:
        os.close(key_in_fd)

    return out.decode('utf-8')


def sign_client_cert(ca_cert, ca_key, password, client_csr):
    extfile = 'extendedKeyUsage = clientAuth\n'

    extfile_in_fd, extfile_out_fd = os.pipe()
    ca_cert_in_fd, ca_cert_out_fd = os.pipe()
    ca_key_in_fd, ca_key_out_fd = os.pipe()
    password_in_fd, password_out_fd = os.pipe()
    csr_in_fd, csr_out_fd = os.pipe()

    try:
        os.write(extfile_out_fd, extfile.encode('utf-8'))
        os.write(ca_cert_out_fd, ca_cert.encode('utf-8'))
        os.write(ca_key_out_fd, ca_key.encode('utf-8'))
        os.write(password_out_fd, password.encode('utf-8'))
        os.write(csr_out_fd, client_csr.encode('utf-8'))

        os.close(extfile_out_fd)
        os.close(ca_cert_out_fd)
        os.close(ca_key_out_fd)
        os.close(password_out_fd)
        os.close(csr_out_fd)

        serial = uuid.uuid4().int

        cmd = ('openssl x509 -req -days 3650 -sha256 -in /dev/fd/%d ' +
               '-passin fd:%d -CA /dev/fd/%d -CAkey /dev/fd/%d ' +
               '-CAcreateserial -extfile /dev/fd/%d -set_serial %d') % \
            (csr_in_fd, password_in_fd, ca_cert_in_fd, ca_key_in_fd,
             extfile_in_fd, serial)
        logging.info(cmd)

        args = {}
        if sys.version_info >= (3, 2):
            args = {'pass_fds': (extfile_in_fd, ca_cert_in_fd, ca_key_in_fd,
                                 password_in_fd, csr_in_fd)}

        out = check_output(shlex.split(cmd), **args)
    finally:
        os.close(extfile_in_fd)
        os.close(ca_cert_in_fd)
        os.close(ca_key_in_fd)
        os.close(password_in_fd)
        os.close(csr_in_fd)

    return out.decode('utf-8')


def generate_server_key():
    cmd = 'openssl genrsa 4096'

    logging.info(cmd)

    out = check_output(shlex.split(cmd))

    return out.decode('utf-8')


def generate_server_csr(server_key, fqdn):
    key_in_fd, key_out_fd = os.pipe()

    try:
        os.write(key_out_fd, server_key.encode('utf-8'))
        os.close(key_out_fd)

        cmd = 'openssl req -subj "/CN=%s" -new -key /dev/fd/%d' % \
            (fqdn, key_in_fd)

        logging.info(cmd)

        args = {}
        if sys.version_info >= (3, 2):
            args = {'pass_fds': (key_in_fd,)}

        out = check_output(shlex.split(cmd), **args)
    finally:
        os.close(key_in_fd)

    return out.decode('utf-8')


def sign_server_cert(ca_cert, ca_key, password, client_csr, altnames=[]):
    extfile = ''

    altname_list = []

    for altname in altnames:
        if is_ip_addr(altname):
            altname_list.append('IP:' + altname)
        else:
            altname_list.append('DNS:' + altname)

    extfile = 'subjectAltName = %s\n' % (', '.join(altname_list))
    extfile += 'extendedKeyUsage = serverAuth, clientAuth'

    extfile_in_fd, extfile_out_fd = os.pipe()
    ca_cert_in_fd, ca_cert_out_fd = os.pipe()
    ca_key_in_fd, ca_key_out_fd = os.pipe()
    password_in_fd, password_out_fd = os.pipe()
    csr_in_fd, csr_out_fd = os.pipe()

    try:
        os.write(extfile_out_fd, extfile.encode('utf-8'))
        os.write(ca_cert_out_fd, ca_cert.encode('utf-8'))
        os.write(ca_key_out_fd, ca_key.encode('utf-8'))
        os.write(password_out_fd, password.encode('utf-8'))
        os.write(csr_out_fd, client_csr.encode('utf-8'))

        os.close(extfile_out_fd)
        os.close(ca_cert_out_fd)
        os.close(ca_key_out_fd)
        os.close(password_out_fd)
        os.close(csr_out_fd)

        serial = uuid.uuid4().int

        cmd = ('openssl x509 -req -days 3650 -sha256 -in /dev/fd/%d ' +
               '-passin fd:%d -CA /dev/fd/%d -CAkey /dev/fd/%d ' +
               '-CAcreateserial -extfile /dev/fd/%d -set_serial %d') % \
            (csr_in_fd, password_in_fd, ca_cert_in_fd, ca_key_in_fd,
             extfile_in_fd, serial)
        logging.info(cmd)

        args = {}
        if sys.version_info >= (3, 2):
            args = {'pass_fds': (extfile_in_fd, ca_cert_in_fd, ca_key_in_fd,
                                 password_in_fd, csr_in_fd)}

        out = check_output(shlex.split(cmd), **args)
    finally:
        os.close(extfile_in_fd)
        os.close(ca_cert_in_fd)
        os.close(ca_key_in_fd)
        os.close(password_in_fd)
        os.close(csr_in_fd)

    return out.decode('utf-8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()

    parser.add_argument('-d', '--dir',
                        help='directory to store certificates (default is .)')

    subparsers = parser.add_subparsers(title="commands", dest="subparser_name")

    # CA parser
    ca_parser = subparsers.add_parser('ca', help='generate CA certificate')
    ca_parser.add_argument('-f', '--force', action='store_true',
                           default=False, help='overwrite if exists')
    ca_parser.add_argument('-p', '--password', help='password for CA key')

    # Client parser
    client_parser = subparsers.add_parser('client',
                                          help='generate client certificate')
    client_parser.add_argument('-f', '--force', action='store_true',
                               default=False, help='overwrite if exists')
    client_parser.add_argument('-p', '--password', help='password for CA key')
    client_parser.add_argument('-k', '--key',
                               help='print generated key')
    client_parser.add_argument('-c', '--cert',
                               help='print generated cert')

    # Server parser
    server_parser = subparsers.add_parser('server',
                                          help='generate server certificate')
    server_parser.add_argument('-f', '--force', action='store_true',
                               default=False, help='overwrite if exists')
    server_parser.add_argument('fqdn', help='domain name of the server')
    server_parser.add_argument('altname', nargs='*',
                               help='alternative server name')
    server_parser.add_argument('-p', '--password', help='password for CA key')
    server_parser.add_argument('-k', '--key',
                               help='print generated key')
    server_parser.add_argument('-c', '--cert',
                               help='print generated cert')

    args = parser.parse_args()

    try:
        common_name = 'cn'
        password = 'asdf'
        fqdn = 'foo.com'
        altnames = ('127.0.0.1', 'foo.org', 'fe80::e000:494a:e8a:4022')

        ca_key = generate_ca_private_key(password)
        ca_cert = generate_ca_certificate(ca_key, password, common_name)

        client_key = generate_client_key()
        client_csr = generate_client_csr(client_key)
        client_cert = sign_client_cert(ca_cert, ca_key, password, client_csr)

        server_key = generate_server_key()
        server_csr = generate_server_csr(server_key, fqdn)
        server_cert = sign_server_cert(ca_cert, ca_key, password, server_csr,
                                       altnames)

    except subprocess.CalledProcessError as ex:
        err_str = ex.stderr.decode('utf-8')

        print("Error: ", err_str)
        sys.exit(1)
