from utils.ssh import run_command


def collect_windows(client):
    commands = {
        "hostname":       "hostname",
        "os":             "powershell -Command \"(Get-CimInstance Win32_OperatingSystem).Caption\"",
        "version":        "powershell -Command \"(Get-CimInstance Win32_OperatingSystem).Version\"",
        "uptime":         "powershell -Command \"$b=(Get-CimInstance Win32_OperatingSystem).LastBootUpTime; $s=(Get-Date)-$b; \\\"$($s.Days)d $($s.Hours)h $($s.Minutes)m\\\"\"",
        "cpu":            "powershell -Command \"(Get-CimInstance Win32_Processor | Select-Object -First 1).Name\"",
        "cpu_cores":      "powershell -Command \"(Get-CimInstance Win32_Processor | Measure-Object -Property NumberOfCores -Sum).Sum\"",
        "cpu_threads":    "powershell -Command \"(Get-CimInstance Win32_Processor | Measure-Object -Property NumberOfLogicalProcessors -Sum).Sum\"",
        "gpu":            "powershell -Command \"(Get-CimInstance Win32_VideoController | Where-Object {$_.Name -notlike '*Basic*' -and $_.Name -notlike '*Generic*'}).Name -join ', '\"",
        "memory":         "powershell -Command \"$os=Get-CimInstance Win32_OperatingSystem; '{0:N1} GB used / {1:N1} GB total' -f (($os.TotalVisibleMemorySize-$os.FreePhysicalMemory)/1MB),($os.TotalVisibleMemorySize/1MB)\"",
        "ip":             "powershell -Command \"(Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.InterfaceAlias -notlike '*Loopback*' }).IPAddress -join ' '\"",
        "domain":         "powershell -Command \"(Get-CimInstance Win32_ComputerSystem).Domain\"",
        "timezone":       "powershell -Command \"(Get-TimeZone).Id\"",
        "bios":           "powershell -Command \"$b=Get-CimInstance Win32_BIOS; \\\"$($b.Manufacturer) $($b.SMBIOSBIOSVersion)\\\"\"",
        "motherboard":    "powershell -Command \"$m=Get-CimInstance Win32_BaseBoard; \\\"$($m.Manufacturer) $($m.Product)\\\"\"",
        "installed_apps": "powershell -Command \"(Get-ItemProperty 'HKLM:\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*','HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*' -ErrorAction SilentlyContinue | Where-Object {$_.DisplayName} | Measure-Object).Count\"",
    }

    data = {}
    for key, cmd in commands.items():
        data[key] = run_command(client, cmd)

    # All logical drives
    drives_raw = run_command(
        client,
        "powershell -Command \"Get-PSDrive | Where-Object {$_.Provider -like '*FileSystem*' -and $_.Used -ne $null} | ForEach-Object { '{0}|{1:N1} GB|{2:N1} GB' -f $_.Name, ($_.Used/1GB), (($_.Used+$_.Free)/1GB) }\"",
    )
    drives = []
    if drives_raw and not drives_raw.startswith("ERROR:"):
        for line in drives_raw.splitlines():
            parts = line.strip().split("|")
            if len(parts) == 3:
                drives.append({"drive": parts[0], "used": parts[1], "total": parts[2]})
    data["all_drives"] = drives

    # Network adapters (up only)
    adapters_raw = run_command(
        client,
        "powershell -Command \"Get-NetAdapter | Where-Object {$_.Status -eq 'Up'} | ForEach-Object { '{0}|{1}|{2}|{3}' -f $_.Name, $_.MacAddress, $_.LinkSpeed, $_.InterfaceDescription }\"",
    )
    adapters = []
    if adapters_raw and not adapters_raw.startswith("ERROR:"):
        for line in adapters_raw.splitlines():
            parts = line.strip().split("|")
            if len(parts) == 4:
                adapters.append({
                    "name": parts[0], "mac": parts[1],
                    "speed": parts[2], "description": parts[3],
                })
    data["network_adapters"] = adapters

    # Non-Microsoft running services
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
