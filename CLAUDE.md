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

- **`inventory.py`** — entry point. Reads `inventory.yml`, builds a flat list of scan tasks (one per host), runs them all concurrently via `ThreadPoolExecutor`, displays results with Rich, prints a summary table, and calls `write_report`/`write_master_report`.
- **`inventory.yml`** — defines the hosts to scan. Top-level keys are **role names** (`servers`, `workstations`, `network`, or any custom label). Under each role, hosts are grouped by **host type** (`linux`, `macos`, `windows`, `proxmox`, `network`). Roles with only comments parse as `null` and are silently skipped.
- **`collectors/linux.py`** — `collect_linux(client)` runs shell commands over an open Paramiko SSH client. Returns OS, kernel, arch, CPU model/cores, memory, swap, `all_disks` (list of `{device, used, total, pct, mount}`), load average, last boot, IP, interfaces, DNS servers, timezone, NTP sync, virt platform, listening ports, logged-in users, package count, failed systemd services, and Docker containers.
- **`collectors/macos.py`** — `collect_macos(client)` collects macOS system info via SSH. Returns OS version, build, model, serial, arch, CPU cores, memory, `all_disks` list, uptime, interfaces, DNS servers, timezone, FileVault status, brew formula count (`brew_formulae`), and brew cask count (`brew_casks`).
- **`collectors/network.py`** — `collect_network(client)` runs BSD/Linux commands suitable for pfSense, OPNsense, OpenWrt, TP-Link Omada APs, and similar appliances. Commands are base64-encoded and piped through `sh` to bypass non-bash login shells (OPNsense uses tcsh). Returns platform, uptime, load average, CPU, memory (used/total via sysctl page-count arithmetic on BSD), disk_root, IP addresses, default gateway, DNS servers, routing table, ARP entry count, and `interface_table` (list of `{interface, status, addresses}`).
- **`collectors/switch.py`** — `collect_switch(client)` uses `invoke_shell()` (PTY) to speak an interactive ProSAFE-style CLI session. Designed for Netgear ProSAFE Smart/Managed switches; not compatible with Unix-tool devices (use `collect_network` for those).
- **`collectors/snmp.py`** — `collect_snmp(host_config)` calls `snmpget`/`snmpwalk` from the system `net-snmp` package via subprocess. Supports SNMPv2c (community string) and SNMPv3 (authNoPriv SHA, authPriv AES). Returns hostname, description, contact, location, uptime, port counts, MAC table entry count, `vlan_list` (list of `{id, name}` from Q-BRIDGE-MIB), and `port_map` (list of `{port, speed, mac, ip}` cross-referencing FDB, ifName, ifSpeed, and ARP tables). `_int()` handles net-snmp enum values like `ethernetCsmacd(6)`.
- **`collectors/proxmox.py`** — `collect_proxmox(host_config)` authenticates via `proxmoxer.ProxmoxAPI` and returns `{host, api_version, nodes: [{name, status, cpu, cpu_count, cpu_model, memory_*, disk_*, uptime, kernel, pve_version, vms: [...], lxc: [...], storage: [...]}]}`. VM entries include `tags`, `snapshots` (count), and `guest_ips` (via QEMU guest agent `network-get-interfaces`, loopback filtered). LXC entries include `tags` and `ip` (from config). Contains `_fmt_bytes`, `_fmt_cpu`, and `_fmt_uptime` helpers. Password prompts cached per `user@host` and serialized via `_password_lock`.
- **`collectors/windows.py`** — `collect_windows(client)` runs PowerShell commands via SSH. Returns OS, version, uptime, CPU (first processor only), cores, threads, GPU, memory, IP, domain, timezone, BIOS, motherboard, installed app count, `all_drives` (list of `{drive, used, total}`), `network_adapters` (list of `{name, mac, speed, description}`), and running non-Microsoft services.
- **`utils/ssh.py`** — `connect(host, username)` returns an authenticated Paramiko client (key → password fallback; passwords are cached per username; `_password_lock` serializes all password prompts — SSH and Proxmox — so parallel scans don't interleave). `run_command(client, cmd, timeout=30)` executes a command with a 30-second read timeout and returns stdout as a stripped string.
- **`utils/report.py`** — `write_report(content)` saves a timestamped Markdown file under `Reference/Hardware Historic/`. `write_master_report(content)` overwrites `Reference/HardwareSurvey.md`. `read_master_report()` returns the current master content (or `None`). Both functions call `_ensure_dirs()` which creates both `Reference/` and `Reference/Hardware Historic/` if they don't exist.

## Inventory structure

```yaml
role_name:          # e.g. servers, workstations, network — any name
  host_type:        # linux | macos | windows | proxmox | network | switch | firewall | ap | router | ...
    - host: IP_OR_HOSTNAME
      user: USERNAME
      collector: network   # override when host_type is a descriptive label that isn't a collector name
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
2. In `inventory.py`:
   - Add `<type>_to_markdown(data)` (use `##` for the host header, skip `hostname` key since it's in the title)
   - Add `display_<type>(data)` using `console.print(Table(...))` (skip `hostname` row)
   - Add `scan_<type>(host_config) -> tuple` returning `(host_addr, data, error)` with a `try/except/finally` that closes any connection in `finally`
   - Register all three in the `SCAN_FNS`, `MARKDOWN_FNS`, and `DISPLAY_FNS` dicts
3. Add `display_summary` handling for the new type — results tuples are `(role, host_type, collector, host_addr, data, err)` (6 elements)
4. Add a commented-out example to `inventory.yml`

## CLI flags

| Flag | Behavior |
|------|----------|
| _(none)_ | Scan all hosts, save timestamped report |
| `--master` | Also overwrite `HardwareSurvey.md` |
| `--diff` | Show unified diff vs. last master |
| `--no-report` | Terminal display only |
| `--dry-run` | Ping check only, no scanning |
| `--host HOST` | Substring filter on host address |
| `--inventory FILE` | Use alternate inventory file |

## Display/markdown conventions

List-type fields (all_disks, all_drives, network_adapters, interface_table, vlan_list, port_map, docker_containers, etc.) are excluded from the generic key/value property loop via `_*_SKIP` sets and rendered as dedicated subtables. This keeps the property table clean and the subtables sortable/scannable. Any new list field must be added to the relevant skip set and given its own display/markdown block.

## Known deferred items

See `TODO.md` for planned improvements including disk trend tracking, structured change detection, Linux interface subtable, and Proxmox guest agent expansion (`guest-get-fsinfo`, `guest-get-osinfo`, `guest-exec` for SSH-free collection).
