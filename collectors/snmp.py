import shutil
import subprocess

_PHYSICAL_TYPES = {6, 117}  # ethernetCsmacd, gigabitEthernet


def _snmp_base_args(host_config: dict) -> list:
    if host_config.get("snmp_user"):
        user       = host_config["snmp_user"]
        auth_key   = host_config.get("auth_key", "")
        auth_proto = host_config.get("auth_proto", "SHA").upper()
        priv_key   = host_config.get("priv_key", "")
        priv_proto = host_config.get("priv_proto", "AES").upper()
        if priv_key:
            return ["-v3", "-l", "authPriv",    "-u", user,
                    "-a", auth_proto, "-A", auth_key,
                    "-x", priv_proto, "-X", priv_key]
        return     ["-v3", "-l", "authNoPriv",  "-u", user,
                    "-a", auth_proto, "-A", auth_key]
    return ["-v2c", "-c", host_config.get("community", "public")]


def _run(cmd: list, timeout: int = 30) -> str:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.stdout
    except Exception:
        return ""


def _get(target: str, args: list, oid: str) -> str | None:
    """Single-OID get; returns the bare value string or None on failure."""
    out = _run(["snmpget", "-Oqv", "-t5", "-r1"] + args + [target, oid],
               timeout=10).strip().strip('"')
    return out if out and "No Such" not in out and "Timeout" not in out else None


def _walk(target: str, args: list, oid: str) -> list[tuple[str, str]]:
    """Walk OID subtree; returns [(full_numeric_oid, value), ...].
    Uses -On (full typed output) so value type is explicit and predictable."""
    out = _run(["snmpwalk", "-On", "-t5", "-r1"] + args + [target, oid],
               timeout=30)
    results = []
    for line in out.splitlines():
        if " = " not in line:
            continue
        oid_part, rest = line.split(" = ", 1)
        if "No Such" in rest or "End of MIB" in rest:
            continue
        # rest is like "INTEGER: 6" or "STRING: foo" or "Hex-STRING: 00 11 22"
        val = rest.split(": ", 1)[1].strip().strip('"') if ": " in rest else rest.strip()
        results.append((oid_part.strip(), val))
    return results


def _fmt_uptime(raw: str) -> str:
    """Parse net-snmp uptime: 'D:H:MM:SS.cs', 'H:MM:SS.cs', or '(ticks) ...' """
    if not raw:
        return "Unknown"
    s = raw.strip().strip('"')
    if s.startswith("(") and ")" in s:
        s = s.split(")", 1)[1].strip()
    # "N days, H:MM:SS.cs" written-out form
    days = 0
    if "day" in s:
        day_part, s = s.split(",", 1)
        days = int(day_part.strip().split()[0])
        s = s.strip()
    try:
        parts = s.split(":")
        if len(parts) == 4:                    # D:H:MM:SS.cs
            days, h, m = int(parts[0]), int(parts[1]), int(parts[2])
        else:                                  # H:MM:SS.cs
            h, m = int(parts[0]), int(parts[1])
        if days:
            return f"{days}d {h}h {m}m"
        if h:
            return f"{h}h {m}m"
        return f"{m}m"
    except Exception:
        return s


def _int(val: str) -> int | None:
    """Parse integer from net-snmp value, handling enum 'name(N)' format."""
    v = val.strip()
    if v.lstrip("-").isdigit():
        return int(v)
    if "(" in v:
        try:
            return int(v[v.rfind("(") + 1:v.rfind(")")])
        except (ValueError, IndexError):
            pass
    return None


def _fmt_mac_hex(val: str) -> str:
    """Parse a MAC from net-snmp Hex-STRING value '00 11 22 33 44 55'."""
    h = val.replace(" ", "").replace(":", "")
    if len(h) == 12 and all(c in "0123456789abcdefABCDEF" for c in h):
        return ":".join(h[i:i+2].lower() for i in range(0, 12, 2))
    return ""


def _port_sort_key(entry: dict):
    port  = entry["port"].replace("/g", "/")
    parts = port.split("/")
    try:
        return (int(parts[0]), int(parts[1]))
    except (ValueError, IndexError):
        return (0, 0)


