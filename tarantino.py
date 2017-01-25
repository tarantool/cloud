#!/usr/bin/env python3
# pylint: disable=missing-super-argument
import global_env
import group
import consul
from sense import Sense
import ip_pool
import random
import logging
import docker
import uuid
import time
import tarantool
import allocate
import datetime
import json
import task
import tarfile
import io


def tar_string(filename, data):
    binary_data = data.encode('utf-8')
    out = io.BytesIO()
    with tarfile.TarFile(fileobj=out, mode='w') as fobj:
        tarinfo = tarfile.TarInfo(name=filename)
        tarinfo.size = len(binary_data)
        fobj.addfile(tarinfo, fileobj=io.BytesIO(binary_data))
    return out.getvalue()


class TarantinoTask(task.Task):
    tarantino_task_type = None

    def __init__(self, group_id):
        super().__init__(self.tarantino_task_type)
        self.group_id = group_id

    def get_dict(self, index=None):
        obj = super().get_dict(index)
        obj['group_id'] = self.group_id
        return obj


class CreateTask(TarantinoTask):
    tarantino_task_type = "create_tarantino"


class UpdateTask(TarantinoTask):
    tarantino_task_type = "update_tarantino"


class DeleteTask(TarantinoTask):
    tarantino_task_type = "delete_tarantino"


def backup_is_valid(storage, digest):
    return True


