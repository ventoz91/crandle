from utils.ssh import run_command


def collect_macos(client):
    commands = {
        "hostname": "hostname",
        "os": "sw_vers -productName",
        "os_version": "sw_vers -productVersion",
        "kernel": "uname -r",
        "uptime": "uptime | sed 's/.*up /up /' | sed 's/,  [0-9]* user.*//'",
        "cpu": "sysctl -n machdep.cpu.brand_string",
        "memory": "top -l 1 -s 0 | grep PhysMem | sed 's/PhysMem: //'",
        "disk": "df -h / | awk 'NR==2{print $3 \" used / \" $2 \" total (\" $5 \")'\"'\"'}'",
        "ip": "ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || echo N/A",
    }

    data = {}
    for key, cmd in commands.items():
        data[key] = run_command(client, cmd)

    brew_output = run_command(client, "brew list --formula 2>/dev/null | wc -l | tr -d ' '")
    data["brew_packages"] = (
        f"{brew_output.strip()} formulae"
        if brew_output and not brew_output.startswith("ERROR:") and brew_output.strip().isdigit()
        else "brew not found"
    )

    return data
