from utils.report import md_escape

_LINUX_SKIP   = {"hostname", "docker_containers", "failed_services", "all_disks", "docker_compose_files", "notes"}
_MACOS_SKIP   = {"hostname", "all_disks"}
_NETWORK_SKIP = {"hostname", "interface_table"}
_SNMP_SKIP    = {"hostname", "port_map", "vlan_list"}
_SNMP_LABELS  = {
    "description": "Description", "uptime": "Uptime", "ip_address": "IP Address",
    "contact": "Contact", "location": "Location",
    "ports": "Ports", "mac_entries": "MAC Table Entries",
}
_WIN_SKIP = {"hostname", "running_services", "all_drives", "network_adapters"}


def _notes_block(notes, heading="### Collector Notes"):
    if not notes:
        return []
    md = [heading, ""]
    for n in notes:
        md.append(f"- {md_escape(n)}")
    md.append("")
    return md


def linux_to_markdown(data):
    md = [f"## {data['hostname']}", ""]
    md += ["| Property | Value |", "|----------|-------|"]
    for key, value in data.items():
        if key in _LINUX_SKIP:
            continue
        md.append(f"| {key} | {md_escape(value)} |")
    md.append("")

    if data.get("all_disks"):
        md += ["### Disks", "", "| Device | Used | Total | Use% | Mount |",
               "|--------|------|-------|------|-------|"]
        for d in data["all_disks"]:
            md.append(f"| {md_escape(d['device'])} | {md_escape(d['used'])} | {md_escape(d['total'])} | {md_escape(d['pct'])} | {md_escape(d['mount'])} |")
        md.append("")

    if data.get("failed_services"):
        md += ["### Failed Services", "", f"```\n{data['failed_services']}\n```", ""]

    if data.get("docker_containers"):
        md += [
            "### Docker Containers", "",
            "| ID | Name | Image | Status | Ports |",
            "|----|------|-------|--------|-------|",
        ]
        for ct in data["docker_containers"]:
            md.append(f"| {md_escape(ct['id'])} | {md_escape(ct['name'])} | {md_escape(ct['image'])} | {md_escape(ct['status'])} | {md_escape(ct['ports'])} |")
        md.append("")

    if data.get("docker_compose_files"):
        for cf in data["docker_compose_files"]:
            md += [f"### Docker Compose — `{cf['path']}`", "", "```yaml", cf["content"], "```", ""]

    md += _notes_block(data.get("notes"))

    md += ["---", ""]
    return "\n".join(md)


def macos_to_markdown(data):
    md = [f"## {data['hostname']} (macOS)", ""]
    md += ["| Property | Value |", "|----------|-------|"]
    for key, value in data.items():
        if key in _MACOS_SKIP:
            continue
        md.append(f"| {key} | {md_escape(value)} |")
    md.append("")

    if data.get("all_disks"):
        md += ["### Disks", "", "| Device | Used | Total | Use% | Mount |",
               "|--------|------|-------|------|-------|"]
        for d in data["all_disks"]:
            md.append(f"| {md_escape(d['device'])} | {md_escape(d['used'])} | {md_escape(d['total'])} | {md_escape(d['pct'])} | {md_escape(d['mount'])} |")
        md.append("")

    md += ["---", ""]
    return "\n".join(md)


def network_to_markdown(data):
    md = [f"## {data.get('hostname', 'Network Device')}", ""]
    md += ["| Property | Value |", "|----------|-------|"]
    for key, value in data.items():
        if key in _NETWORK_SKIP:
            continue
        label = key.replace("_", " ").title()
        md.append(f"| {label} | {md_escape(value)} |")
    md.append("")

    if data.get("interface_table"):
        md += ["### Interfaces", "", "| Interface | Status | Addresses |",
               "|-----------|--------|-----------|"]
        for iface in data["interface_table"]:
            md.append(f"| {md_escape(iface['interface'])} | {md_escape(iface['status'])} | {md_escape(iface['addresses'])} |")
        md.append("")

    md += ["---", ""]
    return "\n".join(md)


