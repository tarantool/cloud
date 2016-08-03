#!/usr/bin/env python

import consul
import global_env
from sense import Sense

class GroupNotFoundError(RuntimeError):
    pass

class Group(object):
    def __init__(self, consul_host, group_id):
        self.consul_host = consul_host
        self.consul = consul.Consul(host=consul_host,
                                    token=global_env.consul_acl_token)
        self.group_id = group_id

        blueprints = Sense.blueprints()

        if not group_id in blueprints:
            raise GroupNotFoundError("No such blueprint: '%s'", group_id)

        self._blueprint = blueprints[group_id]

    @property
    def blueprint(self):
        blueprints = Sense.blueprints()

        if self.group_id in blueprints:
            self._blueprint = blueprints[self.group_id]

        return self._blueprint

    @property
    def allocation(self):
        allocations = Sense.allocations()

        if self.group_id in allocations:
            return allocations[self.group_id]
        else:
            return {"instances": {}}

    @property
    def services(self):
        services = Sense.services()

        if self.group_id in services:
            return services[self.group_id]
        else:
            return {"instances": {}}

    @property
    def containers(self):
        containers = Sense.containers()

        if self.group_id in containers:
            return containers[self.group_id]
        else:
            return {"instances": {}}
