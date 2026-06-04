from utils.ssh import run_command


def collect_linux(client):
    commands = {
        "hostname":        "hostname",
        "os":              "cat /etc/os-release | grep PRETTY_NAME | cut -d= -f2 | tr -d '\"'",
        "kernel":          "uname -r",
        "arch":            "uname -m",
        "uptime":          "uptime -p",
        "last_boot":       "who -b 2>/dev/null | awk '{print $3, $4}' || uptime -s 2>/dev/null | head -1",
        "load_avg":        "cat /proc/loadavg | awk '{print $1, $2, $3}'",
        "cpu":             "lscpu | grep 'Model name' | sed 's/Model name:[[:space:]]*//'",
        "cpu_cores":       "nproc",
        "memory":          "free -h | awk '/^Mem:/{print $3 \" used / \" $2 \" total\"}'",
        "swap":            "free -h | awk '/^Swap:/{if($2==\"0B\"||$2==\"0\"){print \"none\"}else{print $3\" used / \"$2\" total\"}}'",
        "ip":              "hostname -I | awk '{print $1}'",
        "interfaces":      "ip -brief addr show | grep -v '^lo' | awk '{print $1, $3}' | tr '\n' '  '",
        "dns_servers":     "grep '^nameserver' /etc/resolv.conf 2>/dev/null | awk '{print $2}' | tr '\n' ' ' | sed 's/ $//'",
        "timezone":        "timedatectl show --no-pager --property=Timezone 2>/dev/null | cut -d= -f2 || cat /etc/timezone 2>/dev/null",
        "ntp_sync":        "timedatectl show --no-pager --property=NTPSynchronized 2>/dev/null | cut -d= -f2",
        "virt":            "systemd-detect-virt 2>/dev/null",
        "listening_ports": "ss -tlnp 2>/dev/null | awk 'NR>1 && $1==\"LISTEN\"{split($4,a,\":\"); print a[length(a)]}' | sort -nu | tr '\n' ' ' | sed 's/ $//'",
        "logged_in":       "who | awk '{print $1}' | sort -u | tr '\n' ' ' | sed 's/ $//'",
    }

    data = {}
    for key, cmd in commands.items():
        data[key] = run_command(client, cmd)

    # Package count — try dpkg, rpm, pacman in order
    pkg_out = run_command(
        client,
        "dpkg -l 2>/dev/null | grep -c '^ii' || rpm -qa 2>/dev/null | wc -l | tr -d ' ' || pacman -Q 2>/dev/null | wc -l | tr -d ' '",
    )
    data["packages"] = pkg_out if pkg_out and not pkg_out.startswith("ERROR:") else ""

    # Failed systemd services
    failed_output = run_command(
        client,
        "systemctl list-units --failed --no-legend 2>/dev/null | awk '{print $1}' | tr '\n' ' ' | sed 's/ $//'",
    )
    data["failed_services"] = failed_output if failed_output and not failed_output.startswith("ERROR:") else ""

    # All mounted filesystems (excludes virtual/transient fs types)
    disks_raw = run_command(
        client,
        "df -h --exclude-type=tmpfs --exclude-type=devtmpfs --exclude-type=overlay"
        " --exclude-type=squashfs --exclude-type=efivarfs 2>/dev/null"
        " | awk 'NR>1{print $1\"\\t\"$3\"\\t\"$2\"\\t\"$5\"\\t\"$6}'",
    )
    disks = []
    if disks_raw and not disks_raw.startswith("ERROR:"):
        for line in disks_raw.splitlines():
            parts = line.split("\t")
            if len(parts) == 5:
                disks.append({
                    "device": parts[0], "used": parts[1], "total": parts[2],
                    "pct": parts[3], "mount": parts[4],
                })
    data["all_disks"] = disks

    # Docker containers
    docker_output = run_command(
        client,
        "docker ps --format '{{.ID}}|{{.Names}}|{{.Image}}|{{.Status}}|{{.Ports}}' 2>/dev/null",
    )
    containers = []
    if docker_output and not docker_output.startswith("ERROR:"):
        for line in docker_output.splitlines():
            parts = line.split("|", 4)
            if len(parts) == 5:
                containers.append({
                    "id": parts[0], "name": parts[1], "image": parts[2],
                    "status": parts[3], "ports": parts[4],
                })
    data["docker_containers"] = containers

    return data
