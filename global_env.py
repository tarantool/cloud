#!/usr/bin/env python3

consul_host = None
docker_tls_config = None
consul_acl_token = None
backup_storage = None
kv = []
settings = []
backups = {}
services = {}
nodes = {}
containers = {}
docker_info = {}
docker_statuses = {}
default_network_settings = {"network_name": None,
                            "gateway_ip": None,
                            "subnet": None,
                            "create_automatically": False}
