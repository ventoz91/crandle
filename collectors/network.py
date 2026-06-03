import base64

from utils.ssh import run_command


def collect_network(client):
    """
    SSH collector for network appliances (OPNsense, pfSense, OpenWrt, etc.).

    Commands are base64-encoded before sending so they arrive in /bin/sh verbatim,
    bypassing any quoting or expansion done by tcsh (OPNsense/pfSense login shell).
    BSD-native tools (ifconfig, netstat) are tried first; Linux tools (ip) are the fallback.
    """

    def sh(cmd: str) -> str:
        b64 = base64.b64encode(cmd.encode()).decode()
        return run_command(client, f"echo {b64} | base64 -d | sh")

    def _try(*cmds: str) -> str:
        """Run each command in order, returning the first non-empty non-error result."""
        for cmd in cmds:
            out = sh(cmd)
            if out and not out.startswith("ERROR"):
                return out
        return ""

    data = {
        "hostname":     sh("hostname -s 2>/dev/null || hostname"),
        "platform":     sh("uname -sr"),
        "uptime":       sh("uptime"),
        "ip_addresses": _try(
            # BSD / OPNsense primary
            "ifconfig 2>/dev/null | awk '/inet [0-9]/{if($2!=\"127.0.0.1\")printf $2\" \"}'",
            # Linux fallback
            "ip -brief addr show 2>/dev/null | awk '$1!=\"lo\"{printf $3\" \"}'",
        ),
        "routing_table": _try(
            # BSD / OPNsense primary
            "netstat -rn 2>/dev/null | head -15",
            # Linux fallback
            "ip route show 2>/dev/null | head -10",
        ),
        "arp_entries": _try(
            # BSD: arp -a lists all, count lines
            "arp -a 2>/dev/null | wc -l | tr -d ' '",
            # Linux fallback
            "arp -n 2>/dev/null | tail -n +2 | wc -l | tr -d ' '",
        ),
    }

    return data
