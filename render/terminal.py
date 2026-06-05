from rich.console import Console
from rich.table import Table

from render.markdown import _LINUX_SKIP, _MACOS_SKIP, _NETWORK_SKIP, _SNMP_SKIP, _SNMP_LABELS, _WIN_SKIP

console = Console()


def _status_style(status: str) -> str:
    s = str(status).lower()
    if s in ("running", "online", "up"):
        return f"[green]{status}[/green]"
    if s in ("stopped", "offline", "down", "error", "failed"):
        return f"[red]{status}[/red]"
    return str(status)


def display_linux(data):
    table = Table(title=f"Linux Host: {data['hostname']}")
    table.add_column("Property")
    table.add_column("Value")
    for key, value in data.items():
        if key in _LINUX_SKIP:
            continue
        table.add_row(key, str(value))
    console.print(table)

    if data.get("all_disks"):
        disk_table = Table(title=f"Disks on {data['hostname']}")
        disk_table.add_column("Device")
        disk_table.add_column("Used")
        disk_table.add_column("Total")
        disk_table.add_column("Use%")
        disk_table.add_column("Mount")
        for d in data["all_disks"]:
            disk_table.add_row(d["device"], d["used"], d["total"], d["pct"], d["mount"])
        console.print(disk_table)

    if data.get("failed_services"):
        console.print(f"[red]  Failed services:[/red] {data['failed_services']}")

    if data.get("docker_containers"):
        docker_table = Table(title=f"Docker Containers on {data['hostname']}")
        docker_table.add_column("ID")
        docker_table.add_column("Name")
        docker_table.add_column("Image")
        docker_table.add_column("Status")
        docker_table.add_column("Ports")
        for ct in data["docker_containers"]:
            status = ct["status"]
            styled = f"[green]{status}[/green]" if "Up" in status else f"[red]{status}[/red]"
            docker_table.add_row(ct["id"], ct["name"], ct["image"], styled, ct["ports"])
        console.print(docker_table)

    if data.get("docker_compose_files"):
        for cf in data["docker_compose_files"]:
            console.print(f"\n[bold]Docker Compose:[/bold] {cf['path']}\n{cf['content']}")


def display_macos(data):
    table = Table(title=f"macOS Host: {data['hostname']}")
    table.add_column("Property")
    table.add_column("Value")
    for key, value in data.items():
        if key in _MACOS_SKIP:
            continue
        table.add_row(key, str(value))
    console.print(table)

    if data.get("all_disks"):
        disk_table = Table(title=f"Disks on {data['hostname']}")
        disk_table.add_column("Device")
        disk_table.add_column("Used")
        disk_table.add_column("Total")
        disk_table.add_column("Use%")
        disk_table.add_column("Mount")
        for d in data["all_disks"]:
            disk_table.add_row(d["device"], d["used"], d["total"], d["pct"], d["mount"])
        console.print(disk_table)


def display_network(data):
    table = Table(title=f"Network Device: {data.get('hostname', 'unknown')}")
    table.add_column("Property")
    table.add_column("Value")
    for key, value in data.items():
        if key in _NETWORK_SKIP:
            continue
        table.add_row(key.replace("_", " ").title(), str(value))
    console.print(table)

    if data.get("interface_table"):
        iface_table = Table(title=f"Interfaces: {data.get('hostname', '')}")
        iface_table.add_column("Interface")
        iface_table.add_column("Status")
        iface_table.add_column("Addresses")
        for iface in data["interface_table"]:
            status = iface["status"]
            styled = f"[green]{status}[/green]" if "up" in status.lower() else f"[red]{status}[/red]"
            iface_table.add_row(iface["interface"], styled, iface["addresses"])
        console.print(iface_table)


