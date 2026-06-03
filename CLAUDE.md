# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Crandle is a homelab inventory tool. It connects to hosts defined in `inventory.yml`, collects system data via SSH (Linux, macOS, Windows, network appliances) or the Proxmox API, displays it in terminal tables using Rich, and writes a timestamped Markdown report to `~/Documents/Notes/Ventoz/Reference/HardwareSurvey_<timestamp>.md`.

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
- **`collectors/linux.py`** — `collect_linux(client)` runs shell commands over an open Paramiko SSH client and returns a flat `{key: output}` dict including Docker containers, load average, interfaces, logged-in users, and failed systemd services.
- **`collectors/macos.py`** — `collect_macos(client)` collects macOS system info (sw_vers, sysctl, top, brew) via SSH.
- **`collectors/network.py`** — `collect_network(client)` runs basic Unix commands (hostname, uname, uptime, ip/ifconfig, route, arp) suitable for pfSense, OPNsense, OpenWrt, and similar appliances.
- **`collectors/proxmox.py`** — `collect_proxmox(host_config)` authenticates via `proxmoxer.ProxmoxAPI` and returns a nested dict: `{host, nodes: [{name, status, cpu, memory_*, disk_*, uptime, vms: [...], lxc: [...], storage: [...]}]}`.
- **`collectors/windows.py`** — `collect_windows(client)` runs PowerShell commands via SSH and collects system info plus running non-Microsoft services (filtered by `PathName` not matching `\Windows\`).
- **`utils/ssh.py`** — `connect(host, username)` returns an authenticated Paramiko client (key → password fallback; passwords are cached per username; a `threading.Lock` serializes password prompts so parallel scans don't interleave). `run_command(client, cmd)` executes a command and returns stdout as a stripped string.
- **`utils/report.py`** — `write_report(content)` saves a timestamped Markdown file. `write_master_report(content)` overwrites the fixed `HardwareSurvey.md`. `read_master_report()` returns the current master content (or `None`).

## Inventory structure

```yaml
role_name:          # e.g. servers, workstations, network — any name
  host_type:        # linux | macos | windows | proxmox | network
    - host: IP_OR_HOSTNAME
      user: USERNAME
      # proxmox also accepts: realm, verify_ssl, token_id, token_secret
```

## Report structure

Reports are organized by role (`# Servers`), then by host (`## hostname`), then by subsection (`### Node`, `#### VMs`). This hierarchy means:
- `# Role` — h1
- `## Host` — h2
- `### Proxmox node` — h3
- `#### VMs / LXC / Storage` — h4

All `*_to_markdown()` functions output at `##` level so they slot cleanly under a role header.

## Adding a new host type

1. Create `collectors/<type>.py` with a `collect_<type>(client_or_config)` function returning a dict.
2. In `inventory.py`:
   - Add `<type>_to_markdown(data)` (use `##` for the host header)
   - Add `display_<type>(data)` using `console.print(Table(...))`
   - Add `scan_<type>(host_config) -> tuple` returning `(host_addr, data, error)`
   - Register all three in the `SCAN_FNS`, `MARKDOWN_FNS`, and `DISPLAY_FNS` dicts
3. Add `display_summary` handling for the new type (the `(role, host_type, host_addr, data, err)` tuple)
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
