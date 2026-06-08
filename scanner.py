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
        # An empty or comment-only file parses to None (not {}); normalize so
        # _iter_hosts always gets a dict to call .items() on.
        return yaml.safe_load(f) or {}


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


def _make_ssh_scanner(collect_fn, collect_kwargs=lambda host_config: {}):
    """Build a scan_<type> function for an SSH-based collector.

    Handles the connect/collect/close/error boilerplate shared by every
    SSH-based collector. `collect_kwargs` extracts any extra per-host config
    (e.g. Linux's `compose_paths`) to pass through to `collect_fn`.
    """
    def scan(host_config: dict) -> tuple:
        host = host_config["host"]
        client = None
        try:
            client = connect(host, host_config["user"], legacy=host_config.get("legacy_ssh", False))
            data = collect_fn(client, **collect_kwargs(host_config))
            return (host, data, None)
        except Exception as e:
            return (host, None, e)
        finally:
            if client:
                client.close()

    return scan


scan_linux   = _make_ssh_scanner(collect_linux, lambda h: {"compose_paths": h.get("compose_paths")})
scan_macos   = _make_ssh_scanner(collect_macos)
scan_network = _make_ssh_scanner(collect_network)
scan_switch  = _make_ssh_scanner(collect_switch)
scan_windows = _make_ssh_scanner(collect_windows)


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


SCAN_FNS = {
    "linux":   scan_linux,
    "macos":   scan_macos,
    "network": scan_network,
    "proxmox": scan_proxmox,
    "snmp":    scan_snmp,
    "switch":  scan_switch,
    "windows": scan_windows,
}
