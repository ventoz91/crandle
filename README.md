# Crandle

Homelab inventory scanner. Connects to Linux, macOS, Windows, and network appliance hosts over SSH and Proxmox via its API, displays system info in rich terminal tables, and writes a Markdown report organized by role (Servers, Workstations, Network Equipment).

## Features

- **Linux hosts** — hostname, OS, kernel, CPU, memory, disk, load average, IP, interfaces, logged-in users, failed systemd services, Docker containers
- **macOS hosts** — hostname, OS version, kernel, CPU, memory, disk, uptime, Homebrew package count
- **Windows hosts** — hostname, OS, CPU, memory, disk, IP, uptime, running third-party services (Microsoft/Windows built-ins filtered out); requires OpenSSH Server
- **Network appliances** — hostname, platform, uptime, IP addresses, routing table, ARP count; SSH-based, works with pfSense, OPNsense, OpenWrt
- **Proxmox hosts** — node stats, all VMs and LXC containers (status, CPUs, memory, uptime), storage pools
- **Role-based organization** — inventory and report are grouped into Servers, Workstations, Network Equipment
- **Parallel scanning** — all hosts scanned concurrently via a thread pool
- **Rich terminal output** — formatted tables with color-coded status (green = running/up, red = stopped/failed)
- **Summary table** — at-a-glance view of every host after detail tables
- **Timestamped Markdown report** saved per run, with `--master` to maintain a single always-current file
- **Change detection** — `--diff` shows what changed vs. the last master report
- **Dry run** — `--dry-run` pings all hosts and reports reachability without scanning

## Requirements

```bash
pip install -r requirements.txt
```

SSH hosts authenticate via key by default, falling back to a password prompt (cached per username within a run, serialized so parallel scans don't collide). Proxmox hosts prompt for a password unless an API token is configured (recommended for automation).

## Configuration

Edit `inventory.yml` and add your hosts under the appropriate role:

```yaml
servers:
  linux:
    - host: 192.168.1.10
      user: admin
  proxmox:
    - host: 192.168.1.20
      user: root
      realm: pam
      verify_ssl: false
      # Optional — required for automated/non-interactive runs:
      # token_id: root@pam!crandle
      # token_secret: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx

workstations:
  windows:
    - host: 192.168.1.30
      user: YourUsername
  macos:
    - host: 192.168.1.40
      user: YourUsername

network:
  network:
    - host: 192.168.1.1
      user: admin
```

`inventory.yml` is gitignored — it never leaves your machine.

Supported host types under each role: `linux`, `macos`, `windows`, `proxmox`, `network`.
Roles can be named anything; `servers`, `workstations`, and `network` are the conventional defaults.

### Proxmox API token

Create a token in the Proxmox UI: **Datacenter → Permissions → API Tokens → Add**. Give it the `PVEAuditor` role for read-only access. Add `token_id` and `token_secret` to the host entry.

### Windows SSH

Enable the built-in OpenSSH Server: **Settings → System → Optional Features → Add a feature → OpenSSH Server**. PowerShell must be on the remote `PATH` (it is by default on Windows 10 1809+).

### macOS SSH

Enable Remote Login: **System Settings → General → Sharing → Remote Login**.

### Network appliances

Any device running standard Unix commands over SSH works out of the box (pfSense, OPNsense, OpenWrt). Vendor CLI devices (Mikrotik RouterOS, Cisco IOS, etc.) will connect successfully but command output may not parse cleanly — they are still useful as reachability placeholders in `--dry-run`.

## Usage

```bash
python inventory.py [options]
```

| Flag | Description |
|------|-------------|
| _(none)_ | Scan all hosts, save a timestamped report |
| `--master` | Overwrite `HardwareSurvey.md` and save a timestamped archive |
| `--master --diff` | Show what changed vs. the last master before overwriting |
| `--diff` | Show diff vs. last master without overwriting |
| `--no-report` | Display results in the terminal only, write nothing |
| `--dry-run` | Ping all hosts and report reachability, no scanning |
| `--host HOST` | Scan only hosts whose address contains HOST (substring) |
| `--inventory FILE` | Use a custom inventory file instead of `inventory.yml` |

Reports are saved to `~/Documents/Notes/Ventoz/Reference/`.

## Report structure

Reports are Markdown files organized by role, then by host:

```
# Servers
## hostname (linux)
## Proxmox — 192.168.1.20
### Node: pve
#### Virtual Machines
#### LXC Containers
#### Storage

# Workstations
## DESKTOP-ABC (Windows)

# Network
## router (network)
```

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

Requires `token_id` and `token_secret` in `inventory.yml` so the timer can authenticate non-interactively. Windows/macOS/network hosts in automated runs must use SSH key auth.

## Project structure

```
inventory.py            # Entry point — scanning, display, report generation
inventory.yml           # Host definitions (gitignored — edit directly)
collectors/
  linux.py              # SSH: system info, Docker
  macos.py              # SSH: system info, Homebrew
  network.py            # SSH: hostname, platform, routing (pfSense/OPNsense/OpenWrt)
  proxmox.py            # Proxmox API: nodes, VMs, LXC, storage
  windows.py            # SSH + PowerShell: system info, third-party services
utils/
  ssh.py                # Paramiko connection helper (key → password fallback, thread-safe)
  report.py             # Markdown report writer (timestamped + master)
```
