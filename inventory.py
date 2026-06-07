import argparse
import concurrent.futures
import difflib
from datetime import datetime
import re
import subprocess

from rich.table import Table

from render.terminal import console, DISPLAY_FNS, display_summary
from render.markdown import MARKDOWN_FNS, role_to_markdown
from scanner import SCAN_FNS, load_inventory, filter_inventory, _iter_hosts
from utils.report import (
    write_report, write_master_report, read_master_report,
    get_previous_archive, write_diff_report, write_json_report, report_timestamp,
)


# ---------------------------------------------------------------------------
# Preflight (ping check)
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Diff helpers
# ---------------------------------------------------------------------------

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


# Matches size values (G, GB, GiB, T, TB, TiB, M, MB, MiB) and percentages
_MEASURE_RE = re.compile(
    r'(\d+\.?\d*)\s*(GiB|TiB|MiB|GB|TB|MB|Gi|Ti|Mi|G|T|M|%)(?!\w)',
    re.IGNORECASE,
)
_SIZE_THRESHOLD_GB = 5.0
_PCT_THRESHOLD = 5.0


def _to_gb(val: float, unit: str) -> float:
    u = unit.upper()
    if u in ('T', 'TB', 'TIB', 'TI'):
        return val * 1024
    if u in ('M', 'MB', 'MIB', 'MI'):
        return val / 1024
    return val  # G, GB, Gi/GI, GiB/GIB


def _noise_only(old: str, new: str) -> bool:
    """True when lines differ only in size/pct values that are all within threshold."""
    if old == new:
        return True
    old_m = _MEASURE_RE.findall(old)
    new_m = _MEASURE_RE.findall(new)
    if len(old_m) != len(new_m) or not old_m:
        return False
    if _MEASURE_RE.sub('\x00', old) != _MEASURE_RE.sub('\x00', new):
        return False
    for (ov, ou), (nv, nu) in zip(old_m, new_m):
        if ou == '%' or nu == '%':
            if abs(float(nv) - float(ov)) > _PCT_THRESHOLD:
                return False
        else:
            if abs(_to_gb(float(nv), nu) - _to_gb(float(ov), ou)) > _SIZE_THRESHOLD_GB:
                return False
    return True


def _filter_size_noise(diff_lines: list[str]) -> list[str]:
    """Drop -/+ blocks whose only changes are size/pct values within threshold.

    Handles multi-line blocks (N removals followed by N additions) — the block
    is only dropped if every paired line passes _noise_only, so a single
    significant change in the block keeps everything.
    """
    result = []
    i = 0
    while i < len(diff_lines):
        line = diff_lines[i]
        if line.startswith('-') and not line.startswith('---'):
            neg = []
            j = i
            while j < len(diff_lines) and diff_lines[j].startswith('-') and not diff_lines[j].startswith('---'):
                neg.append(diff_lines[j])
                j += 1
            pos = []
            while j < len(diff_lines) and diff_lines[j].startswith('+') and not diff_lines[j].startswith('+++'):
                pos.append(diff_lines[j])
                j += 1
            if (len(neg) == len(pos)
                    and all(_noise_only(n[1:], p[1:]) for n, p in zip(neg, pos))):
                i = j
                continue
            result.extend(neg)
            result.extend(pos)
            i = j
        else:
            result.append(line)
            i += 1
    return result


def _clean_empty_hunks(lines: list[str]) -> list[str]:
    """Remove @@ hunk headers left empty after noise filtering; return [] if nothing remains."""
    headers, i = [], 0
    while i < len(lines) and not lines[i].startswith('@@ '):
        headers.append(lines[i])
        i += 1
    hunks = []
    while i < len(lines):
        if lines[i].startswith('@@ '):
            hunk, j = [lines[i]], i + 1
            while j < len(lines) and not lines[j].startswith('@@ '):
                hunk.append(lines[j])
                j += 1
            if any(
                (l.startswith('+') and not l.startswith('+++')) or
                (l.startswith('-') and not l.startswith('---'))
                for l in hunk[1:]
            ):
                hunks.extend(hunk)
            i = j
        else:
            i += 1
    return (headers + hunks) if hunks else []


def save_survey_diff():
    master = read_master_report()
    if master is None:
        console.print("[yellow]No master report found — run with --master first.[/yellow]")
        return

    prev = get_previous_archive()
    if prev is None:
        console.print("[yellow]Need at least two archived reports to diff.[/yellow]")
        return

    with open(prev, "r", encoding="utf-8") as f:
        prev_content = f.read()

    old_lines = prev_content.splitlines(keepends=True)
    new_lines = master.splitlines(keepends=True)
    diff = _clean_empty_hunks(_filter_size_noise(list(
        difflib.unified_diff(old_lines, new_lines, fromfile=prev.name, tofile="HardwareSurvey.md", lineterm="")
    )))

    if not diff:
        console.print("[green]No meaningful differences (all changes within ±5 GB / ±5% threshold).[/green]")
        return

    added   = sum(1 for l in diff if l.startswith("+") and not l.startswith("+++"))
    removed = sum(1 for l in diff if l.startswith("-") and not l.startswith("---"))
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    lines = [
        f"# Hardware Survey Diff — {now}",
        "",
        "| | File |",
        "|-|------|",
        f"| Previous | `{prev.name}` |",
        "| Current  | `HardwareSurvey.md` |",
        "",
        f"**{added} lines added, {removed} lines removed**",
        "",
        "```diff",
        *[l.rstrip() for l in diff],
        "```",
        "",
    ]

    path = write_diff_report("\n".join(lines))
    console.print(f"[green]Diff saved:[/green] {path}")
    console.print(f"  {added} lines added, {removed} lines removed vs. {prev.name}")


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
            "  python inventory.py --save-diff            write diff of master vs previous archive\n"
            "  python inventory.py --json                 also write a timestamped JSON archive\n"
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
    parser.add_argument("--save-diff", action="store_true",
                        help="write a diff file comparing master vs. previous archive to Hardware Historic/")
    parser.add_argument("--json", action="store_true",
                        help="also write a timestamped JSON archive of raw collected data alongside the report")
    parser.add_argument("--host", metavar="HOST",
                        help="scan only hosts whose address contains HOST (substring match)")
    parser.add_argument("--inventory", metavar="FILE", default="inventory.yml",
                        help="path to inventory file (default: inventory.yml)")
    args = parser.parse_args()

    if args.save_diff:
        save_survey_diff()
        return

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

        console.print()
        ordered_results = []
        sections_by_role = {}

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

        timestamp = report_timestamp()

        if args.master:
            master_path = write_master_report(full_report)
            console.print(f"\n[green]Master report updated:[/green] {master_path}")
            archive_path = write_report(full_report, timestamp=timestamp)
            console.print(f"[green]Archive saved:[/green] {archive_path}")
        else:
            report_path = write_report(full_report, timestamp=timestamp)
            console.print(f"\n[green]Report saved:[/green] {report_path}")

        if args.json:
            json_hosts = [
                {
                    "role": role, "host_type": host_type, "collector": collector,
                    "host": host_addr, "data": data,
                    "error": str(err) if err else None,
                }
                for role, host_type, collector, host_addr, data, err in ordered_results
            ]
            json_path = write_json_report(json_hosts, timestamp=timestamp)
            console.print(f"[green]JSON archive saved:[/green] {json_path}")

    except KeyboardInterrupt:
        console.print("\n[yellow]Inventory scan cancelled by user.[/yellow]")
    except Exception as e:
        console.print(f"[red]Fatal error:[/red] {e}")


if __name__ == "__main__":
    main()
