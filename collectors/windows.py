from utils.ssh import run_command


def collect_windows(client):
    commands = {
        "hostname": "hostname",
        "os": "powershell -Command \"(Get-CimInstance Win32_OperatingSystem).Caption\"",
        "version": "powershell -Command \"(Get-CimInstance Win32_OperatingSystem).Version\"",
        "uptime": "powershell -Command \"$b=(Get-CimInstance Win32_OperatingSystem).LastBootUpTime; $s=(Get-Date)-$b; \\\"$($s.Days)d $($s.Hours)h $($s.Minutes)m\\\"\"",
        "cpu": "powershell -Command \"(Get-CimInstance Win32_Processor).Name\"",
        "memory": "powershell -Command \"$os=Get-CimInstance Win32_OperatingSystem; '{0:N1} GB used / {1:N1} GB total' -f (($os.TotalVisibleMemorySize-$os.FreePhysicalMemory)/1MB),($os.TotalVisibleMemorySize/1MB)\"",
        "disk": "powershell -Command \"Get-PSDrive C | % { '{0:N1} GB used / {1:N1} GB total' -f ($_.Used/1GB),(($_.Used+$_.Free)/1GB) }\"",
        "ip": "powershell -Command \"(Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.InterfaceAlias -notlike '*Loopback*' }).IPAddress -join ' '\"",
    }

    data = {}
    for key, cmd in commands.items():
        data[key] = run_command(client, cmd)

    # Exclude Microsoft/Windows built-in services by filtering out paths under C:\Windows\
    services_output = run_command(
        client,
        "powershell -Command \"Get-CimInstance Win32_Service | Where-Object { $_.State -eq 'Running' -and $_.PathName -and $_.PathName -notmatch '(?i)\\\\Windows\\\\' } | Select-Object -ExpandProperty DisplayName | Sort-Object\"",
    )
    data["running_services"] = (
        services_output.splitlines()
        if services_output and not services_output.startswith("ERROR:")
        else []
    )

    return data
