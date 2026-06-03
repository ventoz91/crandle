# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Crandle is a homelab inventory tool. It connects to hosts defined in `inventory.yml`, collects system data via SSH (Linux) or the Proxmox API, displays it in terminal tables using Rich, and writes a timestamped Markdown report to `~/Documents/Notes/Ventoz/Reference/HardwareSurvey_<timestamp>.md`.

## Running

```bash
python inventory.py
```

Must be run from the project root (it opens `inventory.yml` relative to the working directory). SSH connections try key auth first, then fall back to a password prompt. Proxmox connections always prompt for a password interactively.

## Installing dependencies

```bash
pip install -r requirements.txt
```

## Architecture

- **`inventory.py`** — entry point. Reads `inventory.yml`, loops over `linux` and `proxmox` host lists, dispatches to collectors, displays results with Rich, and calls `write_report`.
- **`inventory.yml`** — defines the hosts to scan. Two top-level keys: `linux` (list of `{host, user}`) and `proxmox` (list of `{host, user, realm, verify_ssl}`).
- **`collectors/linux.py`** — `collect_linux(client)` runs a fixed dict of shell commands over an open Paramiko SSH client and returns a flat `{key: output}` dict.
- **`collectors/proxmox.py`** — `collect_proxmox(host_config)` prompts for a password, authenticates via `proxmoxer.ProxmoxAPI`, and returns a nested dict: `{host, nodes: [{name, status, cpu, memory_*, disk_*, uptime, vms: [...], lxc: [...], storage: [...]}]}`.
- **`utils/ssh.py`** — `connect(host, username)` returns an authenticated Paramiko client (key → password fallback; passwords are cached per username within a run). `run_command(client, cmd)` executes a command and returns stdout as a stripped string.
- **`utils/report.py`** — `write_report(content)` saves a Markdown string to the hardcoded report directory, creating it if needed.

## Adding a new host type

1. Create `collectors/<type>.py` with a `collect_<type>(...)` function returning a dict.
2. Add a `<type>_to_markdown(data)` function and a `display_<type>(data)` function in `inventory.py`.
3. Add a loop over `inventory.get("<type>", [])` in `main()`.
4. Add the new host type section to `inventory.yml`.
