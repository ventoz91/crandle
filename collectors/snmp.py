import asyncio
import datetime

from puresnmp import Auth, Client, Priv, PyWrapper, V2C, V3

_PHYSICAL_TYPES = {6, 117}  # ethernetCsmacd, gigabitEthernet


def _str(val):
    if val is None:
        return "Unknown"
    if isinstance(val, bytes):
        return val.decode("utf-8", errors="replace").strip()
    return str(val)


def _fmt_uptime(ticks):
    if ticks is None:
        return "Unknown"
    secs = int(ticks.total_seconds()) if isinstance(ticks, datetime.timedelta) else int(ticks) // 100
    d, secs = divmod(secs, 86400)
    h, secs = divmod(secs, 3600)
    m = secs // 60
    if d:
        return f"{d}d {h}h {m}m"
    if h:
        return f"{h}h {m}m"
    return f"{m}m"


def _fmt_mac(mac_bytes) -> str:
    if isinstance(mac_bytes, bytes) and len(mac_bytes) == 6:
        return ":".join(f"{b:02x}" for b in mac_bytes)
    return str(mac_bytes)


def _port_sort_key(entry: dict):
    """Sort '1/g3' numerically by slot then port."""
    port = entry["port"].replace("/g", "/")
    parts = port.split("/")
    try:
        return (int(parts[0]), int(parts[1]))
    except (ValueError, IndexError):
        return (0, 0)


async def _build_port_map(client) -> list:
    """Return a list of {port, mac, ip} for each learned FDB entry."""

    # ifIndex → port name via ifName (IF-MIB)
    ifidx_to_name = {}
    try:
        async for item in client.walk("1.3.6.1.2.1.31.1.1.1.1"):
            ifidx = int(str(item.oid).split(".")[-1])
            ifidx_to_name[ifidx] = _str(item.value)
    except Exception:
        pass

    # ARP table: MAC → IP  (ipNetToMediaPhysAddress; OID suffix = ifIndex.a.b.c.d)
    mac_to_ip = {}
    try:
        async for item in client.walk("1.3.6.1.2.1.4.22.1.2"):
            oid_parts = str(item.oid).split(".")
            ip = ".".join(oid_parts[-4:])
            mac = _fmt_mac(item.value)
            if mac != str(item.value):   # only store if formatting succeeded
                mac_to_ip[mac] = ip
    except Exception:
        pass

    # FDB port: MAC (from OID suffix) → bridge port number
    fdb_ports = {}
    try:
        async for item in client.walk("1.3.6.1.2.1.17.4.3.1.2"):
            oid_parts = str(item.oid).split(".")
            mac = ":".join(f"{int(x):02x}" for x in oid_parts[-6:])
            fdb_ports[mac] = int(item.value)
    except Exception:
        pass

    # FDB status: 3 = learned (dynamic), others = static/self/invalid
    fdb_status = {}
    try:
        async for item in client.walk("1.3.6.1.2.1.17.4.3.1.3"):
            oid_parts = str(item.oid).split(".")
            mac = ":".join(f"{int(x):02x}" for x in oid_parts[-6:])
            fdb_status[mac] = int(item.value)
    except Exception:
        pass

    entries = []
    for mac, bridge_port in fdb_ports.items():
        if fdb_status.get(mac) != 3:              # skip non-learned
            continue
        if int(mac.split(":")[0], 16) & 1:        # skip multicast/broadcast
            continue
        port_name = ifidx_to_name.get(bridge_port, f"port{bridge_port}")
        entries.append({"port": port_name, "mac": mac, "ip": mac_to_ip.get(mac, "")})

    entries.sort(key=_port_sort_key)
    return entries


async def _collect(host: str, creds, port: int) -> dict:
    client = PyWrapper(Client(host, creds, port=port))

    async def get(oid):
        try:
            return await client.get(oid)
        except Exception:
            return None

    async def walk(oid):
        try:
            results = []
            async for item in client.walk(oid):
                results.append(item.value if hasattr(item, "value") else item)
            return results
        except Exception:
            return []

    hostname = _str(await get("1.3.6.1.2.1.1.5.0"))
    descr    = _str(await get("1.3.6.1.2.1.1.1.0"))
    uptime   = _fmt_uptime(await get("1.3.6.1.2.1.1.3.0"))

    ip_address = host  # switch ARP table is unreliable; use configured IP

    if_types    = [int(v) for v in await walk("1.3.6.1.2.1.2.2.1.3")]
    if_statuses = [int(v) for v in await walk("1.3.6.1.2.1.2.2.1.8")]
    physical    = [
        st for ty, st in zip(if_types, if_statuses)
        if ty in _PHYSICAL_TYPES and st != 6   # exclude notPresent slots
    ]
    ports_up    = sum(1 for s in physical if s == 1)
    ports_total = len(physical)
    ports       = f"{ports_up}/{ports_total} up" if ports_total else "Unknown"

    mac_table   = await walk("1.3.6.1.2.1.17.4.3.1.1")
    mac_entries = str(len(mac_table)) if mac_table else "Unknown"

    port_map = await _build_port_map(client)

    return {
        "hostname":    hostname if hostname not in ("Unknown", "") else host,
        "description": descr,
        "uptime":      uptime,
        "ip_address":  ip_address,
        "ports":       ports,
        "mac_entries": mac_entries,
        "port_map":    port_map,
    }


def _credentials(host_config: dict):
    """Return V3 credentials if snmp_user is set, otherwise V2C community string."""
    if host_config.get("snmp_user"):
        auth_key   = host_config.get("auth_key", "")
        priv_key   = host_config.get("priv_key", "")
        auth_proto = host_config.get("auth_proto", "sha").lower()
        priv_proto = host_config.get("priv_proto", "aes").lower()
        auth = Auth(key=auth_key.encode(), method=auth_proto) if auth_key else None
        priv = Priv(key=priv_key.encode(), method=priv_proto) if (priv_key and auth) else None
        return V3(username=host_config["snmp_user"], auth=auth, priv=priv)
    return V2C(host_config.get("community", "public"))


def collect_snmp(host_config: dict) -> dict:
    host  = host_config["host"]
    port  = host_config.get("snmp_port", 161)
    creds = _credentials(host_config)
    return asyncio.run(_collect(host, creds, port))
