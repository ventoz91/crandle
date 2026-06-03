import re
import time

# Matches the end-of-line prompt pattern for ProSAFE-style CLIs: (Name) > or (Name) #
_PROMPT = re.compile(r'[>#]\s*$', re.MULTILINE)
# Common pager pause strings
_MORE   = re.compile(r'--[Mm]ore--|press .{1,20} key|SPACE=next', re.IGNORECASE)


def _drain(channel, timeout: float = 8.0) -> str:
    """Read from the channel until a CLI prompt appears or timeout expires."""
    buf = ""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if channel.recv_ready():
            chunk = channel.recv(8192).decode("utf-8", errors="replace")
            if _MORE.search(chunk):
                channel.send(" ")  # page through any pager pauses
            buf += chunk
            if _PROMPT.search(buf):
                break
        else:
            time.sleep(0.05)
    return buf


def _cmd(channel, command: str, timeout: float = 10.0) -> str:
    channel.send(command + "\n")
    return _drain(channel, timeout)


def _kv(text: str) -> dict:
    """Parse 'Key Name.....value' dotted-pair lines common in ProSAFE output."""
    result = {}
    for line in text.splitlines():
        m = re.search(r'^(.+?)\s*\.{3,}\s*(.+?)\s*$', line)
        if m:
            result[m.group(1).strip()] = m.group(2).strip()
    return result


def _fmt_uptime(raw: str) -> str:
    """Convert '3 day 2 hr 15 min 33 sec' to '3d 2h 15m'."""
    def n(pat):
        m = re.search(pat, raw or "")
        return int(m.group(1)) if m else 0
    d, h, m = n(r'(\d+)\s+day'), n(r'(\d+)\s+hr'), n(r'(\d+)\s+min')
    if d:
        return f"{d}d {h}h {m}m"
    if h:
        return f"{h}h {m}m"
    return f"{m}m" if m else (raw or "Unknown")


def _count_ports(text: str) -> tuple:
    """Return (ports_up, ports_total) by parsing 'show port status all' output.

    Expects interface lines starting with 0/1, 0/2, etc. (Netgear ProSAFE format).
    Link Status is in column index 4 of each port line.
    """
    up = total = 0
    for line in text.splitlines():
        parts = line.split()
        if not parts or not re.match(r'^\d+/\d+$', parts[0]):
            continue
        total += 1
        status = parts[4].lower() if len(parts) > 4 else ""
        if status == "up":
            up += 1
    return up, total


def collect_switch(client):
    """Interactive CLI collector for Netgear ProSAFE-style managed switches.

    Uses invoke_shell() (PTY) because the ProSAFE CLI is session-oriented and
    does not support exec_command-style single-shot commands.

    Tested against: Netgear GS748TS v5 (firmware 6.x).
    Should also work on other Netgear ProSAFE Smart/Managed switches.
    """
    ch = client.invoke_shell()
    ch.settimeout(15)
    time.sleep(1.5)
    _drain(ch, timeout=5.0)        # discard banner and initial prompt
    _cmd(ch, "terminal length 0")  # disable paging (no-op if unsupported; _MORE handles fallback)

    ver      = _kv(_cmd(ch, "show version"))
    sysinfo  = _kv(_cmd(ch, "show sysinfo"))
    ipmgmt   = _kv(_cmd(ch, "show ip management"))
    port_out = _cmd(ch, "show port status all", timeout=15.0)
    mac_out  = _cmd(ch, "show mac-address-table count")
    ch.close()

    model    = ver.get("Machine Model") or ver.get("System Description") or "Unknown"
    firmware = ver.get("Software Version") or ver.get("Operating System (OS) Version") or "Unknown"
    serial   = ver.get("Serial Number", "Unknown")
    mac_addr = ver.get("Burned In MAC Address", "Unknown")
    uptime   = _fmt_uptime(sysinfo.get("System Up Time") or ver.get("System Up Time", ""))

    # Use System Name if configured; fall back to model string
    name = sysinfo.get("System Name", "")
    hostname = name if name and name not in ("(None)", "None") else model

    ip_address = ipmgmt.get("IP Address") or sysinfo.get("IP Address", "Unknown")
    gateway    = ipmgmt.get("Default Gateway") or sysinfo.get("Default Gateway", "Unknown")

    up, total  = _count_ports(port_out)
    ports      = f"{up}/{total} up" if total else "Unknown"

    mac_m       = re.search(r'(\d+)', mac_out) if mac_out and "ERROR" not in mac_out else None
    mac_entries = mac_m.group(1) if mac_m else "Unknown"

    return {
        "hostname":    hostname,
        "model":       model,
        "firmware":    firmware,
        "serial":      serial,
        "mac_address": mac_addr,
        "uptime":      uptime,
        "ip_address":  ip_address,
        "gateway":     gateway,
        "ports":       ports,
        "mac_entries": mac_entries,
    }
