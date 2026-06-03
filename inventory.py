import argparse
import yaml

from rich.console import Console
from rich.table import Table

from utils.ssh import connect
from utils.report import write_report, write_master_report
from collectors.linux import collect_linux
from collectors.proxmox import collect_proxmox


console = Console()


def linux_to_markdown(data):
    md = []
    md.append(f"# {data['hostname']}")
    md.append("")
    md.append("| Property | Value |")
    md.append("|----------|-------|")
    for key, value in data.items():
        if key in ("hostname", "docker_containers"):
            continue
        md.append(f"| {key} | {value} |")
    md.append("")

    if data.get("docker_containers"):
        md.append("### Docker Containers")
        md.append("")
        md.append("| ID | Name | Image | Status | Ports |")
        md.append("|----|------|-------|--------|-------|")
        for ct in data["docker_containers"]:
            md.append(f"| {ct['id']} | {ct['name']} | {ct['image']} | {ct['status']} | {ct['ports']} |")
        md.append("")

    md.append("---")
    md.append("")
    return "\n".join(md)


def proxmox_to_markdown(data):
    md = []
    md.append(f"# Proxmox Host - {data['host']}")
    md.append("")

    for node in data["nodes"]:
        md.append(f"## Node: {node['name']}")
        md.append("")
        md.append(f"- Status: {node['status']}")
        md.append(f"- CPU Usage: {node['cpu']}")
        md.append(f"- Memory: {node['memory_used']} / {node['memory_total']}")
        md.append(f"- Disk: {node['disk_used']} / {node['disk_total']}")
        md.append(f"- Uptime: {node['uptime']}")
        md.append("")

        md.append("### Virtual Machines")
        md.append("")
        md.append("| VMID | Name | Status | CPUs | Memory | Uptime |")
        md.append("|------|------|--------|------|--------|--------|")
        for vm in node["vms"]:
            md.append(
                f"| {vm['vmid']} | {vm['name']} | {vm['status']} |"
                f" {vm['cpus']} | {vm['memory']} / {vm['max_memory']} | {vm['uptime']} |"
            )
        md.append("")

        md.append("### LXC Containers")
        md.append("")
        md.append("| VMID | Name | Status | CPUs | Memory | Uptime |")
        md.append("|------|------|--------|------|--------|--------|")
        for ct in node["lxc"]:
            md.append(
                f"| {ct['vmid']} | {ct['name']} | {ct['status']} |"
                f" {ct['cpus']} | {ct['memory']} / {ct['max_memory']} | {ct['uptime']} |"
            )
        md.append("")

        md.append("### Storage")
        md.append("")
        md.append("| Name | Type | Used | Total | Available |")
        md.append("|------|------|------|-------|-----------|")
        for s in node["storage"]:
            md.append(
                f"| {s['name']} | {s['type']} | {s['used']} |"
                f" {s['total']} | {s['available']} |"
            )
        md.append("")
        md.append("---")
        md.append("")

    return "\n".join(md)


def load_inventory(path="inventory.yml"):
    with open(path, "r") as f:
        return yaml.safe_load(f)


def display_linux(data):
    table = Table(title=f"Linux Host: {data['hostname']}")
    table.add_column("Property")
    table.add_column("Value")
    for key, value in data.items():
        if key == "docker_containers":
            continue
        table.add_row(key, str(value))
    console.print(table)

    if data.get("docker_containers"):
        docker_table = Table(title=f"Docker Containers on {data['hostname']}")
        docker_table.add_column("ID")
        docker_table.add_column("Name")
        docker_table.add_column("Image")
        docker_table.add_column("Status")
        docker_table.add_column("Ports")
        for ct in data["docker_containers"]:
            docker_table.add_row(ct["id"], ct["name"], ct["image"], ct["status"], ct["ports"])
        console.print(docker_table)


