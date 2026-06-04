from pysnmp.hlapi import (
    CommunityData, ContextData, ObjectIdentity, ObjectType,
    SnmpEngine, UdpTransportTarget, getCmd, nextCmd,
)

# Standard ifType values for physical Ethernet ports
_PHYSICAL_TYPES = {6, 117}  # ethernetCsmacd, gigabitEthernet


def _get(host, community, port, oid):
    err_ind, err_status, _, var_binds = next(
        getCmd(
            SnmpEngine(),
            CommunityData(community, mpModel=1),
            UdpTransportTarget((host, port), timeout=5, retries=1),
            ContextData(),
            ObjectType(ObjectIdentity(oid)),
        )
    )
    if err_ind or err_status:
        return None
    return var_binds[0][1]


def _walk(host, community, port, oid):
    results = []
    for err_ind, err_status, _, var_binds in nextCmd(
        SnmpEngine(),
        CommunityData(community, mpModel=1),
        UdpTransportTarget((host, port), timeout=5, retries=1),
        ContextData(),
        ObjectType(ObjectIdentity(oid)),
        lexicographicMode=False,
    ):
        if err_ind or err_status:
            break
        for _, val in var_binds:
            results.append(val)
    return results


def _str(val):
    return val.prettyPrint() if val is not None else "Unknown"


def _fmt_uptime(ticks):
    if ticks is None:
        return "Unknown"
    secs = int(ticks) // 100
    d, secs = divmod(secs, 86400)
    h, secs = divmod(secs, 3600)
    m = secs // 60
    if d:
        return f"{d}d {h}h {m}m"
    if h:
        return f"{h}h {m}m"
    return f"{m}m"


def collect_snmp(host_config: dict) -> dict:
    """SNMP collector for managed switches and other SNMP-capable devices.

    Uses standard MIBs (RFC 1213, IF-MIB, IP-MIB, BRIDGE-MIB) so it works
    on any SNMPv2c device — Netgear ProSAFE, Cisco, HP, etc.
    """
    host      = host_config["host"]
    community = host_config.get("community", "public")
    port      = host_config.get("snmp_port", 161)

    def get(oid):
        return _get(host, community, port, oid)

    def walk(oid):
        return _walk(host, community, port, oid)

    # System group (RFC 1213)
    hostname = _str(get("1.3.6.1.2.1.1.5.0"))   # sysName
    descr    = _str(get("1.3.6.1.2.1.1.1.0"))   # sysDescr
    uptime   = _fmt_uptime(get("1.3.6.1.2.1.1.3.0"))  # sysUpTime (TimeTicks)

    # Management IP: first non-loopback address from ipAdEntAddr
    ip_addrs   = [_str(v) for v in walk("1.3.6.1.2.1.4.20.1.1")]
    ip_address = next((ip for ip in ip_addrs if not ip.startswith("127.")), "Unknown")

    # Port status: pair ifType with ifOperStatus, keep physical Ethernet only
    if_types    = [int(v) for v in walk("1.3.6.1.2.1.2.2.1.3")]  # ifType
    if_statuses = [int(v) for v in walk("1.3.6.1.2.1.2.2.1.8")]  # ifOperStatus
    physical    = [st for ty, st in zip(if_types, if_statuses) if ty in _PHYSICAL_TYPES]
    ports_up    = sum(1 for s in physical if s == 1)
    ports_total = len(physical)
    ports       = f"{ports_up}/{ports_total} up" if ports_total else "Unknown"

    # MAC forwarding table entry count (BRIDGE-MIB dot1dTpFdbAddress)
    mac_table   = walk("1.3.6.1.2.1.17.4.3.1.1")
    mac_entries = str(len(mac_table)) if mac_table else "Unknown"

    return {
        "hostname":    hostname if hostname not in ("Unknown", "") else host,
        "description": descr,
        "uptime":      uptime,
        "ip_address":  ip_address,
        "ports":       ports,
        "mac_entries": mac_entries,
    }