def display_proxmox(data):
    for node in data["nodes"]:
        table = Table(title=f"Proxmox Node: {node['name']}")
        table.add_column("Property")
        table.add_column("Value")
        table.add_row("Status",     _status_style(node["status"]))
        table.add_row("CPU Usage",  str(node["cpu"]))
        table.add_row("Memory",     f"{node['memory_used']} / {node['memory_total']}")
        table.add_row("Disk",       f"{node['disk_used']} / {node['disk_total']}")
        table.add_row("Uptime",     str(node["uptime"]))
        if node.get("pve_version"):
            table.add_row("PVE Version", str(node["pve_version"]))
        if node.get("kernel"):
            table.add_row("Kernel",      str(node["kernel"]))
        if node.get("cpu_model"):
            table.add_row("CPU",         f"{node['cpu_model']} ({node.get('cpu_count','')} threads)")
        console.print(table)

        vm_table = Table(title=f"VMs on {node['name']}")
        vm_table.add_column("VMID")
        vm_table.add_column("Name")
        vm_table.add_column("Status")
        vm_table.add_column("Tags")
        vm_table.add_column("CPUs")
        vm_table.add_column("Memory")
        vm_table.add_column("Uptime")
        vm_table.add_column("Snaps")
        vm_table.add_column("Guest IPs")
        for vm in node["vms"]:
            vm_table.add_row(
                str(vm["vmid"]), str(vm["name"]), _status_style(vm["status"]),
                str(vm.get("tags", "")), str(vm["cpus"]),
                f"{vm['memory']} / {vm['max_memory']}", str(vm["uptime"]),
                str(vm.get("snapshots", "")), str(vm.get("guest_ips", "")),
            )
        console.print(vm_table)

        lxc_table = Table(title=f"LXC Containers on {node['name']}")
        lxc_table.add_column("VMID")
        lxc_table.add_column("Name")
        lxc_table.add_column("Status")
        lxc_table.add_column("Tags")
        lxc_table.add_column("CPUs")
        lxc_table.add_column("Memory")
        lxc_table.add_column("Uptime")
        lxc_table.add_column("IP")
        for ct in node["lxc"]:
            lxc_table.add_row(
                str(ct["vmid"]), str(ct["name"]), _status_style(ct["status"]),
                str(ct.get("tags", "")), str(ct["cpus"]),
                f"{ct['memory']} / {ct['max_memory']}", str(ct["uptime"]),
                str(ct.get("ip", "")),
            )
        console.print(lxc_table)

        storage_table = Table(title=f"Storage on {node['name']}")
        storage_table.add_column("Name")
        storage_table.add_column("Type")
        storage_table.add_column("Used")
        storage_table.add_column("Total")
        storage_table.add_column("Available")
        for s in node["storage"]:
            storage_table.add_row(
                str(s["name"]), str(s["type"]), str(s["used"]), str(s["total"]), str(s["available"]),
            )
        console.print(storage_table)


def display_snmp(data):
    table = Table(title=f"Switch: {data['hostname']} (SNMP)")
    table.add_column("Property")
    table.add_column("Value")
    for key, value in data.items():
        if key in _SNMP_SKIP:
            continue
        label = _SNMP_LABELS.get(key, key.replace("_", " ").title())
        table.add_row(label, str(value))
    console.print(table)

    if data.get("vlan_list"):
        vlan_table = Table(title=f"VLANs: {data['hostname']}")
        vlan_table.add_column("VLAN ID")
        vlan_table.add_column("Name")
        for v in data["vlan_list"]:
            vlan_table.add_row(v["id"], v["name"])
        console.print(vlan_table)

    if data.get("port_map"):
        port_table = Table(title=f"Port Map: {data['hostname']}")
        port_table.add_column("Port")
        port_table.add_column("Speed")
        port_table.add_column("MAC")
        port_table.add_column("IP")
        for entry in data["port_map"]:
            port_table.add_row(entry["port"], entry.get("speed", ""), entry["mac"], entry.get("ip", ""))
        console.print(port_table)


