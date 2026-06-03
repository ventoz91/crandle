import getpass
import paramiko

# Cache passwords so we only ask once per username
password_cache = {}


def connect(host: str, username: str):

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        client.connect(
            hostname=host,
            username=username,
            timeout=10,
            look_for_keys=True,
            allow_agent=True,
        )

        print(f"[OK] SSH key auth succeeded for {host}")
        return client

    except paramiko.AuthenticationException:

        print(f"[INFO] Key auth failed for {host}")

        if username not in password_cache:
            password_cache[username] = getpass.getpass(
                f"Password for {username}: "
            )

        client.connect(
            hostname=host,
            username=username,
            password=password_cache[username],
            timeout=10,
            look_for_keys=False,
        )

        print(f"[OK] Password auth succeeded for {host}")
        return client


def run_command(client, command: str) -> str:

    stdin, stdout, stderr = client.exec_command(command)

    output = stdout.read().decode().strip()
    error = stderr.read().decode().strip()

    if error:
        return f"ERROR: {error}"

    return output