def proxmox_to_markdown(data):
    md = [f"## Proxmox — {data['host']}", ""]
    if data.get("api_version"):
        md.append(f"API version: {data['api_version']}")
        md.append("")

    for node in data["nodes"]:
        extras = []
        if node.get("pve_version"):
            extras.append(f"PVE: {node['pve_version']}")
        if node.get("kernel"):
            extras.append(f"Kernel: {node['kernel']}")
        if node.get("cpu_model"):
            extras.append(f"CPU: {node['cpu_model']} ({node.get('cpu_count', '')} threads)")

        md += [
            f"### Node: {node['name']}", "",
            f"- Status: {node['status']}",
            f"- CPU Usage: {node['cpu']}",
            f"- Memory: {node['memory_used']} / {node['memory_total']}",
            f"- Disk: {node['disk_used']} / {node['disk_total']}",
            f"- Uptime: {node['uptime']}",
        ]
        for e in extras:
            md.append(f"- {e}")
        md += [
            "",
            "#### Virtual Machines", "",
            "| VMID | Name | Status | Tags | CPUs | Memory | Uptime | Snapshots | Guest IPs |",
            "|------|------|--------|------|------|--------|--------|-----------|-----------|",
        ]
        for vm in node["vms"]:
            md.append(
                f"| {vm['vmid']} | {md_escape(vm['name'])} | {vm['status']} | {md_escape(vm.get('tags',''))} |"
                f" {vm['cpus']} | {vm['memory']} / {vm['max_memory']} | {vm['uptime']} |"
                f" {vm.get('snapshots', '')} | {md_escape(vm.get('guest_ips', ''))} |"
            )
        md += [
            "",
            "#### LXC Containers", "",
            "| VMID | Name | Status | Tags | CPUs | Memory | Uptime | IP |",
            "|------|------|--------|------|------|--------|--------|----|",
        ]
        for ct in node["lxc"]:
            md.append(
                f"| {ct['vmid']} | {md_escape(ct['name'])} | {ct['status']} | {md_escape(ct.get('tags',''))} |"
                f" {ct['cpus']} | {ct['memory']} / {ct['max_memory']} | {ct['uptime']} |"
                f" {md_escape(ct.get('ip', ''))} |"
            )
        md += [
            "",
            "#### Storage", "",
            "| Name | Type | Used | Total | Available |",
            "|------|------|------|-------|-----------|",
        ]
        for s in node["storage"]:
            md.append(f"| {md_escape(s['name'])} | {s['type']} | {s['used']} | {s['total']} | {s['available']} |")
        md.append("")

        md += _notes_block(node.get("notes"), heading="#### Collector Notes")

    md += ["---", ""]
    return "\n".join(md)


def snmp_to_markdown(data):
    md = [f"## {data['hostname']} (switch/snmp)", ""]
    md += ["| Property | Value |", "|----------|-------|"]
    for key, value in data.items():
        if key in _SNMP_SKIP:
            continue
        label = _SNMP_LABELS.get(key, key.replace("_", " ").title())
        md.append(f"| {label} | {md_escape(value)} |")
    md.append("")

    if data.get("vlan_list"):
        md += ["### VLANs", "", "| VLAN ID | Name |", "|---------|------|"]
        for v in data["vlan_list"]:
            md.append(f"| {v['id']} | {md_escape(v['name'])} |")
        md.append("")

    if data.get("port_map"):
        md += ["### Port Map", "", "| Port | Speed | MAC | IP |", "|------|-------|-----|-----|"]
        for entry in data["port_map"]:
            md.append(f"| {md_escape(entry['port'])} | {md_escape(entry.get('speed',''))} | {md_escape(entry['mac'])} | {md_escape(entry.get('ip', ''))} |")
        md.append("")

    md += ["---", ""]
    return "\n".join(md)


def switch_to_markdown(data):
    md = [f"## {data['hostname']} (switch)", ""]
    md += ["| Property | Value |", "|----------|-------|"]
    labels = {
        "model": "Model", "firmware": "Firmware", "serial": "Serial",
        "mac_address": "MAC Address", "uptime": "Uptime", "ip_address": "IP Address",
        "gateway": "Default Gateway", "ports": "Ports", "mac_entries": "MAC Table Entries",
    }
    for key, value in data.items():
        if key == "hostname":
            continue
        label = labels.get(key, key.replace("_", " ").title())
        md.append(f"| {label} | {md_escape(value)} |")
    md += ["", "---", ""]
    return "\n".join(md)


def windows_to_markdown(data):
    md = [f"## {data['hostname']} (Windows)", ""]
    md += ["| Property | Value |", "|----------|-------|"]
    for key, value in data.items():
        if key in _WIN_SKIP:
            continue
        md.append(f"| {key} | {md_escape(value)} |")
    md.append("")

    if data.get("all_drives"):
        md += ["### Drives", "", "| Drive | Used | Total |", "|-------|------|-------|"]
        for d in data["all_drives"]:
            md.append(f"| {md_escape(d['drive'])}: | {md_escape(d['used'])} | {md_escape(d['total'])} |")
        md.append("")

    if data.get("network_adapters"):
        md += ["### Network Adapters", "",
               "| Name | MAC | Speed | Description |",
               "|------|-----|-------|-------------|"]
        for a in data["network_adapters"]:
            md.append(f"| {md_escape(a['name'])} | {md_escape(a['mac'])} | {md_escape(a['speed'])} | {md_escape(a['description'])} |")
        md.append("")

    if data.get("running_services"):
        md += ["### Running Services (non-Microsoft)", ""]
        for svc in data["running_services"]:
            md.append(f"- {svc}")
        md.append("")

    md += ["---", ""]
    return "\n".join(md)


def role_to_markdown(role_name: str, host_sections: list) -> str:
    return f"# {role_name.title()}\n\n" + "\n".join(host_sections)


MARKDOWN_FNS = {
    "linux":   linux_to_markdown,
    "macos":   macos_to_markdown,
    "network": network_to_markdown,
    "proxmox": proxmox_to_markdown,
    "snmp":    snmp_to_markdown,
    "switch":  switch_to_markdown,
    "windows": windows_to_markdown,
}
