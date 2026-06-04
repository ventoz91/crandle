import base64

from utils.ssh import run_command


def collect_network(client):
    """
    SSH collector for network appliances (OPNsense, pfSense, OpenWrt, etc.).

    Commands are base64-encoded before sending so they arrive in /bin/sh verbatim,
    bypassing any quoting or expansion done by tcsh (OPNsense/pfSense login shell).
    BSD-native tools (ifconfig, netstat) are tried first; Linux tools are the fallback.
    """

    def sh(cmd: str) -> str:
        b64 = base64.b64encode(cmd.encode()).decode()
        return run_command(client, f"echo {b64} | base64 -d | sh")

    def _try(*cmds: str) -> str:
        for cmd in cmds:
            out = sh(cmd)
            if out and not out.startswith("ERROR"):
                return out
        return ""

    data = {
        "hostname":      sh("hostname -s 2>/dev/null || hostname"),
        "platform":      sh("uname -sr"),
        "uptime":        sh("uptime"),
        "load_avg":      _try(
            "uptime | awk -F'load averages?: ' '{print $2}'",
        ),
        "cpu":           _try(
            "sysctl -n hw.model 2>/dev/null",
            "grep 'model name' /proc/cpuinfo 2>/dev/null | head -1 | cut -d: -f2 | sed 's/^ //'",
        ),
        "memory":        _try(
            # BSD: compute used = total - (free_pages * page_size)
            "sysctl -n hw.physmem vm.stats.vm.v_free_count hw.pagesize 2>/dev/null"
            " | awk 'NR==1{t=$1} NR==2{f=$1} NR==3{s=$1}"
            " END{printf \"%.1f GB used / %.1f GB total\", (t-f*s)/1073741824, t/1073741824}'",
            "grep MemTotal /proc/meminfo 2>/dev/null | awk '{printf \"%.1f GB total\", $2/1048576}'",
        ),
        "disk_root":     _try(
            "df -h / 2>/dev/null | awk 'NR==2{print $3\" used / \"$2\" total (\"$5\")\"}'"
        ),
        "ip_addresses":  _try(
            "ifconfig 2>/dev/null | awk '/inet [0-9]/{if($2!=\"127.0.0.1\")printf $2\" \"}'",
            "ip -brief addr show 2>/dev/null | awk '$1!=\"lo\"{printf $3\" \"}'",
        ),
        "default_gateway": _try(
            "route -n get default 2>/dev/null | awk '/gateway/{print $2}'",
            "ip route show default 2>/dev/null | awk '/default/{print $3}'",
        ),
        "dns_servers":   sh("grep '^nameserver' /etc/resolv.conf 2>/dev/null | awk '{print $2}' | tr '\n' ' ' | sed 's/ $//'" ),
        "routing_table": _try(
            "netstat -rn 2>/dev/null | head -20",
            "ip route show 2>/dev/null | head -15",
        ),
        "arp_entries":   _try(
            "arp -a 2>/dev/null | wc -l | tr -d ' '",
            "arp -n 2>/dev/null | tail -n +2 | wc -l | tr -d ' '",
        ),
    }

    # Interface table: name, status, IPs
    iface_raw = _try(
        # BSD: parse ifconfig output
        "ifconfig 2>/dev/null | awk '/^[a-z0-9]/{if(iface!=\"\"){printf iface\"\\t\"status\"\\t\"addrs\"\\n\"}; iface=$1; status=\"down\"; addrs=\"\"} /status: active/{status=\"up\"} /status: no carrier/{status=\"no carrier\"} /inet [0-9]/{if($2!=\"127.0.0.1\")addrs=addrs$2\" \"} END{if(iface!=\"\")printf iface\"\\t\"status\"\\t\"addrs\"\\n\"}'",
        # Linux fallback
        "ip -brief addr show 2>/dev/null | awk '{print $1\"\\t\"$2\"\\t\"$3}'",
    )
    ifaces = []
    if iface_raw and not iface_raw.startswith("ERROR"):
        for line in iface_raw.splitlines():
            parts = line.split("\t")
            if len(parts) >= 2:
                ifaces.append({
                    "interface": parts[0].rstrip(":"),
                    "status":    parts[1] if len(parts) > 1 else "",
                    "addresses": parts[2].strip() if len(parts) > 2 else "",
                })
    data["interface_table"] = ifaces

    return data
