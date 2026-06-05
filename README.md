# Crandle

Homelab inventory scanner. Connects to Linux, macOS, Windows, and network appliance hosts over SSH and Proxmox via its API, displays system info in rich terminal tables, and writes a Markdown report organized by role (Servers, Workstations, Network Equipment).

## Features

- **Linux hosts** — OS, kernel, arch, CPU model/cores, memory, swap, all disks (used/total/% per mount), load average, last boot, IP, interfaces, DNS servers, timezone, NTP sync, virtualisation platform, listening ports, logged-in users, package count, failed systemd services, Docker containers
- **macOS hosts** — OS version + build, model, serial, arch, CPU cores, memory, all disks, uptime, interfaces, DNS servers, timezone, FileVault status, Homebrew formula + cask counts
- **Windows hosts** — OS version, CPU, cores/threads, GPU, memory, all drives, network adapters (MAC/speed/description), IP, domain, timezone, BIOS, motherboard, installed app count, running third-party services; requires OpenSSH Server
- **Network appliances** — hostname, platform, uptime, load average, CPU, memory (used/total), root disk usage, IP addresses, default gateway, DNS servers, routing table, ARP count, interface table (name/status/addresses); SSH-based with BSD/Linux fallbacks, works with pfSense, OPNsense, OpenWrt, TP-Link Omada APs
- **Managed switches (SNMP)** — hostname, description, contact, location, uptime, port status (up/total), MAC table entry count, VLAN list, and a full port map (port/speed → MAC → IP) cross-referencing FDB and ARP tables; works with any SNMPv2c or SNMPv3 device; requires `net-snmp` on the scanning machine
- **Proxmox hosts** — node stats (CPU, memory, disk, uptime, PVE version, kernel, CPU model/threads), all VMs and LXC containers (status, tags, CPUs, memory, disk, uptime, snapshot count, guest IPs via QEMU agent, LXC IPs from config), storage pools; API version reported
- **Role-based organization** — inventory and report are grouped by role (servers, workstations, network, or any custom label)
- **Parallel scanning** — all hosts scanned concurrently via a thread pool
- **Rich terminal output** — formatted tables with color-coded status (green = running/up, red = stopped/failed)
- **Summary table** — at-a-glance view of every host after detail tables
- **Timestamped Markdown report** saved per run, with `--master` to maintain a single always-current file
- **Change detection** — `--diff` shows what changed vs. the last master report; `--save-diff` writes a filtered diff file (size/percentage changes within ±5 GB / ±5% are suppressed as noise)
- **Dry run** — `--dry-run` pings all hosts and reports reachability without scanning

## Requirements

```bash
pip install -r requirements.txt
```

SSH hosts authenticate via key by default, falling back to a password prompt (cached per username within a run, serialized so parallel scans don't collide). Proxmox hosts prompt for a password unless an API token is configured (recommended for automation); Proxmox passwords are also cached per host so multiple Proxmox nodes with the same credentials only prompt once.

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
  firewall:
    - host: 192.168.1.1
      user: root
      collector: network
  switch:
    - host: 192.168.1.2
      user: admin
      collector: network
  ap:
    - host: 192.168.1.3
      user: admin
      collector: network
```

`inventory.yml` is gitignored — it never leaves your machine.

Supported collectors: `linux`, `macos`, `windows`, `proxmox`, `network`, `snmp`, `switch`. The host type key (e.g. `firewall`, `ap`, `router`) is just a label used in display and reports — set `collector: network` on any SSH-based network device, or `collector: snmp` for SNMP-managed switches.

### Proxmox API token

Create a token in the Proxmox UI: **Datacenter → Permissions → API Tokens → Add**. Give it the `PVEAuditor` role for read-only access. Add `token_id` and `token_secret` to the host entry.

### Proxmox QEMU guest agent

To get guest IPs in the VM table, install `qemu-guest-agent` inside each VM and enable it in Proxmox: **VM → Options → QEMU Guest Agent → Enabled**. No reboot required once the agent is already running.

### Windows SSH

Enable the built-in OpenSSH Server: **Settings → System → Optional Features → Add a feature → OpenSSH Server**. PowerShell must be on the remote `PATH` (it is by default on Windows 10 1809+).

### macOS SSH

Enable Remote Login: **System Settings → General → Sharing → Remote Login**.

### Network appliances (pfSense / OPNsense / OpenWrt / TP-Link Omada APs)

Any device running standard Unix commands over SSH works out of the box. Commands are base64-encoded before sending so they arrive in `/bin/sh` verbatim, bypassing non-bash login shells like OPNsense's tcsh. BSD tools are tried first with Linux fallbacks.

If your network device has a descriptive host type name (e.g. `firewall`, `router`, `ap`), add `collector: network` so Crandle knows which collector to use. See [SETUP.md](SETUP.md) for SSH setup instructions for OPNsense and TP-Link Omada APs.

For old embedded devices that only support weak SSH algorithms (dh-group1-sha1, ssh-rsa, aes-cbc), add `legacy_ssh: true` to the host entry. Without it, Paramiko uses modern algorithms only:

```yaml
network:
  ap:
    - host: 192.168.1.3
      user: admin
      collector: network
      legacy_ssh: true
```

### Managed switches (SNMP)

The `snmp` collector uses `snmpget`/`snmpwalk` from the system `net-snmp` package — install with `sudo pacman -S net-snmp` (or your distro equivalent). Supports SNMPv2c (community string) and SNMPv3 (authNoPriv with SHA). See [SETUP.md](SETUP.md) for full setup instructions including the Netgear GS748TS SNMPv3 VACM walkthrough.

**SNMPv2c:**
```yaml
network:
  switch:
    - host: 192.168.1.2
      community: public
      collector: snmp
```

**SNMPv3 (authNoPriv):**
```yaml
network:
  switch:
    - host: 192.168.1.2
      snmp_user: crandle
      auth_key: your_passphrase
      collector: snmp
```

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
| `--save-diff` | Write a filtered diff file comparing master vs. previous archive (no scan needed) |
| `--no-report` | Display results in the terminal only, write nothing |
| `--dry-run` | Ping all hosts and report reachability, no scanning |
| `--host HOST` | Scan only hosts whose address contains HOST (substring) |
| `--inventory FILE` | Use a custom inventory file instead of `inventory.yml` |

Timestamped reports are saved to `~/Documents/Notes/Ventoz/Reference/Hardware Historic/`. The master `HardwareSurvey.md` stays at the top level of `Reference/`.

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
inventory.py            # CLI entry point — arg parsing, preflight, diff logic, main()
scanner.py              # Scan orchestration — load/filter inventory, all scan_* functions
inventory.yml           # Host definitions (gitignored — edit directly)
render/
  terminal.py           # Rich terminal display — all display_* functions, console
  markdown.py           # Markdown rendering — all *_to_markdown functions
collectors/
  linux.py              # SSH: system info, Docker
  macos.py              # SSH: system info, Homebrew
  network.py            # SSH: hostname, platform, routing (pfSense/OPNsense/OpenWrt/Omada AP)
  proxmox.py            # Proxmox API: nodes, VMs, LXC, storage
  snmp.py               # net-snmp CLI wrapper: SNMP v2c/v3 switches (port map, FDB, ARP)
  switch.py             # Interactive CLI: Netgear ProSAFE managed switches (SSH/PTY)
  windows.py            # SSH + PowerShell: system info, third-party services
utils/
  ssh.py                # Paramiko connection helper (key → password fallback, thread-safe, legacy opt-in)
  report.py             # Report writer — timestamped archive, master, diff files
```
