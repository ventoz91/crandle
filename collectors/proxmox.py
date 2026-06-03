import getpass
from proxmoxer import ProxmoxAPI


def connect_proxmox(host: str, user: str, realm: str, verify_ssl: bool, token_id: str = None, token_secret: str = None):
    if token_id and token_secret:
        return ProxmoxAPI(
            host,
            user=f"{user}@{realm}",
            token_name=token_id,
            token_value=token_secret,
            verify_ssl=verify_ssl,
        )
    password = getpass.getpass(f"Proxmox password for {user}@{host}: ")
    return ProxmoxAPI(
        host,
        user=f"{user}@{realm}",
        password=password,
        verify_ssl=verify_ssl,
    )


def collect_proxmox(host_config: dict):
    host = host_config["host"]
    user = host_config.get("user", "root")
    realm = host_config.get("realm", "pam")
    verify_ssl = host_config.get("verify_ssl", False)
    token_id = host_config.get("token_id")
    token_secret = host_config.get("token_secret")

    proxmox = connect_proxmox(host, user, realm, verify_ssl, token_id, token_secret)

    data = {
        "host": host,
        "nodes": [],
    }

    for node in proxmox.nodes.get():
        node_name = node["node"]

        node_data = {
            "name": node_name,
            "status": node.get("status"),
            "cpu": node.get("cpu"),
            "memory_used": node.get("mem"),
            "memory_total": node.get("maxmem"),
            "disk_used": node.get("disk"),
            "disk_total": node.get("maxdisk"),
            "uptime": node.get("uptime"),
            "vms": [],
            "lxc": [],
            "storage": [],
        }

        for vm in proxmox.nodes(node_name).qemu.get():
            node_data["vms"].append({
                "vmid": vm.get("vmid"),
                "name": vm.get("name"),
                "status": vm.get("status"),
                "cpu": vm.get("cpu"),
                "cpus": vm.get("cpus"),
                "memory": vm.get("mem"),
                "max_memory": vm.get("maxmem"),
                "disk": vm.get("disk"),
                "max_disk": vm.get("maxdisk"),
                "uptime": vm.get("uptime"),
            })

        for ct in proxmox.nodes(node_name).lxc.get():
            node_data["lxc"].append({
                "vmid": ct.get("vmid"),
                "name": ct.get("name"),
                "status": ct.get("status"),
                "cpu": ct.get("cpu"),
                "cpus": ct.get("cpus"),
                "memory": ct.get("mem"),
                "max_memory": ct.get("maxmem"),
                "disk": ct.get("disk"),
                "max_disk": ct.get("maxdisk"),
                "uptime": ct.get("uptime"),
            })

        for storage in proxmox.nodes(node_name).storage.get():
            node_data["storage"].append({
                "name": storage.get("storage"),
                "type": storage.get("type"),
                "enabled": storage.get("enabled"),
                "active": storage.get("active"),
                "used": storage.get("used"),
                "total": storage.get("total"),
                "available": storage.get("avail"),
            })

        data["nodes"].append(node_data)

    return data
