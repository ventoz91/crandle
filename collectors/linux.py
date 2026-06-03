from utils.ssh import run_command


def collect_linux(client):

    data = {}

    commands = {
        "hostname": "hostname",
        "os": "cat /etc/os-release | grep PRETTY_NAME | cut -d= -f2",
        "kernel": "uname -r",
        "uptime": "uptime -p",
        "cpu": "lscpu | grep 'Model name' | sed 's/Model name:[[:space:]]*//'",
        "memory": "free -h | grep Mem",
        "disk": "df -h / | tail -1",
        "ip": "hostname -I"
    }

    for key, cmd in commands.items():
        data[key] = run_command(client, cmd)

    docker_output = run_command(
        client,
        "docker ps --format '{{.ID}}|{{.Names}}|{{.Image}}|{{.Status}}|{{.Ports}}' 2>/dev/null"
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
