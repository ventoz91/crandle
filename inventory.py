import argparse
import concurrent.futures
import difflib
import subprocess
import yaml

from rich.console import Console
from rich.table import Table

from utils.ssh import connect
from utils.report import write_report, write_master_report, read_master_report
from collectors.linux import collect_linux
from collectors.macos import collect_macos
from collectors.network import collect_network
from collectors.proxmox import collect_proxmox
from collectors.windows import collect_windows


console = Console()

SCAN_FNS = {}  # populated below after scan_* functions are defined


def _status_style(status: str) -> str:
    s = str(status).lower()
    if s in ("running", "online", "up"):
        return f"[green]{status}[/green]"
    if s in ("stopped", "offline", "down", "error", "failed"):
        return f"[red]{status}[/red]"
    return str(status)


# ---------------------------------------------------------------------------
# Markdown renderers  (## for host, ### for subsections, #### for sub-sub)
# ---------------------------------------------------------------------------

def linux_to_markdown(data):
    md = [f"## {data['hostname']}", ""]
    md += ["| Property | Value |", "|----------|-------|"]
    for key, value in data.items():
        if key in ("hostname", "docker_containers", "failed_services"):
            continue
        md.append(f"| {key} | {value} |")
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
            md.append(f"| {ct['id']} | {ct['name']} | {ct['image']} | {ct['status']} | {ct['ports']} |")
        md.append("")

    md += ["---", ""]
    return "\n".join(md)


def macos_to_markdown(data):
    md = [f"## {data['hostname']} (macOS)", ""]
    md += ["| Property | Value |", "|----------|-------|"]
    for key, value in data.items():
        if key == "hostname":
            continue
        md.append(f"| {key} | {value} |")
    md += ["", "---", ""]
    return "\n".join(md)


def network_to_markdown(data):
    md = [f"## {data.get('hostname', 'Network Device')}", ""]
    md += ["| Property | Value |", "|----------|-------|"]
    for key, value in data.items():
        if key == "hostname":
            continue
        label = key.replace("_", " ").title()
        md.append(f"| {label} | {value} |")
    md += ["", "---", ""]
    return "\n".join(md)


def proxmox_to_markdown(data):
    md = [f"## Proxmox — {data['host']}", ""]

    for node in data["nodes"]:
        md += [
            f"### Node: {node['name']}", "",
            f"- Status: {node['status']}",
            f"- CPU Usage: {node['cpu']}",
            f"- Memory: {node['memory_used']} / {node['memory_total']}",
            f"- Disk: {node['disk_used']} / {node['disk_total']}",
            f"- Uptime: {node['uptime']}", "",
            "#### Virtual Machines", "",
            "| VMID | Name | Status | CPUs | Memory | Uptime |",
            "|------|------|--------|------|--------|--------|",
        ]
        for vm in node["vms"]:
            md.append(
                f"| {vm['vmid']} | {vm['name']} | {vm['status']} |"
                f" {vm['cpus']} | {vm['memory']} / {vm['max_memory']} | {vm['uptime']} |"
            )
        md += [
            "",
            "#### LXC Containers", "",
            "| VMID | Name | Status | CPUs | Memory | Uptime |",
            "|------|------|--------|------|--------|--------|",
        ]
        for ct in node["lxc"]:
            md.append(
                f"| {ct['vmid']} | {ct['name']} | {ct['status']} |"
                f" {ct['cpus']} | {ct['memory']} / {ct['max_memory']} | {ct['uptime']} |"
            )
        md += [
            "",
            "#### Storage", "",
            "| Name | Type | Used | Total | Available |",
            "|------|------|------|-------|-----------|",
        ]
        for s in node["storage"]:
            md.append(
                f"| {s['name']} | {s['type']} | {s['used']} |"
                f" {s['total']} | {s['available']} |"
            )
        md += ["", "---", ""]

    return "\n".join(md)


def windows_to_markdown(data):
    md = [f"## {data['hostname']} (Windows)", ""]
    md += ["| Property | Value |", "|----------|-------|"]
    for key, value in data.items():
        if key == "running_services":
            continue
        md.append(f"| {key} | {value} |")
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


# ---------------------------------------------------------------------------
# Display functions
# ---------------------------------------------------------------------------

def display_linux(data):
    table = Table(title=f"Linux Host: {data['hostname']}")
    table.add_column("Property")
    table.add_column("Value")
    for key, value in data.items():
        if key in ("docker_containers", "failed_services"):
            continue
        table.add_row(key, str(value))
    console.print(table)

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


def display_macos(data):
    table = Table(title=f"macOS Host: {data['hostname']}")
    table.add_column("Property")
    table.add_column("Value")
    for key, value in data.items():
        if key == "hostname":
            continue
        table.add_row(key, str(value))
    console.print(table)


def display_network(data):
    table = Table(title=f"Network Device: {data.get('hostname', 'unknown')}")
    table.add_column("Property")
    table.add_column("Value")
    for key, value in data.items():
        table.add_row(key.replace("_", " ").title(), str(value))
    console.print(table)


