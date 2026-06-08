# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Crandle is a homelab inventory tool. It connects to hosts defined in `inventory.yml`, collects system data via SSH (Linux, macOS, Windows, network appliances) or the Proxmox API, displays it in terminal tables using Rich, and writes a timestamped Markdown report to `~/Documents/Notes/Ventoz/Reference/Hardware Historic/HardwareSurvey_<timestamp>.md`. The always-current master lives at `~/Documents/Notes/Ventoz/Reference/HardwareSurvey.md`.

## Running

```bash
python inventory.py
```

Must be run from the project root (it opens `inventory.yml` relative to the working directory). SSH connections try key auth first, then fall back to a password prompt (cached per username, serialized via threading.Lock so parallel scans don't produce interleaved prompts). Proxmox connections use an API token if configured, otherwise prompt for a password.

## Installing dependencies

```bash
pip install -r requirements.txt
```

## Architecture

- **`inventory.py`** — CLI entry point. Parses arguments, runs preflight ping check (`--dry-run`), orchestrates the scan loop, calls display/markdown/report functions, and handles `--diff` / `--save-diff`. Does not contain collectors, renderers, or scan functions — those live in their own modules.
- **`scanner.py`** — scan orchestration. `load_inventory`, `_iter_hosts`, `filter_inventory` handle inventory parsing. All `scan_*` functions open connections, call the appropriate collector, and return `(host, data, error)` tuples. `SCAN_FNS` dict maps collector names to functions.
- **`render/terminal.py`** — Rich terminal output. All `display_*` functions, `display_summary`, `_status_style`, and the shared `console = Console()` instance. `DISPLAY_FNS` dict maps collector names to functions. Imports skip-set constants from `render/markdown.py`.
- **`render/markdown.py`** — Markdown rendering. All `*_to_markdown` functions, `role_to_markdown`, skip sets (`_LINUX_SKIP` etc.), and `MARKDOWN_FNS` dict.
- **`inventory.yml`** — defines the hosts to scan. Top-level keys are **role names** (`servers`, `workstations`, `network`, or any custom label). Under each role, hosts are grouped by **host type** (`linux`, `macos`, `windows`, `proxmox`, `network`). Roles with only comments parse as `null` and are silently skipped.
- **`collectors/linux.py`** — `collect_linux(client)` runs shell commands over an open Paramiko SSH client. Returns OS, kernel, arch, CPU model/cores, memory, swap, `all_disks` (list of `{device, used, total, pct, mount}`), load average, last boot, IP, interfaces, DNS servers, timezone, NTP sync, virt platform, listening ports, logged-in users, package count, failed systemd services, and Docker containers.
- **`collectors/macos.py`** — `collect_macos(client)` collects macOS system info via SSH. Returns OS version, build, model, serial, arch, CPU cores, memory, `all_disks` list, uptime, interfaces, DNS servers, timezone, FileVault status, brew formula count (`brew_formulae`), and brew cask count (`brew_casks`).
- **`collectors/network.py`** — `collect_network(client)` runs BSD/Linux commands suitable for pfSense, OPNsense, OpenWrt, TP-Link Omada APs, and similar appliances. Commands are base64-encoded and piped through `sh` to bypass non-bash login shells (OPNsense uses tcsh). Returns platform, uptime, load average, CPU, memory (used/total via sysctl page-count arithmetic on BSD), disk_root, IP addresses, default gateway, DNS servers, routing table, ARP entry count, and `interface_table` (list of `{interface, status, addresses}`).
- **`collectors/switch.py`** — `collect_switch(client)` uses `invoke_shell()` (PTY) to speak an interactive ProSAFE-style CLI session. Designed for Netgear ProSAFE Smart/Managed switches; not compatible with Unix-tool devices (use `collect_network` for those).
- **`collectors/snmp.py`** — `collect_snmp(host_config)` calls `snmpget`/`snmpwalk` from the system `net-snmp` package via subprocess. Supports SNMPv2c (community string) and SNMPv3 (authNoPriv SHA, authPriv AES). Returns hostname, description, contact, location, uptime, port counts, MAC table entry count, `vlan_list` (list of `{id, name}` from Q-BRIDGE-MIB), and `port_map` (list of `{port, speed, mac, ip}` cross-referencing FDB, ifName, ifSpeed, and ARP tables). `_int()` handles net-snmp enum values like `ethernetCsmacd(6)`.
- **`collectors/proxmox.py`** — `collect_proxmox(host_config)` authenticates via `proxmoxer.ProxmoxAPI` and returns `{host, api_version, nodes: [{name, status, cpu, cpu_count, cpu_model, memory_*, disk_*, uptime, kernel, pve_version, vms: [...], lxc: [...], storage: [...]}]}`. VM entries include `tags`, `snapshots` (count), and `guest_ips` (via QEMU guest agent `network-get-interfaces`, loopback filtered). LXC entries include `tags` and `ip` (from config). Contains `_fmt_bytes`, `_fmt_cpu`, and `_fmt_uptime` helpers. Password prompts cached per `user@host` and serialized via `_password_lock`.
- **`collectors/windows.py`** — `collect_windows(client)` runs PowerShell commands via SSH. Returns OS, version, uptime, CPU (first processor only), cores, threads, GPU, memory, IP, domain, timezone, BIOS, motherboard, installed app count, `all_drives` (list of `{drive, used, total}`), `network_adapters` (list of `{name, mac, speed, description}`), and running non-Microsoft services.
- **`utils/ssh.py`** — `connect(host, username, legacy=False)` returns an authenticated Paramiko client (key → password fallback; passwords are cached per username; `_password_lock` serializes all password prompts so parallel scans don't interleave). `legacy=True` re-enables weak SSH algorithms (dh-group1-sha1, aes-cbc, etc.) for old embedded devices; set via `legacy_ssh: true` in `inventory.yml`. `run_command(client, cmd, timeout=30)` executes a command and returns stdout as a stripped string.
- **`utils/report.py`** — `write_report(content, timestamp=None)` saves a timestamped Markdown archive under `Reference/Hardware Historic/`. `write_json_report(hosts, timestamp=None)` saves a paired `HardwareSurvey_<timestamp>.json` archive of raw collected data (used by `--json`); pass the same `timestamp` to both so the files pair up. `report_timestamp()` generates that shared timestamp string. `write_master_report(content)` overwrites `Reference/HardwareSurvey.md`. `read_master_report()` returns the current master (or `None`). `get_previous_archive()` returns the second-most-recent archive path (used by `--save-diff`). `write_diff_report(content)` saves a `HardwareSurveyDiff_<timestamp>.md` file to the same archive directory. `md_escape(s)` escapes `|` and strips newlines for safe embedding in markdown table cells.

## Inventory structure

```yaml
role_name:          # e.g. servers, workstations, network — any name
  host_type:        # linux | macos | windows | proxmox | network | switch | firewall | ap | router | ...
    - host: IP_OR_HOSTNAME
      user: USERNAME
      collector: network   # override when host_type is a descriptive label that isn't a collector name
      legacy_ssh: true     # optional: re-enables weak SSH algorithms for old embedded devices
      # proxmox also accepts: realm, verify_ssl, token_id, token_secret
```

If `collector` is omitted, `host_type` is used as the collector key directly. Registered collectors: `linux`, `macos`, `windows`, `proxmox`, `network`, `switch`. Descriptive type names like `firewall`, `ap`, `router` need `collector: network`; `switch` routes to the ProSAFE CLI collector automatically (no override needed). For OpenWrt-based managed switches, add `collector: network` to override. The type name appears as-is in terminal tables and report headers.

## Report structure

Reports are organized by role (`# Servers`), then by host (`## hostname`), then by subsection (`### Node`, `#### VMs`). This hierarchy means:
- `# Role` — h1
- `## Host` — h2
- `### Proxmox node` — h3
- `#### VMs / LXC / Storage` — h4

All `*_to_markdown()` functions output at `##` level so they slot cleanly under a role header.

## Adding a new host type

1. Create `collectors/<type>.py` with a `collect_<type>(client_or_config)` function returning a dict. Format all values to strings at collection time (see `_fmt_bytes`, `_fmt_cpu`, `_fmt_uptime` in `proxmox.py` as examples) so display and markdown functions never receive raw integers.
2. In `render/markdown.py`:
   - Add a `_<TYPE>_SKIP` set for list fields rendered as subtables
   - Add `<type>_to_markdown(data)` (use `##` for the host header, skip `hostname` key since it's in the title)
   - Register it in `MARKDOWN_FNS`
3. In `render/terminal.py`:
   - Add `display_<type>(data)` using `console.print(Table(...))` (skip `hostname` row; import any new skip sets from `render/markdown.py`)
   - Register it in `DISPLAY_FNS`
4. In `scanner.py`:
   - For SSH-based collectors, register `scan_<type> = _make_ssh_scanner(collect_<type>)` — it handles the connect/collect/close/error boilerplate (pass a `collect_kwargs` lambda if the collector needs extra per-host config, e.g. Linux's `compose_paths`). For non-SSH collectors (Proxmox, SNMP), write a plain `scan_<type>(host_config) -> tuple` returning `(host_addr, data, error)`.
   - Register it in `SCAN_FNS`
5. In `inventory.py`, add `display_summary` handling for the new type — results tuples are `(role, host_type, collector, host_addr, data, err)` (6 elements)
6. Add a commented-out example to `inventory.yml`

## CLI flags

| Flag | Behavior |
|------|----------|
| _(none)_ | Scan all hosts, save timestamped report |
| `--master` | Also overwrite `HardwareSurvey.md` |
| `--diff` | Show unified diff vs. last master |
| `--save-diff` | Write a filtered diff file (master vs. previous archive) — no scan needed |
| `--json` | Also write a timestamped JSON archive of raw collected data, paired with the markdown report by timestamp |
| `--trend` | Show disk usage trend per host/mount across all `--json` archives — no scan needed |
| `--no-report` | Terminal display only |
| `--dry-run` | Ping check only, no scanning |
| `--host HOST` | Substring filter on host address |
| `--inventory FILE` | Use alternate inventory file |

## Display/markdown conventions

List-type fields (all_disks, all_drives, network_adapters, interface_table, vlan_list, port_map, docker_containers, etc.) are excluded from the generic key/value property loop via `_*_SKIP` sets defined in `render/markdown.py` and imported by `render/terminal.py`. They are rendered as dedicated subtables. Any new list field must be added to the relevant skip set in `render/markdown.py` and given its own display block in `render/terminal.py` and markdown block in `render/markdown.py`.

## Known deferred items

See `TODO.md` for planned improvements including disk trend tracking, structured change detection, Linux interface subtable, and Proxmox guest agent expansion (`guest-get-fsinfo`, `guest-get-osinfo`, `guest-exec` for SSH-free collection).
