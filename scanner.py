import yaml

from utils.ssh import connect
from collectors.linux import collect_linux
from collectors.macos import collect_macos
from collectors.network import collect_network
from collectors.proxmox import collect_proxmox
from collectors.snmp import collect_snmp
from collectors.switch import collect_switch
from collectors.windows import collect_windows


def load_inventory(path="inventory.yml"):
    with open(path, "r") as f:
        return yaml.safe_load(f)


def _iter_hosts(inventory: dict):
    """Yield (role, host_type, host_config) for every defined host."""
    for role, host_types in inventory.items():
        if not isinstance(host_types, dict):
            continue
        for host_type, hosts in host_types.items():
            if not isinstance(hosts, list):
                continue
            for h in hosts:
                yield role, host_type, h


def filter_inventory(inventory: dict, host_filter: str) -> dict:
    filtered = {}
    for role, host_type, h in _iter_hosts(inventory):
        if host_filter not in h.get("host", ""):
            continue
        filtered.setdefault(role, {}).setdefault(host_type, []).append(h)
    return filtered


def scan_linux(host_config: dict) -> tuple:
    host = host_config["host"]
    client = None
    try:
        client = connect(host, host_config["user"], legacy=host_config.get("legacy_ssh", False))
        data = collect_linux(client, compose_paths=host_config.get("compose_paths"))
        return (host, data, None)
    except Exception as e:
        return (host, None, e)
    finally:
        if client:
            client.close()


def scan_macos(host_config: dict) -> tuple:
    host = host_config["host"]
    client = None
    try:
        client = connect(host, host_config["user"], legacy=host_config.get("legacy_ssh", False))
        data = collect_macos(client)
        return (host, data, None)
    except Exception as e:
        return (host, None, e)
    finally:
        if client:
            client.close()


def scan_network(host_config: dict) -> tuple:
    host = host_config["host"]
    client = None
    try:
        client = connect(host, host_config["user"], legacy=host_config.get("legacy_ssh", False))
        data = collect_network(client)
        return (host, data, None)
    except Exception as e:
        return (host, None, e)
    finally:
        if client:
            client.close()


def scan_proxmox(host_config: dict) -> tuple:
    host = host_config["host"]
    try:
        data = collect_proxmox(host_config)
        return (host, data, None)
    except Exception as e:
        return (host, None, e)


def scan_snmp(host_config: dict) -> tuple:
    host = host_config["host"]
    try:
        data = collect_snmp(host_config)
        return (host, data, None)
    except Exception as e:
        return (host, None, e)


def scan_switch(host_config: dict) -> tuple:
    host = host_config["host"]
    client = None
    try:
        client = connect(host, host_config["user"], legacy=host_config.get("legacy_ssh", False))
        data = collect_switch(client)
        return (host, data, None)
    except Exception as e:
        return (host, None, e)
    finally:
        if client:
            client.close()


def scan_windows(host_config: dict) -> tuple:
    host = host_config["host"]
    client = None
    try:
        client = connect(host, host_config["user"], legacy=host_config.get("legacy_ssh", False))
        data = collect_windows(client)
        return (host, data, None)
    except Exception as e:
        return (host, None, e)
    finally:
        if client:
            client.close()


SCAN_FNS = {
    "linux":   scan_linux,
    "macos":   scan_macos,
    "network": scan_network,
    "proxmox": scan_proxmox,
    "snmp":    scan_snmp,
    "switch":  scan_switch,
    "windows": scan_windows,
}