def display_proxmox(data):
    for node in data["nodes"]:
        table = Table(title=f"Proxmox Node: {node['name']}")
        table.add_column("Property")
        table.add_column("Value")
        table.add_row("Status", _status_style(node["status"]))
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
                str(vm["vmid"]), str(vm["name"]), _status_style(vm["status"]),
                str(vm["cpus"]), f"{vm['memory']} / {vm['max_memory']}", str(vm["uptime"]),
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
                str(ct["vmid"]), str(ct["name"]), _status_style(ct["status"]),
                str(ct["cpus"]), f"{ct['memory']} / {ct['max_memory']}", str(ct["uptime"]),
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


def display_windows(data):
    table = Table(title=f"Windows Host: {data['hostname']}")
    table.add_column("Property")
    table.add_column("Value")
    for key, value in data.items():
        if key == "running_services":
            continue
        table.add_row(key, str(value))
    console.print(table)

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


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------

def load_inventory(path="inventory.yml"):
    with open(path, "r") as f:
        return yaml.safe_load(f)


def _iter_hosts(inventory: dict):
    """Yield (role, host_type, host_config) for every defined host."""
    for role, host_types in inventory.items():
        if not isinstance(host_types, dict):
            continue
        for host_type, hosts in host_types.items():
            if not isinstance(hosts, list):
                continue
            for h in hosts:
                yield role, host_type, h


def filter_inventory(inventory: dict, host_filter: str) -> dict:
    filtered = {}
    for role, host_type, h in _iter_hosts(inventory):
        if host_filter not in h.get("host", ""):
            continue
        filtered.setdefault(role, {}).setdefault(host_type, []).append(h)
    return filtered


def ping_host(host: str) -> bool:
    try:
        result = subprocess.run(
            ["ping", "-c", "1", "-W", "2", host],
            capture_output=True,
            timeout=5,
        )
        return result.returncode == 0
    except Exception:
        return False


def run_preflight(inventory: dict):
    console.print("\n[bold]Ping check[/bold]")
    table = Table(show_header=True)
    table.add_column("Role")
    table.add_column("Host")
    table.add_column("Type")
    table.add_column("Reachable")

    all_hosts = [(role, host_type, h.get("host", "")) for role, host_type, h in _iter_hosts(inventory)]

    with concurrent.futures.ThreadPoolExecutor() as executor:
        futures = {executor.submit(ping_host, host): (role, host_type, host) for role, host_type, host in all_hosts}
        for future in concurrent.futures.as_completed(futures):
            role, host_type, host = futures[future]
            reachable = future.result()
            table.add_row(role, host, host_type, "[green]yes[/green]" if reachable else "[red]no[/red]")

    console.print(table)


def show_diff(new_report: str):
    old_report = read_master_report()
    if old_report is None:
        console.print("[yellow]No master report exists yet — nothing to diff.[/yellow]")
        return

    old_lines = old_report.splitlines(keepends=True)
    new_lines = new_report.splitlines(keepends=True)
    diff = list(difflib.unified_diff(old_lines, new_lines, fromfile="previous", tofile="current"))

    if not diff:
        console.print("\n[green]No changes detected vs. last master report.[/green]")
        return

    console.print("\n[bold]Changes from last master report:[/bold]")
    for line in diff:
        line = line.rstrip()
        if line.startswith("+") and not line.startswith("+++"):
            console.print(f"[green]{line}[/green]")
        elif line.startswith("-") and not line.startswith("---"):
            console.print(f"[red]{line}[/red]")
        elif line.startswith("@@"):
            console.print(f"[cyan]{line}[/cyan]")


# ---------------------------------------------------------------------------
# Scan functions (run in thread pool)
# ---------------------------------------------------------------------------

def scan_linux(host_config: dict) -> tuple:
    host = host_config["host"]
    client = None
    try:
        client = connect(host, host_config["user"])
        data = collect_linux(client)
        return (host, data, None)
    except Exception as e:
        return (host, None, e)
    finally:
        if client:
            client.close()


def scan_macos(host_config: dict) -> tuple:
    host = host_config["host"]
    client = None
    try:
        client = connect(host, host_config["user"])
        data = collect_macos(client)
        return (host, data, None)
    except Exception as e:
        return (host, None, e)
    finally:
        if client:
            client.close()


def scan_network(host_config: dict) -> tuple:
    host = host_config["host"]
    client = None
    try:
        client = connect(host, host_config["user"])
        data = collect_network(client)
        return (host, data, None)
    except Exception as e:
        return (host, None, e)
    finally:
        if client:
            client.close()


def scan_proxmox(host_config: dict) -> tuple:
    host = host_config["host"]
    try:
        data = collect_proxmox(host_config)
        return (host, data, None)
    except Exception as e:
        return (host, None, e)


def scan_windows(host_config: dict) -> tuple:
    host = host_config["host"]
    client = None
    try:
        client = connect(host, host_config["user"])
        data = collect_windows(client)
        return (host, data, None)
    except Exception as e:
        return (host, None, e)
    finally:
        if client:
            client.close()