def _build_port_map(target: str, args: list) -> list:
    # ifIndex → port name (ifName)
    ifidx_to_name = {}
    for oid, val in _walk(target, args, "1.3.6.1.2.1.31.1.1.1.1"):
        ifidx = int(oid.split(".")[-1])
        ifidx_to_name[ifidx] = val

    # ARP table: MAC → IP  (OID suffix = ifIndex.a.b.c.d, value = Hex-STRING MAC)
    mac_to_ip = {}
    for oid, val in _walk(target, args, "1.3.6.1.2.1.4.22.1.2"):
        parts = oid.split(".")
        if len(parts) >= 4:
            ip  = ".".join(parts[-4:])
            mac = _fmt_mac_hex(val)
            if mac:
                mac_to_ip[mac] = ip

    # FDB port: OID suffix = MAC decimal octets, value = bridge port number
    fdb_ports = {}
    for oid, val in _walk(target, args, "1.3.6.1.2.1.17.4.3.1.2"):
        parts = oid.split(".")
        if len(parts) >= 6:
            mac = ":".join(f"{int(x):02x}" for x in parts[-6:])
            n = _int(val)
            if n is not None:
                fdb_ports[mac] = n

    # FDB status: 3 = learned (dynamic)
    fdb_status = {}
    for oid, val in _walk(target, args, "1.3.6.1.2.1.17.4.3.1.3"):
        parts = oid.split(".")
        if len(parts) >= 6:
            mac = ":".join(f"{int(x):02x}" for x in parts[-6:])
            n = _int(val)
            if n is not None:
                fdb_status[mac] = n

    entries = []
    for mac, bridge_port in fdb_ports.items():
        if fdb_status.get(mac) != 3:
            continue
        if int(mac.split(":")[0], 16) & 1:      # skip multicast/broadcast
            continue
        port_name = ifidx_to_name.get(bridge_port, f"port{bridge_port}")
        entries.append({"port": port_name, "mac": mac, "ip": mac_to_ip.get(mac, "")})

    entries.sort(key=_port_sort_key)
    return entries


def collect_snmp(host_config: dict) -> dict:
    if not shutil.which("snmpget"):
        raise RuntimeError("net-snmp not found — install with: sudo pacman -S net-snmp")

    host   = host_config["host"]
    port   = host_config.get("snmp_port", 161)
    target = f"{host}:{port}"
    args   = _snmp_base_args(host_config)

    hostname = _get(target, args, "1.3.6.1.2.1.1.5.0") or host
    descr    = _get(target, args, "1.3.6.1.2.1.1.1.0") or "Unknown"
    uptime   = _fmt_uptime(_get(target, args, "1.3.6.1.2.1.1.3.0") or "")
    contact  = _get(target, args, "1.3.6.1.2.1.1.4.0") or ""
    location = _get(target, args, "1.3.6.1.2.1.1.6.0") or ""

    if_types_raw    = _walk(target, args, "1.3.6.1.2.1.2.2.1.3")
    if_statuses_raw = _walk(target, args, "1.3.6.1.2.1.2.2.1.8")

    if_types    = [n for _, v in if_types_raw    if (n := _int(v)) is not None]
    if_statuses = [n for _, v in if_statuses_raw if (n := _int(v)) is not None]

    physical    = [st for ty, st in zip(if_types, if_statuses)
                   if ty in _PHYSICAL_TYPES and st != 6]
    ports_up    = sum(1 for s in physical if s == 1)
    ports_total = len(physical)
    ports       = f"{ports_up}/{ports_total} up" if ports_total else "Unknown"

    mac_table   = _walk(target, args, "1.3.6.1.2.1.17.4.3.1.1")
    mac_entries = str(len(mac_table)) if mac_table else "Unknown"

    # VLAN names (dot1qVlanStaticName — Q-BRIDGE-MIB)
    vlan_raw  = _walk(target, args, "1.3.6.1.2.1.17.7.1.4.3.1.1")
    vlan_list = []
    for oid, val in vlan_raw:
        vlan_id = oid.split(".")[-1]
        vlan_list.append({"id": vlan_id, "name": val})

    port_map = _build_port_map(target, args)

    # Add interface speed to port_map entries
    if_speed_raw = _walk(target, args, "1.3.6.1.2.1.2.2.1.5")  # ifSpeed (bps)
    ifidx_to_speed = {}
    for oid, val in if_speed_raw:
        ifidx = int(oid.split(".")[-1])
        n = _int(val)
        if n is not None and n > 0:
            if n >= 1_000_000_000:
                ifidx_to_speed[ifidx] = f"{n // 1_000_000_000}G"
            elif n >= 1_000_000:
                ifidx_to_speed[ifidx] = f"{n // 1_000_000}M"
            else:
                ifidx_to_speed[ifidx] = f"{n // 1_000}K"

    # Re-walk ifName to map port name → ifIndex for speed lookup
    ifname_raw = _walk(target, args, "1.3.6.1.2.1.31.1.1.1.1")
    name_to_ifidx = {}
    for oid, val in ifname_raw:
        ifidx = int(oid.split(".")[-1])
        name_to_ifidx[val] = ifidx

    for entry in port_map:
        ifidx = name_to_ifidx.get(entry["port"])
        entry["speed"] = ifidx_to_speed.get(ifidx, "") if ifidx else ""

    return {
        "hostname":    hostname,
        "description": descr,
        "uptime":      uptime,
        "ip_address":  host,
        "contact":     contact,
        "location":    location,
        "ports":       ports,
        "mac_entries": mac_entries,
        "vlan_list":   vlan_list,
        "port_map":    port_map,
    }