def display_switch(data):
    table = Table(title=f"Switch: {data['hostname']}")
    table.add_column("Property")
    table.add_column("Value")
    labels = {
        "model": "Model", "firmware": "Firmware", "serial": "Serial",
        "mac_address": "MAC Address", "uptime": "Uptime", "ip_address": "IP Address",
        "gateway": "Default Gateway", "ports": "Ports", "mac_entries": "MAC Table Entries",
    }
    for key, value in data.items():
        if key == "hostname":
            continue
        label = labels.get(key, key.replace("_", " ").title())
        table.add_row(label, str(value))
    console.print(table)


def display_windows(data):
    table = Table(title=f"Windows Host: {data['hostname']}")
    table.add_column("Property")
    table.add_column("Value")
    for key, value in data.items():
        if key in _WIN_SKIP:
            continue
        table.add_row(key, str(value))
    console.print(table)

    if data.get("all_drives"):
        drive_table = Table(title=f"Drives on {data['hostname']}")
        drive_table.add_column("Drive")
        drive_table.add_column("Used")
        drive_table.add_column("Total")
        for d in data["all_drives"]:
            drive_table.add_row(f"{d['drive']}:", d["used"], d["total"])
        console.print(drive_table)

    if data.get("network_adapters"):
        adapter_table = Table(title=f"Network Adapters on {data['hostname']}")
        adapter_table.add_column("Name")
        adapter_table.add_column("MAC")
        adapter_table.add_column("Speed")
        adapter_table.add_column("Description")
        for a in data["network_adapters"]:
            adapter_table.add_row(a["name"], a["mac"], a["speed"], a["description"])
        console.print(adapter_table)

    if data.get("running_services"):
        svc_table = Table(title=f"Running Services (non-Microsoft) on {data['hostname']}")
        svc_table.add_column("Service")
        for svc in data["running_services"]:
            svc_table.add_row(svc)
        console.print(svc_table)


def display_summary(results: list):
    table = Table(title="Scan Summary", show_lines=False)
    table.add_column("Role")
    table.add_column("Host")
    table.add_column("Type")
    table.add_column("Status")
    table.add_column("Details")

    for role, host_type, collector, host_addr, data, err in results:
        if err:
            table.add_row(role, host_addr, host_type, "[red]failed[/red]", str(err)[:60])
        elif collector in ("linux", "macos"):
            table.add_row(
                role, data.get("hostname", host_addr), host_type,
                "[green]up[/green]",
                f"{data.get('uptime', '')}  |  {data.get('memory', '')}",
            )
        elif collector == "windows":
            table.add_row(
                role, data.get("hostname", host_addr), host_type,
                "[green]up[/green]",
                f"{data.get('os', '')}  |  {data.get('memory', '')}",
            )
        elif collector == "network":
            table.add_row(
                role, data.get("hostname", host_addr), host_type,
                "[green]up[/green]",
                f"{data.get('platform', '')}  |  {data.get('uptime', '')}",
            )
        elif collector == "snmp":
            table.add_row(
                role, data.get("hostname", host_addr), host_type,
                "[green]up[/green]",
                f"{data.get('uptime', '')}  |  {data.get('ports', '')}  |  {data.get('mac_entries', '')} MACs",
            )
        elif collector == "switch":
            table.add_row(
                role, data.get("hostname", host_addr), host_type,
                "[green]up[/green]",
                f"{data.get('model', '')}  |  {data.get('uptime', '')}  |  {data.get('ports', '')}",
            )
        elif collector == "proxmox":
            for node in data.get("nodes", []):
                vms_running = sum(1 for v in node.get("vms", []) if v.get("status") == "running")
                lxc_running = sum(1 for c in node.get("lxc", []) if c.get("status") == "running")
                table.add_row(
                    role, node["name"], host_type,
                    _status_style(node.get("status", "unknown")),
                    f"VMs: {vms_running}/{len(node['vms'])} running  |  LXC: {lxc_running}/{len(node['lxc'])} running",
                )

    console.print(table)


DISPLAY_FNS = {
    "linux":   display_linux,
    "macos":   display_macos,
    "network": display_network,
    "proxmox": display_proxmox,
    "snmp":    display_snmp,
    "switch":  display_switch,
    "windows": display_windows,
}
