import getpass
import threading

import paramiko

password_cache = {}
# Not project-private: also used by collectors/proxmox.py to serialize its own
# password prompts on the same lock, so getpass() never interleaves across
# SSH and Proxmox auth from parallel scan threads.
password_lock = threading.Lock()

_PASSWORD_ATTEMPTS = 2


def connect(host: str, username: str, legacy: bool = False):
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    # Only re-enable legacy algorithms for hosts that explicitly opt in via
    # `legacy_ssh: true` in inventory.yml. Without this flag Paramiko uses its
    # default (modern-only) algorithm set.
    extra = (
        {"disabled_algorithms": {"pubkeys": [], "kex": [], "ciphers": [], "macs": []}}
        if legacy else {}
    )

    try:
        client.connect(
            hostname=host,
            username=username,
            timeout=10,
            look_for_keys=True,
            allow_agent=True,
            **extra,
        )
        print(f"[OK] SSH key auth succeeded for {host}")
        return client

    except paramiko.AuthenticationException:
        print(f"[INFO] Key auth failed for {host}")

    last_error = None
    for attempt in range(_PASSWORD_ATTEMPTS):
        with password_lock:
            if username not in password_cache:
                password_cache[username] = getpass.getpass(f"Password for {username}: ")
            password = password_cache[username]

        try:
            client.connect(
                hostname=host,
                username=username,
                password=password,
                timeout=10,
                look_for_keys=False,
                **extra,
            )
            print(f"[OK] Password auth succeeded for {host}")
            return client
        except paramiko.AuthenticationException as e:
            last_error = e
            # Drop the bad password so the next host (or retry) re-prompts
            # instead of every host under this username failing silently.
            with password_lock:
                if password_cache.get(username) == password:
                    del password_cache[username]
            remaining = _PASSWORD_ATTEMPTS - attempt - 1
            print(f"[INFO] Password auth failed for {username}@{host}"
                  f" — {'retrying' if remaining else 'giving up'}")

    raise last_error


def run_command(client, command: str, timeout: int = 30) -> str:
    stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
    try:
        output = stdout.read().decode().strip()
        error = stderr.read().decode().strip()
    except Exception as e:
        return f"ERROR: failed to read command output ({e})"
    # Many commands write benign warnings to stderr while still succeeding —
    # only treat it as a failure if it produced no usable stdout.
    if error and not output:
        return f"ERROR: {error}"
    return output
