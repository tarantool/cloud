#!/bin/bash

consul_delete_kv()
{
    consul_host=$1
    kv_path=$2
    python3 <<-EOF
import consul
c = consul.Consul(host="$consul_host")
c.kv.delete("$kv_path", recurse=True)
EOF
}

consul_put_kv()
{
    consul_host=$1
    kv_path=$2
    kv_value=$3
    python3 <<-EOF
import consul
c = consul.Consul(host="$consul_host")
c.kv.put("$kv_path", "$kv_value")
EOF
}


consul_delete_services()
{
    consul_host=$1
    service_name=$2
    python3 <<-EOF
import consul
c = consul.Consul(host="172.20.20.10")

consul_health = c.health.service("consul")[1]
healthy_consul_nodes = []
for service in consul_health:
    statuses = [check['Status'] for check in service['Checks']]
    if "critical" not in statuses:
        service_addr = service['Service']['Address'] or \
                       service['Node']['Address']
        healthy_consul_nodes += [service_addr]

for node in healthy_consul_nodes:
    local = consul.Consul(host=node)
    services = local.health.service("$service_name")[1]
    for service in services:
        local.agent.service.deregister(service['Service']['ID'])
EOF
}

consul_delete_service()
{
    consul_host=$1
    service_id=$2
    python3 <<-EOF
import consul
c = consul.Consul(host="172.20.20.10")
for node in  c.catalog.nodes()[1]:
    local = consul.Consul(host=node['Address'])
    local.agent.service.deregister("$service_id")
EOF
}


consul_get_healthy_docker_hosts()
{
    consul_host=$1
    python3 <<-EOF
import consul

c = consul.Consul(host="$consul_host")

health =  c.health.service("docker", passing=True)[1]

result = []
for entry in health:
    addr = entry['Service']['Address'] or entry['Node']['Address']
    port = entry['Service']['Port']

    statuses = [check['Status'] for check in entry['Checks']]
    if "critical" not in statuses:
        result.append(addr)

print("\n".join(result))
EOF
}

consul_get_service_ip()
{
    consul_host=$1
    service_name=$2
    service_id=$3
    python3 <<-EOF
import consul
c = consul.Consul(host="$consul_host")

health =  c.health.service("$service_name")[1]

result = []
for entry in health:
    addr = entry['Service']['Address'] or entry['Node']['Address']

    if entry['Service']['ID'] == "$service_id":
        print(addr)
EOF
}


consul_delete_service()
{
    consul_host=$1
    service_name=$2
    service_id=$3

    python3 <<-EOF
import consul
c = consul.Consul(host="$consul_host")

health =  c.health.service("$service_name")[1]

agent_addr = None

for service in health:
    if service['Service']['ID'] == "$service_id":
        agent_addr = service['Node']['Address']

if agent_addr:
    c = consul.Consul(host=agent_addr)
    c.agent.service.deregister("$service_id")
EOF
}

consul_register_service()
{
    consul_host=$1
    service_name=$2
    service_id=$3
    ip_addr=$4
    port=$5

    python3 <<-EOF
import consul
c = consul.Consul(host="$consul_host")

ret = c.agent.service.register("$service_name",
                               service_id="$service_id",
                               address="$ip_addr",
                               port=int("$port"))
EOF

}
