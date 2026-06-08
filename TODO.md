# TODO

## Priority 3 — Larger features

### Smart change detection
`--diff` currently produces a raw unified text diff. Replace or augment with a
structured diff that understands the data: flag meaningful changes only (disk
crossed 90%, VM that was running is now stopped, new failed service appeared,
new host added/removed). Would make automated weekly runs actually alertable.

### Linux interface table
The `interfaces` field on Linux hosts is a long flat string. Parse it into a
proper `interface_table` list (same shape as the network collector's) so it
renders as a subtable rather than a wrapped blob in the property row.

### Canary disk-health cross-reference
Canary (`~/Documents/Projects/canary` — a separate SMART monitoring tool)
already writes `DiskHealth.md` straight into `REPORT_DIR`
(`~/Documents/Notes/Ventoz/Reference/DiskHealth.md`), no new path needed. Its
header carries a parseable timestamp and summary:

```
# Disk Health — 2026-06-07 22:51

**Summary** — Healthy: 9  ·  Warning: 2
```

Crandle could read that file and surface a coarse, host-level pointer in its
own report — e.g. a top-level Collector Note reading "Canary (2026-06-07
22:51): Healthy: 9 · Warning: 2 — see DiskHealth.md" — and flag it as **stale**
if the parsed timestamp is more than 7 days old (the monthly systemd timer
should keep it fresh; a stale report usually means the timer broke, not that
the drives are fine).

Deliberately *not* attempting a per-drive join against `all_disks`: Crandle's
disk records are filesystem-level (keyed by mount point, from `df`), while
Canary's are physical-drive-level (keyed by serial number, raw block devices
like `/dev/sda`). Mapping one to the other — especially through LVM/ZFS/RAID,
where several physical drives sit behind one mount — is a real correlation
problem that's easy to get subtly wrong. A host-level pointer is coarse enough
to never misattribute one drive's health to another's mount point.

---

## Smaller enhancements

### `--role` filter
Mirror `--host` (substring match on host address) but for role names — lets you
scan just `servers` or `network` from a large inventory without editing the
inventory file or filtering by address.

### Configurable worker count
The scan and preflight loops both use `ThreadPoolExecutor()` with Python's
default `min(32, os.cpu_count() + 4)` worker count. A `--workers N` flag (or an
inventory-level setting) would let scans of large inventories with many slow
SSH/SNMP hosts be tuned for throughput, or throttled to avoid hammering a
host's SSH daemon.

## Testing

A good chunk of the collector and report logic is pure string/regex parsing of
captured command output with no I/O — `_kv` / `_fmt_uptime` / `_count_ports` in
`switch.py`, `_int` / `_fmt_mac_hex` / `_fmt_uptime` in `snmp.py`, and the
diff-noise filtering (`_noise_only` / `_filter_size_noise` / `_clean_empty_hunks`)
in `inventory.py`. These are prime candidates for a unit test suite against
captured sample output, and would catch regressions in the trickier regex-based
parsing without needing a live host to scan.

---

## Proxmox guest agent expansion

The QEMU guest agent exposes additional API commands beyond `network-get-interfaces`.
All are available via `proxmox.nodes(node).qemu(vmid).agent("<command>").get()`.

### `guest-get-fsinfo`
Returns per-filesystem disk usage from inside the VM — used bytes, total bytes,
mount point, filesystem type. Would replace or supplement the external Proxmox
disk figure with actual in-guest data, and works for any running VM regardless
of whether SSH is configured.

### `guest-get-osinfo`
Returns OS name, version, kernel, machine type, and hostname directly from the
guest agent. Could pre-populate OS fields in the Proxmox VM table without
needing a separate SSH scan of each VM.

### `guest-exec` (SSH-free collection)
Execute arbitrary commands inside a running VM via Proxmox — no SSH connection
needed. Long-term this means Proxmox-managed VMs could be fully collected
through the agent channel instead of requiring SSH keys and open port 22.
Useful as a fallback when SSH is down or not configured.