def display_proxmox(data):
    for node in data["nodes"]:
        table = Table(title=f"Proxmox Node: {node['name']}")
        table.add_column("Property")
        table.add_column("Value")
        table.add_row("Status", str(node["status"]))
        table.add_row("CPU Usage", str(node["cpu"]))
        table.add_row("Memory", f"{node['memory_used']} / {node['memory_total']}")
        table.add_row("Disk", f"{node['disk_used']} / {node['disk_total']}")
        table.add_row("Uptime", str(node["uptime"]))
        console.print(table)

        vm_table = Table(title=f"VMs on {node['name']}")
        vm_table.add_column("VMID")
        vm_table.add_column("Name")
        vm_table.add_column("Status")
        vm_table.add_column("CPUs")
        vm_table.add_column("Memory")
        vm_table.add_column("Uptime")
        for vm in node["vms"]:
            vm_table.add_row(
                str(vm["vmid"]),
                str(vm["name"]),
                str(vm["status"]),
                str(vm["cpus"]),
                f"{vm['memory']} / {vm['max_memory']}",
                str(vm["uptime"]),
            )
        console.print(vm_table)

        lxc_table = Table(title=f"LXC Containers on {node['name']}")
        lxc_table.add_column("VMID")
        lxc_table.add_column("Name")
        lxc_table.add_column("Status")
        lxc_table.add_column("CPUs")
        lxc_table.add_column("Memory")
        lxc_table.add_column("Uptime")
        for ct in node["lxc"]:
            lxc_table.add_row(
                str(ct["vmid"]),
                str(ct["name"]),
                str(ct["status"]),
                str(ct["cpus"]),
                f"{ct['memory']} / {ct['max_memory']}",
                str(ct["uptime"]),
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
                str(s["name"]),
                str(s["type"]),
                str(s["used"]),
                str(s["total"]),
                str(s["available"]),
            )
        console.print(storage_table)


def main():
    parser = argparse.ArgumentParser(
        prog="inventory.py",
        description="Crandle — homelab inventory scanner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples:\n"
            "  python inventory.py                        scan all hosts, save timestamped report\n"
            "  python inventory.py --master               scan and update master HardwareSurvey.md\n"
            "  python inventory.py --no-report            display only, write nothing\n"
            "  python inventory.py --inventory ~/lab.yml  use a custom inventory file\n"
        ),
    )
    parser.add_argument(
        "--master",
        action="store_true",
        help="overwrite HardwareSurvey.md and save a timestamped archive",
    )
    parser.add_argument(
        "--no-report",
        action="store_true",
        help="display results in the terminal only, do not write any report files",
    )
    parser.add_argument(
        "--inventory",
        metavar="FILE",
        default="inventory.yml",
        help="path to inventory file (default: inventory.yml)",
    )
    args = parser.parse_args()

    report_sections = []

    try:
        inventory = load_inventory(args.inventory)

        for host in inventory.get("linux", []):
            console.print(f"\n[cyan]Connecting to Linux host {host['host']}[/cyan]")
            try:
                client = connect(host["host"], host["user"])
                data = collect_linux(client)
                display_linux(data)
                report_sections.append(linux_to_markdown(data))
                client.close()
            except Exception as e:
                console.print(f"[red]Failed Linux host {host['host']}[/red]")
                console.print(str(e))

        for host in inventory.get("proxmox", []):
            console.print(f"\n[cyan]Connecting to Proxmox host {host['host']}[/cyan]")
            try:
                data = collect_proxmox(host)
                display_proxmox(data)
                report_sections.append(proxmox_to_markdown(data))
            except Exception as e:
                console.print(f"[red]Failed Proxmox host {host['host']}[/red]")
                console.print(str(e))

        if report_sections and not args.no_report:
            full_report = "\n".join(report_sections)
            if args.master:
                master_path = write_master_report(full_report)
                console.print(f"\n[green]Master report updated:[/green] {master_path}")
                archive_path = write_report(full_report)
                console.print(f"[green]Archive saved:[/green] {archive_path}")
            else:
                report_path = write_report(full_report)
                console.print(f"\n[green]Report saved:[/green] {report_path}")
        elif not report_sections:
            console.print("\n[yellow]No data collected.[/yellow]")

    except KeyboardInterrupt:
        console.print("\n[yellow]Inventory scan cancelled by user.[/yellow]")
    except Exception as e:
        console.print(f"[red]Fatal error:[/red] {e}")


if __name__ == "__main__":
    main()