class Tarantino(group.Group):
    def __init__(self, consul_host, group_id):
        super(Tarantino, self).__init__(consul_host, group_id)

    @classmethod
    def get(cls, group_id):
        tar = Tarantino(global_env.consul_host, group_id)

        return tar

    @classmethod
    def create(cls, create_task, name, memsize, password, check_period):
        group_id = create_task.group_id

        try:
            consul_obj = consul.Consul(host=global_env.consul_host,
                                       token=global_env.consul_acl_token)
            kv = consul_obj.kv

            create_task.log("Creating group '%s'", group_id)

            ip1 = ip_pool.allocate_ip()
            creation_time = datetime.datetime.now(
                datetime.timezone.utc).isoformat()

            kv.put('tarantool/%s/blueprint/type' % group_id, 'tarantino')
            kv.put('tarantool/%s/blueprint/name' % group_id, name)
            kv.put('tarantool/%s/blueprint/memsize' % group_id, str(memsize))
            kv.put('tarantool/%s/blueprint/check_period' % group_id,
                   str(check_period))
            kv.put('tarantool/%s/blueprint/creation_time' % group_id,
                   creation_time)
            kv.put('tarantool/%s/blueprint/instances/1/addr' % group_id, ip1)

            Sense.update()

            tar = Tarantino(global_env.consul_host, group_id)

            create_task.log("Allocating instance to physical nodes")

            tar.allocate()
            Sense.update()

            create_task.log("Registering services")
            tar.register()
            Sense.update()

            create_task.log("Creating containers")
            tar.create_containers(password)
            Sense.update()

            create_task.log("Completed creating group")

            create_task.set_status(task.STATUS_SUCCESS)
        except Exception as ex:
            logging.exception("Failed to create group '%s'", group_id)
            create_task.set_status(task.STATUS_CRITICAL, str(ex))

            raise

        return tar

    def delete(self, delete_task):
        try:
            group_id = self.group_id

            delete_task.log("Unallocating instance")
            self.unallocate()

            delete_task.log("Unregistering services")
            self.unregister()

            delete_task.log("Removing containers")
            self.remove_containers()

            delete_task.log("Removing blueprint")
            self.remove_blueprint()

            delete_task.log("Completed removing group")

            Sense.update()
            delete_task.set_status(task.STATUS_SUCCESS)
        except Exception as ex:
            logging.exception("Failed to delete group '%s'", group_id)
            delete_task.set_status(task.STATUS_CRITICAL, str(ex))

            raise

    def allocate(self):
        consul_obj = consul.Consul(host=global_env.consul_host,
                                   token=global_env.consul_acl_token)
        kv = consul_obj.kv

        blueprint = self.blueprint

        host = allocate.allocate(blueprint['memsize'])

        kv.put('tarantool/%s/allocation/instances/1/host' %
               self.group_id, host)

    def register(self):
        instance_num = '1'
        blueprint = self.blueprint
        allocation = self.allocation

        instance_id = self.group_id + '_' + instance_num
        docker_host = allocation['instances'][instance_num]['host']
        docker_hosts = Sense.docker_hosts()
        consul_host = None
        for host in docker_hosts:
            if host['addr'].split(':')[0] == docker_host or \
               host['consul_host'] == docker_host:
                consul_host = host['consul_host']
        if not consul_host:
            raise RuntimeError("Failed to find consul host of %s" %
                               docker_host)

        addr = blueprint['instances'][instance_num]['addr']
        check_period = blueprint['check_period']

        consul_obj = consul.Consul(host=consul_host,
                                   token=global_env.consul_acl_token)

        container_check = {
            'docker_container_id': instance_id,
            'shell': "/bin/sh",
            'script': "/bin/true",
            'interval': "%ds" % check_period,
            'status': 'warning'
        }

        replication_check = {
            'docker_container_id': instance_id,
            'shell': "/bin/sh",
            'script': "/var/lib/mon.d/tarantool_replication.sh",
            'interval': "%ds" % check_period,
            'status': 'warning'
        }

        memory_check = {
            'docker_container_id': instance_id,
            'shell': "/bin/sh",
            'script': "/var/lib/mon.d/tarantool_memory.sh",
            'interval': "%ds" % check_period,
            'status': 'warning'
        }

        logging.info("Registering instance '%s' on '%s'",
                     instance_id,
                     consul_host)

        ret = consul_obj.agent.service.register("tarantino",
                                                service_id=instance_id,
                                                address=addr,
                                                port=80,
                                                check=container_check,
                                                tags=['tarantool'])

        #ret = consul_obj.agent.check.register("Memory Utilization",
        #                                      check=memory_check,
        #                                      check_id=instance_id + '_memory',
        #                                      service_id=instance_id)

    def create_containers(self, password):
        instance_num = '1'
        blueprint = self.blueprint
        allocation = self.allocation

        instance_id = self.group_id + '_' + instance_num
        addr = blueprint['instances'][instance_num]['addr']
        memsize = blueprint['memsize']
        network_settings = Sense.network_settings()
        network_name = network_settings['network_name']
        if not network_name:
            raise RuntimeError("Network name is not specified in settings")

        docker_host = allocation['instances'][instance_num]['host']
        docker_hosts = Sense.docker_hosts()

        docker_addr = None
        for host in docker_hosts:
            if host['addr'].split(':')[0] == docker_host or \
               host['consul_host'] == docker_host:
                docker_addr = host['addr']

        if not docker_addr:
            raise RuntimeError("No such Docker host: '%s'" % docker_host)

        replica_ip = None
        if instance_num == '2':
            replica_ip = blueprint['instances']['1']['addr']

        docker_obj = docker.Client(base_url=docker_addr,
                                   tls=global_env.docker_tls_config)

        self.ensure_image(docker_addr)
        self.ensure_network(docker_addr)

        if not replica_ip:
            logging.info("Creating tarantino '%s' on '%s' with ip '%s'",
                         instance_id, docker_obj.base_url, addr)
        else:
            logging.info("Creating tarantino '%s' on '%s' with ip '%s'" +
                         " and replication source: '%s'",
                         instance_id, docker_obj.base_url, addr, replica_ip)

        host_config = docker_obj.create_host_config(
            restart_policy =
            {
                "MaximumRetryCount": 0,
                "Name": "unless-stopped"
            })

        networking_config = {
            'EndpointsConfig':
            {
                network_name:
                {
                    'IPAMConfig':
                    {
                        "IPv4Address": addr,
                        "IPv6Address": ""
                    },
                    "Links": [],
                    "Aliases": []
                }
            }
        }

        environment = {}

        environment['TARANTOOL_SLAB_ALLOC_ARENA'] = float(memsize)/1024

        if password:
            environment['MEMCACHED_PASSWORD'] = password

        container = docker_obj.create_container(image='tarantool/tarantino',
                                                name=instance_id,
                                                host_config=host_config,
                                                networking_config=networking_config,
                                                environment=environment,
                                                labels=['tarantool'])

        docker_obj.connect_container_to_network(container.get('Id'),
                                                network_name,
                                                ipv4_address=addr)
        docker_obj.start(container=container.get('Id'))

    def update(self, name, memsize, password, config_str,
               docker_image_name, update_task):
        try:
            if name and name != self.blueprint['name']:
                self.rename(name, update_task)

            if memsize and memsize != self.blueprint['memsize']:
                self.resize(memsize, update_task)

            if config_str:
                update_task.log("Updating config of group %s", self.group_id)
                self.update_config("1", config_str)

            if docker_image_name:
                self.upgrade(update_task)

            Sense.update()
            update_task.set_status(task.STATUS_SUCCESS)
        except Exception as ex:
            logging.exception("Failed to update group '%s'", self.group_id)
            update_task.set_status(task.STATUS_CRITICAL, str(ex))

            raise

    def resize(self, memsize, update_task):
        consul_obj = consul.Consul(host=global_env.consul_host,
                                   token=global_env.consul_acl_token)
        kv = consul_obj.kv

        update_task.log("Resizing instance")
        self.resize_instance("1", memsize)

        kv.put('tarantool/%s/blueprint/memsize' % self.group_id, str(memsize))
        update_task.log("Completed resizing")


    def rename(self, name, update_task):
        consul_obj = consul.Consul(host=global_env.consul_host,
                                   token=global_env.consul_acl_token)
        kv = consul_obj.kv

        msg = "Renaming group '%s' to '%s'" % (self.group_id, name)
        update_task.log(msg)
        logging.info(msg)

        kv.put('tarantool/%s/blueprint/name' % self.group_id, name)


    def ensure_image(self, docker_addr):
        docker_obj = docker.Client(base_url=docker_addr,
                                   tls=global_env.docker_tls_config)
        image_exists = any(['tarantool/tarantino:latest' in
                            (i['RepoTags'] or [])
                            for i in docker_obj.images()])

        if image_exists:
            return

        response = docker_obj.pull('tarantool/tarantino', stream=True)

        for line in response:
            decoded_line = json.loads(line.decode('utf-8'))
            if 'stream' in decoded_line:
                logging.info("Pull tarantino on %s: %s",
                             docker_addr,
                             decoded_line['stream'])

    def ensure_network(self, docker_addr):
        docker_obj = docker.Client(base_url=docker_addr,
                                   tls=global_env.docker_tls_config)

        settings = Sense.network_settings()
        network_name = settings['network_name']
        subnet = settings['subnet']

        if not network_name:
            raise RuntimeError("Network name not specified")

        network_exists = any([n['Name'] == network_name
                              for n in docker_obj.networks()])

        if network_exists:
            return

        if not settings['create_automatically']:
            raise RuntimeError(("No network '%s' exists and automatic creation" +
                                "prohibited") % network_name)

        ipam_pool = docker.utils.create_ipam_pool(
            subnet=subnet
        )
        ipam_config = docker.utils.create_ipam_config(
            pool_configs=[ipam_pool]
        )

        logging.info("Creating network '%s'", network_name)
        docker_obj.create_network(name=network_name,
                                  driver='bridge',
                                  ipam=ipam_config)


    def resize_instance(self, instance_num, memsize):
        containers = self.containers

        if instance_num not in containers['instances']:
            return

        instance_id = self.group_id + '_' + instance_num
        docker_hosts = [h['addr'].split(':')[0] for h in Sense.docker_hosts()
                        if h['status'] == 'passing']

        if containers:
            docker_host = containers['instances'][instance_num]['host']
            docker_hosts = Sense.docker_hosts()

            docker_addr = None
            for host in docker_hosts:
                if host['addr'].split(':')[0] == docker_host or \
                   host['consul_host'] == docker_host:
                    docker_addr = host['addr']
            if not docker_addr:
                raise RuntimeError("No such Docker host: '%s'" % docker_host)

            logging.info("Resizing container '%s' to %d MiB on '%s'",
                         instance_id,
                         memsize,
                         docker_host)

            docker_obj = docker.Client(base_url=docker_addr,
                                       tls=global_env.docker_tls_config)

            cmd = "tarantool_set_config.lua TARANTOOL_SLAB_ALLOC_ARENA " + \
                  str(float(memsize)/1024)

            exec_id = docker_obj.exec_create(self.group_id + '_' + instance_num,
                                             cmd)
            docker_obj.exec_start(exec_id)
            ret = docker_obj.exec_inspect(exec_id)

            if ret['ExitCode'] != 0:
                raise RuntimeError("Failed to set memory size for container " +
                                   instance_id)

            docker_obj.restart(container=instance_id)
        else:
            logging.info("Not resizing container '%s', as it doesn't exist",
                         instance_id)

    def update_config(self, instance_num, config_str):
        containers = self.containers

        if instance_num not in containers['instances']:
            return

        instance_id = self.group_id + '_' + instance_num
        docker_hosts = [h['addr'].split(':')[0] for h in Sense.docker_hosts()
                        if h['status'] == 'passing']

        if containers:
            docker_host = containers['instances'][instance_num]['host']
            docker_hosts = Sense.docker_hosts()

            docker_addr = None
            for host in docker_hosts:
                if host['addr'].split(':')[0] == docker_host or \
                   host['consul_host'] == docker_host:
                    docker_addr = host['addr']
            if not docker_addr:
                raise RuntimeError("No such Docker host: '%s'" % docker_host)

            logging.info("Uploading new config for container '%s' on '%s'",
                         instance_id,
                         docker_host)

            docker_obj = docker.Client(base_url=docker_addr,
                                       tls=global_env.docker_tls_config)

            buf = io.BytesIO(tar_string('service.json', config_str))
            status = docker_obj.put_archive(self.group_id + '_' + instance_num,
                                            '/opt/tarantool',
                                            buf)

            if not status:
                raise RuntimeError("Failed to set config for container " +
                                   instance_id)

            docker_obj.restart(container=instance_id)
        else:
            logging.info(
                "Not setting config for container '%s', as it doesn't exist",
                instance_id)
