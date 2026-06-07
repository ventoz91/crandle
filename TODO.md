# TODO

## Priority 3 — Larger features

### Disk trend tracking (`--trend` flag)
Timestamped archives already exist in `Hardware Historic/`. Add a `--trend` flag
that reads the last N reports and shows delta/trajectory per disk mount per host —
answers "how fast is my plex pool filling up?" without manually diffing old files.
Could output a small table: host | mount | oldest% | latest% | change | days.

### Smart change detection
`--diff` currently produces a raw unified text diff. Replace or augment with a
structured diff that understands the data: flag meaningful changes only (disk
crossed 90%, VM that was running is now stopped, new failed service appeared,
new host added/removed). Would make automated weekly runs actually alertable.

### Linux interface table
The `interfaces` field on Linux hosts is a long flat string. Parse it into a
proper `interface_table` list (same shape as the network collector's) so it
renders as a subtable rather than a wrapped blob in the property row.

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