SCAN_FNS = {
    "linux": scan_linux,
    "macos": scan_macos,
    "network": scan_network,
    "proxmox": scan_proxmox,
    "windows": scan_windows,
}

MARKDOWN_FNS = {
    "linux": linux_to_markdown,
    "macos": macos_to_markdown,
    "network": network_to_markdown,
    "proxmox": proxmox_to_markdown,
    "windows": windows_to_markdown,
}

DISPLAY_FNS = {
    "linux": display_linux,
    "macos": display_macos,
    "network": display_network,
    "proxmox": display_proxmox,
    "windows": display_windows,
}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        prog="inventory.py",
        description="Crandle — homelab inventory scanner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples:\n"
            "  python inventory.py                        scan all hosts, save timestamped report\n"
            "  python inventory.py --master               scan and update master HardwareSurvey.md\n"
            "  python inventory.py --master --diff        show what changed before overwriting master\n"
            "  python inventory.py --no-report            display only, write nothing\n"
            "  python inventory.py --dry-run              ping hosts and check reachability only\n"
            "  python inventory.py --host 192.168.0.53   scan a single host\n"
            "  python inventory.py --inventory ~/lab.yml  use a custom inventory file\n"
        ),
    )
    parser.add_argument("--master", action="store_true",
                        help="overwrite HardwareSurvey.md and save a timestamped archive")
    parser.add_argument("--no-report", action="store_true",
                        help="display results in the terminal only, do not write any report files")
    parser.add_argument("--dry-run", action="store_true",
                        help="ping all hosts and report reachability without scanning")
    parser.add_argument("--diff", action="store_true",
                        help="show changes compared to the last master report")
    parser.add_argument("--host", metavar="HOST",
                        help="scan only hosts whose address contains HOST (substring match)")
    parser.add_argument("--inventory", metavar="FILE", default="inventory.yml",
                        help="path to inventory file (default: inventory.yml)")
    args = parser.parse_args()

    try:
        inventory = load_inventory(args.inventory)

        if args.host:
            inventory = filter_inventory(inventory, args.host)
            if not inventory:
                console.print(f"[yellow]No hosts matched '{args.host}'.[/yellow]")
                return

        if args.dry_run:
            run_preflight(inventory)
            return

        # Build ordered task list: (fn, host_config, task_key)
        scan_tasks = []
        for role, host_type, h in _iter_hosts(inventory):
            collector = h.get("collector", host_type)
            fn = SCAN_FNS.get(collector)
            if fn is None:
                console.print(f"[yellow]Unknown collector '{collector}' for '{host_type}' in '{role}' — skipping[/yellow]")
                continue
            scan_tasks.append((fn, h, (role, host_type, collector, h["host"])))

        if not scan_tasks:
            console.print("[yellow]No hosts defined in inventory.[/yellow]")
            return

        console.print(f"\n[cyan]Scanning {len(scan_tasks)} host(s) in parallel...[/cyan]")

        results_by_key = {}
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future_to_key = {executor.submit(fn, h): key for fn, h, key in scan_tasks}
            for future in concurrent.futures.as_completed(future_to_key):
                key = future_to_key[future]
                host_addr, data, err = future.result()
                results_by_key[key] = (host_addr, data, err)
                role, host_type, collector, _ = key
                if err:
                    console.print(f"  [red]✗[/red] {host_addr} ({role}/{host_type})")
                else:
                    name = data.get("hostname", host_addr) if collector != "proxmox" else host_addr
                    console.print(f"  [green]✓[/green] {name} ({role}/{host_type})")

        # Display detail tables and build report, both in inventory order
        console.print()
        ordered_results = []
        sections_by_role = {}  # role -> [markdown strings]

        for fn, h, key in scan_tasks:
            role, host_type, collector, host_addr = key
            result = results_by_key.get(key)
            if result is None:
                continue

            _, data, err = result
            ordered_results.append((role, host_type, collector, host_addr, data, err))

            if err:
                console.print(f"[red]Failed {host_type} host {host_addr} ({role}):[/red] {err}")
                continue

            DISPLAY_FNS[collector](data)
            sections_by_role.setdefault(role, []).append(MARKDOWN_FNS[collector](data))

        console.print()
        display_summary(ordered_results)

        if not sections_by_role or args.no_report:
            if not sections_by_role:
                console.print("\n[yellow]No data collected.[/yellow]")
            return

        full_report = "\n\n".join(
            role_to_markdown(role, sections)
            for role, sections in sections_by_role.items()
        )

        if args.diff:
            show_diff(full_report)

        if args.master:
            master_path = write_master_report(full_report)
            console.print(f"\n[green]Master report updated:[/green] {master_path}")
            archive_path = write_report(full_report)
            console.print(f"[green]Archive saved:[/green] {archive_path}")
        else:
            report_path = write_report(full_report)
            console.print(f"\n[green]Report saved:[/green] {report_path}")

    except KeyboardInterrupt:
        console.print("\n[yellow]Inventory scan cancelled by user.[/yellow]")
    except Exception as e:
        console.print(f"[red]Fatal error:[/red] {e}")


if __name__ == "__main__":
    main()
