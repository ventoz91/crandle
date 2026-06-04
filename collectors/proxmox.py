import getpass

from proxmoxer import ProxmoxAPI

from utils.ssh import _password_lock

_proxmox_password_cache = {}


def _fmt_bytes(n):
    if n is None:
        return "N/A"
    n = int(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024.0:
            return f"{n:.1f} {unit}"
        n /= 1024.0
    return f"{n:.1f} PB"


def _fmt_cpu(cpu):
    if cpu is None:
        return "N/A"
    return f"{float(cpu) * 100:.1f}%"


def _fmt_uptime(seconds):
    if seconds is None:
        return "N/A"
    s = int(seconds)
    d, s = divmod(s, 86400)
    h, m = divmod(s, 3600)
    m //= 60
    if d > 0:
        return f"{d}d {h}h {m}m"
    if h > 0:
        return f"{h}h {m}m"
    return f"{m}m"


def connect_proxmox(host, user, realm, verify_ssl, token_id=None, token_secret=None):
    if token_id and token_secret:
        if "!" in token_id:
            full_user, token_name = token_id.split("!", 1)
        else:
            full_user = f"{user}@{realm}"
            token_name = token_id
        return ProxmoxAPI(
            host, user=full_user, token_name=token_name,
            token_value=token_secret, verify_ssl=verify_ssl,
        )

    cache_key = f"{user}@{host}"
    with _password_lock:
        if cache_key not in _proxmox_password_cache:
            _proxmox_password_cache[cache_key] = getpass.getpass(f"Proxmox password for {user}@{host}: ")

    return ProxmoxAPI(
        host, user=f"{user}@{realm}",
        password=_proxmox_password_cache[cache_key], verify_ssl=verify_ssl,
    )


def _guest_ips(proxmox, node_name, vmid) -> str:
    """Return comma-separated IPv4 addresses from QEMU guest agent, or empty string."""
    try:
        result = proxmox.nodes(node_name).qemu(vmid).agent("network-get-interfaces").get()
        ips = []
        for iface in result.get("result", []):
            if iface.get("name", "").startswith("lo"):
                continue
            for addr in iface.get("ip-addresses", []):
                if addr.get("ip-address-type") == "ipv4":
                    ip = addr.get("ip-address", "")
                    if ip and not ip.startswith("127."):
                        ips.append(ip)
        return ", ".join(ips)
    except Exception:
        return ""


def _lxc_ip(proxmox, node_name, vmid) -> str:
    """Return first static IPv4 from LXC network config, or empty string."""
    try:
        cfg = proxmox.nodes(node_name).lxc(vmid).config.get()
        for key in sorted(cfg):
            if not key.startswith("net"):
                continue
            for part in cfg[key].split(","):
                if part.startswith("ip=") and part != "ip=dhcp":
                    return part[3:].split("/")[0]
    except Exception:
        pass
    return ""


def collect_proxmox(host_config: dict):
    host         = host_config["host"]
    user         = host_config.get("user", "root")
    realm        = host_config.get("realm", "pam")
    verify_ssl   = host_config.get("verify_ssl", False)
    token_id     = host_config.get("token_id")
    token_secret = host_config.get("token_secret")

    proxmox = connect_proxmox(host, user, realm, verify_ssl, token_id, token_secret)

    # Cluster/API version
    try:
        api_version = proxmox.version.get().get("version", "")
    except Exception:
        api_version = ""

    data = {
        "host":        host,
        "api_version": api_version,
        "nodes":       [],
    }

    for node in proxmox.nodes.get():
        node_name = node["node"]

        # Node detail from status endpoint (has kernel/pveversion)
        try:
            node_status = proxmox.nodes(node_name).status.get()
        except Exception:
            node_status = {}

        node_data = {
            "name":         node_name,
            "status":       node.get("status"),
            "cpu":          _fmt_cpu(node.get("cpu")),
            "cpu_count":    node_status.get("cpuinfo", {}).get("cpus", ""),
            "cpu_model":    node_status.get("cpuinfo", {}).get("model", ""),
            "memory_used":  _fmt_bytes(node.get("mem")),
            "memory_total": _fmt_bytes(node.get("maxmem")),
            "disk_used":    _fmt_bytes(node.get("disk")),
            "disk_total":   _fmt_bytes(node.get("maxdisk")),
            "uptime":       _fmt_uptime(node.get("uptime")),
            "kernel":       node_status.get("kversion", ""),
            "pve_version":  node_status.get("pveversion", ""),
            "vms":          [],
            "lxc":          [],
            "storage":      [],
        }

        for vm in proxmox.nodes(node_name).qemu.get():
            vmid   = vm.get("vmid")
            status = vm.get("status", "")

            # Snapshot count
            try:
                snaps = proxmox.nodes(node_name).qemu(vmid).snapshot.get()
                snap_count = max(0, len(snaps) - 1)  # subtract "current" pseudo-snapshot
            except Exception:
                snap_count = 0

            vm_entry = {
                "vmid":        vmid,
                "name":        vm.get("name"),
                "status":      status,
                "tags":        vm.get("tags", ""),
                "cpu":         _fmt_cpu(vm.get("cpu")),
                "cpus":        vm.get("cpus"),
                "memory":      _fmt_bytes(vm.get("mem")),
                "max_memory":  _fmt_bytes(vm.get("maxmem")),
                "disk":        _fmt_bytes(vm.get("disk")),
                "max_disk":    _fmt_bytes(vm.get("maxdisk")),
                "uptime":      _fmt_uptime(vm.get("uptime")),
                "snapshots":   snap_count,
                "guest_ips":   _guest_ips(proxmox, node_name, vmid) if status == "running" else "",
            }
            node_data["vms"].append(vm_entry)

        for ct in proxmox.nodes(node_name).lxc.get():
            vmid = ct.get("vmid")
            ct_entry = {
                "vmid":       vmid,
                "name":       ct.get("name"),
                "status":     ct.get("status"),
                "tags":       ct.get("tags", ""),
                "cpu":        _fmt_cpu(ct.get("cpu")),
                "cpus":       ct.get("cpus"),
                "memory":     _fmt_bytes(ct.get("mem")),
                "max_memory": _fmt_bytes(ct.get("maxmem")),
                "disk":       _fmt_bytes(ct.get("disk")),
                "max_disk":   _fmt_bytes(ct.get("maxdisk")),
                "uptime":     _fmt_uptime(ct.get("uptime")),
                "ip":         _lxc_ip(proxmox, node_name, vmid),
            }
            node_data["lxc"].append(ct_entry)

        for storage in proxmox.nodes(node_name).storage.get():
            node_data["storage"].append({
                "name":      storage.get("storage"),
                "type":      storage.get("type"),
                "enabled":   storage.get("enabled"),
                "active":    storage.get("active"),
                "used":      _fmt_bytes(storage.get("used")),
                "total":     _fmt_bytes(storage.get("total")),
                "available": _fmt_bytes(storage.get("avail")),
            })

        data["nodes"].append(node_data)

    return data
