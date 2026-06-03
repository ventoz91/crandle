from utils.ssh import run_command


def collect_linux(client):
    commands = {
        "hostname": "hostname",
        "os": "cat /etc/os-release | grep PRETTY_NAME | cut -d= -f2 | tr -d '\"'",
        "kernel": "uname -r",
        "uptime": "uptime -p",
        "load_avg": "cat /proc/loadavg | awk '{print $1, $2, $3}'",
        "cpu": "lscpu | grep 'Model name' | sed 's/Model name:[[:space:]]*//'",
        "memory": "free -h | awk '/^Mem:/{print $3 \" used / \" $2 \" total\"}'",
        "disk": "df -h / | awk 'NR==2{print $3 \" used / \" $2 \" total (\" $5 \")\"}'",
        "ip": "hostname -I | awk '{print $1}'",
        "interfaces": "ip -brief addr show | grep -v '^lo' | awk '{print $1, $3}' | tr '\n' '  '",
        "logged_in": "who | awk '{print $1}' | sort -u | tr '\n' ' ' | sed 's/ $//'",
    }

    data = {}
    for key, cmd in commands.items():
        data[key] = run_command(client, cmd)

    failed_output = run_command(
        client,
        "systemctl list-units --failed --no-legend 2>/dev/null | awk '{print $1}' | tr '\n' ' ' | sed 's/ $//'",
    )
    data["failed_services"] = failed_output if failed_output and not failed_output.startswith("ERROR:") else ""

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
                    "id": parts[0],
                    "name": parts[1],
                    "image": parts[2],
                    "status": parts[3],
                    "ports": parts[4],
                })

    data["docker_containers"] = containers

    return data
