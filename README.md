# Crandle

Homelab inventory scanner. Connects to Linux hosts over SSH and Proxmox via its API, displays system info in rich terminal tables, and writes a Markdown report.

## Features

- Linux hosts: hostname, OS, kernel, CPU, memory, disk, IP, uptime, Docker containers via SSH
- Proxmox hosts: node stats, all VMs and LXC containers (status, CPUs, memory, uptime), storage pools
- Rich terminal output with formatted tables
- Timestamped Markdown report saved per run
- `--master` flag to maintain a single always-current `HardwareSurvey.md`
- Weekly automation via systemd user timer (see [Automation](#automation))

## Requirements

```bash
pip install -r requirements.txt
```

SSH hosts authenticate via key by default, falling back to a password prompt. Proxmox hosts prompt for a password unless an API token is configured (recommended for automation).

## Configuration

Copy the example inventory and fill in your hosts:

```bash
cp inventory.yml.example inventory.yml
```

```yaml
linux:
  - host: 192.168.1.10
    user: admin

proxmox:
  - host: 192.168.1.20
    user: root
    realm: pam
    verify_ssl: false
    # Optional — required for automated/non-interactive runs:
    # token_id: crandle
    # token_secret: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
```

`inventory.yml` is gitignored — it never leaves your machine.

### Proxmox API token

Create a token in the Proxmox UI: **Datacenter → Permissions → API Tokens → Add**. Give it the `PVEAuditor` role for read-only access.

## Usage

```bash
# Standard run — saves HardwareSurvey_<timestamp>.md
python inventory.py

# Master run — overwrites HardwareSurvey.md and saves a timestamped archive
python inventory.py --master
```

Reports are saved to `~/Documents/Notes/Ventoz/Reference/`.

## Automation

Systemd user units live in the [dotfiles](https://github.com/ventoz91/dotfiles) repo (`crandle/` stow package). They run `inventory.py --master` every Sunday at 02:00.

To install:

```bash
# From ~/dotfiles
stow crandle
systemctl --user daemon-reload
systemctl --user enable --now crandle.timer

# Verify
systemctl --user list-timers crandle.timer
```

Requires `token_id` and `token_secret` in `inventory.yml` so the timer can authenticate non-interactively.

## Project structure

```
inventory.py            # Entry point
inventory.yml           # Host definitions (gitignored — copy from .example)
inventory.yml.example   # Template
collectors/
  linux.py              # SSH-based Linux data collection (system info + Docker)
  proxmox.py            # Proxmox API data collection
utils/
  ssh.py                # Paramiko connection + command runner
  report.py             # Markdown report writer
```
