# Crandle Host Setup Guide

Setup instructions for each host type supported by Crandle.

---

## Windows

Requires OpenSSH Server and key-based auth configured correctly. Windows has several
permission quirks that differ from Linux.

### 1. Install and start OpenSSH Server

Open PowerShell as Administrator:

```powershell
Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0
Start-Service sshd
Set-Service -Name sshd -StartupType Automatic
```

### 2. Create the `.ssh` folder and `authorized_keys` file

```powershell
New-Item -ItemType Directory -Path "$env:USERPROFILE\.ssh"
New-Item -ItemType File -Path "$env:USERPROFILE\.ssh\authorized_keys"
```

### 3. Copy your public key from this machine

Run this on your Linux machine (enter the Windows password when prompted — this is the
last time you'll need it):

```bash
cat ~/.ssh/id_ed25519.pub | ssh YourWindowsUser@192.168.0.X "powershell -Command \"Add-Content -Path '%USERPROFILE%\\.ssh\\authorized_keys' -Value ([Console]::In.ReadToEnd().Trim())\""
```

### 4. Fix `authorized_keys` permissions

Windows OpenSSH is strict about file permissions. The sshd service runs as
`NT AUTHORITY\SYSTEM`, so it must be able to read the file, and no other accounts
should have write access.

In PowerShell on the Windows machine:

```powershell
icacls "$env:USERPROFILE\.ssh\authorized_keys" /inheritance:r
icacls "$env:USERPROFILE\.ssh\authorized_keys" /grant:r "YourUsername:(R)"
icacls "$env:USERPROFILE\.ssh\authorized_keys" /grant:r "SYSTEM:(R)"
```

Verify the result looks like this:

```
C:\Users\YourUsername\.ssh\authorized_keys  GAMEWINDOWS\YourUsername:(R)
                                            NT AUTHORITY\SYSTEM:(R)
```

### 5. Fix the admin override in `sshd_config`

If the Windows user is in the Administrators group, Windows overrides `authorized_keys`
with a different path by default. Open `C:\ProgramData\ssh\sshd_config` in Notepad
(run as Administrator) and comment out the last two lines:

```
#Match Group administrators
#       AuthorizedKeysFile __PROGRAMDATA__/ssh/administrators_authorized_keys
```

Restart the service to apply:

```powershell
Restart-Service sshd
```

### 6. Add to inventory

```yaml
servers:       # or whichever role fits
  windows:
    - host: 192.168.0.X
      user: YourUsername
```

---

## Proxmox

Crandle uses the Proxmox API. API token auth is recommended over password auth so
the tool can run non-interactively.

### 1. Create an API token

In the Proxmox web UI:

1. Go to **Datacenter > Permissions > API Tokens**
2. Click **Add**
3. Select the user (e.g. `root@pam`), give the token a name (e.g. `crandle`)
4. Uncheck **Privilege Separation** if you want the token to inherit the user's full permissions
5. Copy the token secret — it is only shown once

### 2. Add to inventory

```yaml
servers:
  proxmox:
    - host: 192.168.0.X
      user: root
      realm: pam
      verify_ssl: false
      token_id: root@pam!crandle
      token_secret: your-token-secret-here
```

`token_id` accepts either the full Proxmox format (`user@realm!tokenname`) or just the
token name — the collector handles both.

If `token_id`/`token_secret` are omitted, Crandle will prompt for a password interactively.

---

## OPNsense (and other network appliances)

Crandle connects to OPNsense via SSH and runs basic Unix commands (`hostname`, `uname`,
`uptime`, `ip`/`ifconfig`, `route`, `arp`). The same collector works for pfSense,
OpenWrt, and any other Linux/BSD-based appliance.

### 1. Enable SSH on OPNsense

In the OPNsense web UI:

1. Go to **System > Settings > Administration**
2. Under **Secure Shell**, check **Enable Secure Shell**
3. Set **SSH port** (default 22 is fine for a homelab)
4. Check **Permit password login** temporarily if you haven't copied your key yet
5. Click **Save**

### 2. Add your public key to the OPNsense user

1. Go to **System > Access > Users**
2. Edit the user you want to connect as (e.g. `root`)
3. Paste the contents of `~/.ssh/id_ed25519.pub` into the **Authorized keys** field
4. Save

### 3. Disable password login (optional but recommended)

Once key auth is confirmed working, go back to **System > Settings > Administration**
and uncheck **Permit password login**.

### 4. Add to inventory

```yaml
network:
  network:
    - host: 192.168.0.1
      user: root
```

> Note: vendor CLI devices (Mikrotik, Cisco, etc.) will connect successfully but some
> fields may show raw or unparseable output. The host will still appear in the report.

---

## TP-Link Omada APs (EAP series)

Omada APs run Linux/OpenWrt, so the standard `network` collector works once SSH is
enabled. No special collector needed.

### 1. Enable SSH

**Via Omada Controller (recommended):**

1. Open the controller → **Settings → Site → Services → SSH**
2. Toggle SSH on and set a username and password

**Standalone mode (no controller):**

1. Open the AP's web UI at `http://<ap-ip>`
2. Go to **Management → SSH** and enable it

### 2. Add your public key (optional but recommended)

If your Omada version supports it, paste your public key into the SSH authorized keys
field in the controller or the AP's SSH settings. Otherwise Crandle will fall back to
password auth and cache it for the run.

### 3. Add to inventory

```yaml
network:
  ap:
    - host: 192.168.0.X
      user: admin         # or whatever you set in the SSH settings
      collector: network
```

---

## Netgear GS748TS (ProSAFE managed switch)

Crandle uses SNMP to collect data from this switch — no SSH required. It collects
system description, uptime, management IP, port status (up/total), and MAC table
entry count using standard MIBs that work on any SNMPv2c device.

### 1. Enable SNMP on the switch

1. Log into the web GUI
2. Go to **System → SNMP** (or **Security → SNMP** depending on firmware)
3. Enable **SNMP v1/v2c**
4. Note the **read community string** — default is `public`
5. If the UI asks for a trusted host IP, add your machine's IP or leave it open for
   read-only access (read-only SNMP is low risk on a local network)

### 2. Set a system name (optional)

If you want a friendly hostname in Crandle instead of the raw IP:

1. Go to **System → General → System Information**
2. Set **System Name** to something like `core-switch`

This populates the `sysName` OID that Crandle reads for the hostname field.

### 3. Add to inventory

```yaml
network:
  switch:
    - host: 192.168.0.X
      community: public    # match whatever you set in the switch SNMP config
      collector: snmp
```
