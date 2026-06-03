import shlex

from utils.ssh import run_command


def collect_network(client):
    """
    Basic SSH collector for network appliances running Linux/BSD (pfSense, OPNsense, OpenWrt, etc.).
    Commands are intentionally simple and broadly compatible; vendor CLI devices will connect
    successfully but may return unparseable output for some fields.
    All commands are wrapped in 'sh -c' to avoid issues with tcsh login shells (e.g. OPNsense).
    """
    commands = {
        "hostname": "hostname",
        "platform": "uname -sr || echo unknown",
        "uptime": "uptime",
        "ip_addresses": (
            "ip -brief addr show 2>/dev/null | grep -v '^lo' | awk '{print $1, $3}' | tr '\\n' ' '"
            " || ifconfig 2>/dev/null | grep 'inet ' | grep -v 127 | awk '{print $2}' | tr '\\n' ' '"
        ),
        "routing_table": (
            "ip route show 2>/dev/null | head -10"
            " || netstat -rn 2>/dev/null | head -15"
        ),
        "arp_entries": "arp -n 2>/dev/null | grep -v '^?' | wc -l | tr -d ' '",
    }

    data = {}
    for key, cmd in commands.items():
        data[key] = run_command(client, "sh -c " + shlex.quote(cmd))

    return data
