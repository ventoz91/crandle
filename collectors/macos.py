from utils.ssh import run_command


def collect_macos(client):
    commands = {
        "hostname":    "hostname",
        "os":          "sw_vers -productName",
        "os_version":  "sw_vers -productVersion",
        "os_build":    "sw_vers -buildVersion",
        "kernel":      "uname -r",
        "arch":        "uname -m",
        "model":       "system_profiler SPHardwareDataType 2>/dev/null | awk '/Model Identifier/{print $3}'",
        "serial":      "system_profiler SPHardwareDataType 2>/dev/null | awk '/Serial Number/{print $NF}'",
        "cpu":         "sysctl -n machdep.cpu.brand_string",
        "cpu_cores":   "sysctl -n hw.ncpu",
        "memory":      "top -l 1 -s 0 | grep PhysMem | sed 's/PhysMem: //'",
        "memory_total":"sysctl -n hw.memsize | awk '{printf \"%.1f GB\", $1/1073741824}'",
        "uptime":      "uptime | sed 's/.*up /up /' | sed 's/,  [0-9]* user.*//'",
        "ip":          "ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || echo N/A",
        "interfaces":  "ifconfig | awk '/^[a-z0-9]/{iface=$1} /inet [0-9]/{if($2!=\"127.0.0.1\")printf iface\" \"$2\"  \"}' | sed 's/ $//'",
        "dns_servers": "grep '^nameserver' /etc/resolv.conf 2>/dev/null | awk '{print $2}' | tr '\n' ' ' | sed 's/ $//'",
        "timezone":    "readlink /etc/localtime | sed 's|.*/zoneinfo/||'",
        "filevault":   "fdesetup status 2>/dev/null | head -1",
    }

    data = {}
    for key, cmd in commands.items():
        data[key] = run_command(client, cmd)

    # Homebrew formulae
    brew_out = run_command(client, "brew list --formula 2>/dev/null | wc -l | tr -d ' '")
    data["brew_formulae"] = (
        f"{brew_out.strip()} formulae"
        if brew_out and not brew_out.startswith("ERROR:") and brew_out.strip().isdigit()
        else "brew not found"
    )

    # Homebrew casks
    cask_out = run_command(client, "brew list --cask 2>/dev/null | wc -l | tr -d ' '")
    data["brew_casks"] = (
        f"{cask_out.strip()} casks"
        if cask_out and not cask_out.startswith("ERROR:") and cask_out.strip().isdigit()
        else ""
    )

    # All mounted filesystems
    disks_raw = run_command(
        client,
        "df -h | grep -v devfs | grep -v map | grep -v autofs | awk 'NR>1{print $1\"\\t\"$3\"\\t\"$2\"\\t\"$5\"\\t\"$9}'",
    )
    disks = []
    if disks_raw and not disks_raw.startswith("ERROR:"):
        for line in disks_raw.splitlines():
            parts = line.split("\t")
            if len(parts) == 5 and parts[4]:
                disks.append({
                    "device": parts[0], "used": parts[1], "total": parts[2],
                    "pct": parts[3], "mount": parts[4],
                })
    data["all_disks"] = disks

    return data
