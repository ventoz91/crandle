import asyncio
import datetime

from puresnmp import Client, PyWrapper, V2C

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


async def _collect(host: str, community: str, port: int) -> dict:
    client = PyWrapper(Client(host, V2C(community), port=port))

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

    hostname = _str(await get("1.3.6.1.2.1.1.5.0"))          # sysName
    descr    = _str(await get("1.3.6.1.2.1.1.1.0"))          # sysDescr
    uptime   = _fmt_uptime(await get("1.3.6.1.2.1.1.3.0"))   # sysUpTime

    # Use the configured host IP — SNMP ipAdEntAddr returns unreliable values on some switches
    ip_address = host

    # Port status: filter to physical Ethernet (ifType=6/117), exclude notPresent (status=6)
    # notPresent = empty port slot; filtering it out gives only populated/cabled ports
    if_types    = [int(v) for v in await walk("1.3.6.1.2.1.2.2.1.3")]   # ifType
    if_statuses = [int(v) for v in await walk("1.3.6.1.2.1.2.2.1.8")]   # ifOperStatus
    physical    = [
        st for ty, st in zip(if_types, if_statuses)
        if ty in _PHYSICAL_TYPES and st != 6
    ]
    ports_up    = sum(1 for s in physical if s == 1)
    ports_total = len(physical)
    ports       = f"{ports_up}/{ports_total} up" if ports_total else "Unknown"

    mac_table   = await walk("1.3.6.1.2.1.17.4.3.1.1")
    mac_entries = str(len(mac_table)) if mac_table else "Unknown"

    return {
        "hostname":    hostname if hostname not in ("Unknown", "") else host,
        "description": descr,
        "uptime":      uptime,
        "ip_address":  ip_address,
        "ports":       ports,
        "mac_entries": mac_entries,
    }


def collect_snmp(host_config: dict) -> dict:
    host      = host_config["host"]
    community = host_config.get("community", "public")
    port      = host_config.get("snmp_port", 161)
    return asyncio.run(_collect(host, community, port))
