import ctypes
import json
import platform
import re
import socket
import subprocess
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime
from pathlib import Path
import threading

APP_NAME = 'Hospital Network Doctor'
VERSION = '2.0'
BASE = Path(__file__).resolve().parent
CONFIG_FILE = BASE / 'network_config.json'
LOG_FILE = BASE / 'network_doctor.log'

DEFAULT_CONFIG = {
    'network': {
        'subnet_mask': '255.255.255.0',
        'gateway': '10.58.27.1',
        'preferred_dns': '8.8.8.8',
        'alternate_dns': '8.8.4.4'
    },
    'repair': {
        'ip_address': '',
        'apply_static_ip': False
    }
}


def load_config():
    if not CONFIG_FILE.exists():
        CONFIG_FILE.write_text(json.dumps(DEFAULT_CONFIG, indent=4), encoding='utf-8')
    try:
        return json.loads(CONFIG_FILE.read_text(encoding='utf-8'))
    except Exception:
        return DEFAULT_CONFIG.copy()


CONFIG = load_config()


def is_admin():
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def run_command(command, timeout=60):
    try:
        p = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=timeout
        )
        return p.returncode, (p.stdout + '\n' + p.stderr).strip()
    except subprocess.TimeoutExpired:
        return -2, 'Command timed out.'
    except Exception as exc:
        return -1, str(exc)


def log_event(title, body):
    try:
        with LOG_FILE.open('a', encoding='utf-8') as f:
            f.write(f'\n[{datetime.now():%Y-%m-%d %H:%M:%S}] {title}\n{body}\n')
    except Exception:
        pass


def get_ipconfig():
    return run_command('ipconfig /all')[1]


def parse_ipconfig(text):
    result = {'ipv4': '', 'mask': '', 'gateway': '', 'dns': []}
    lines = text.splitlines()
    dns_section = False
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        m = re.search(r'IPv4 Address[^:]*:\s*([\d.]+)', line, re.I)
        if m and not result['ipv4']:
            result['ipv4'] = m.group(1)
        m = re.search(r'Subnet Mask[^:]*:\s*([\d.]+)', line, re.I)
        if m and not result['mask']:
            result['mask'] = m.group(1)
        m = re.search(r'Default Gateway[^:]*:\s*([\d.]+)', line, re.I)
        if m and m.group(1) != '0.0.0.0':
            result['gateway'] = m.group(1)
        m = re.search(r'DNS Servers[^:]*:\s*([\d.]+)', line, re.I)
        if m:
            result['dns'].append(m.group(1))
            dns_section = True
        elif dns_section and re.fullmatch(r'[\d.]+', line):
            result['dns'].append(line)
        elif not raw.startswith((' ', '\t')):
            dns_section = False
    return result


def ping(host):
    code, output = run_command(f'ping -n 2 -w 1500 "{host}"', timeout=10)
    return code == 0, output


def dns_test():
    try:
        socket.gethostbyname('www.google.com')
        return True, 'DNS resolution succeeded.'
    except Exception as exc:
        return False, f'DNS resolution failed: {exc}'


def internet_test():
    ok, output = ping('8.8.8.8')
    return ok, output


def validate_ipv4(ip):
    parts = ip.strip().split('.')
    if len(parts) != 4:
        return False
    try:
        return all(0 <= int(p) <= 255 for p in parts)
    except ValueError:
        return False


def diagnose():
    cfg = CONFIG['network']
    current = parse_ipconfig(get_ipconfig())
    out = [
        f'COMPUTER: {socket.gethostname()}',
        f'OS: {platform.platform()}',
        f'TIME: {datetime.now():%Y-%m-%d %H:%M:%S}',
        '',
        'CURRENT CONFIGURATION',
        f"IPv4 address : {current['ipv4'] or 'NOT FOUND'}",
        f"Subnet mask  : {current['mask'] or 'NOT FOUND'}",
        f"Gateway      : {current['gateway'] or 'NOT FOUND'}",
        f"DNS servers  : {', '.join(current['dns']) if current['dns'] else 'NOT FOUND'}",
        '',
        'CONFIGURATION CHECKS'
    ]
    failures = 0

    if current['ipv4'].startswith('169.254.'):
        out.append('FAIL - APIPA address detected (169.254.x.x).')
        failures += 1
    elif current['ipv4']:
        out.append('PASS - IPv4 address is assigned.')
    else:
        out.append('FAIL - No IPv4 address detected.')
        failures += 1

    if current['mask'] == cfg['subnet_mask']:
        out.append('PASS - Subnet mask matches approved configuration.')
    else:
        out.append(f"FAIL - Subnet mask is {current['mask'] or 'missing'}; expected {cfg['subnet_mask']}.")
        failures += 1

    if current['gateway'] == cfg['gateway']:
        out.append('PASS - Default gateway matches approved configuration.')
    else:
        out.append(f"FAIL - Gateway is {current['gateway'] or 'missing'}; expected {cfg['gateway']}.")
        failures += 1

    if cfg['preferred_dns'] in current['dns'] or cfg['alternate_dns'] in current['dns']:
        out.append('PASS - At least one approved DNS server is present.')
    else:
        out.append('FAIL - Approved DNS servers were not detected.')
        failures += 1

    out += ['', 'CONNECTIVITY TESTS']
    if current['gateway']:
        ok, _ = ping(current['gateway'])
        out.append(('PASS' if ok else 'FAIL') + f' - Gateway ping ({current["gateway"]})')
        failures += int(not ok)
    else:
        out.append('SKIP - No gateway to test.')

    ok_dns, dns_msg = dns_test()
    out.append(('PASS' if ok_dns else 'FAIL') + ' - ' + dns_msg)
    failures += int(not ok_dns)

    ok_net, _ = internet_test()
    out.append(('PASS' if ok_net else 'FAIL') + ' - Internet reachability (8.8.8.8)')
    failures += int(not ok_net)

    out += ['', f'FINAL RESULT: {"PROBLEM DETECTED" if failures else "NO OBVIOUS PROBLEM"}']
    if failures:
        out.append('Review FAIL items before making network changes.')
    else:
        out.append('The PC passed the basic configuration and connectivity checks.')

    text = '\n'.join(out)
    log_event('DIAGNOSIS', text)
    return text


def find_active_adapter():
    cmd = (
        'powershell -NoProfile -Command "Get-NetIPConfiguration | '
        'Where-Object {$_.IPv4Address -and $_.NetAdapter.Status -eq \'Up\'} | '
        'Select-Object -First 1 -ExpandProperty InterfaceAlias"'
    )
    _, output = run_command(cmd)
    return output.strip().splitlines()[0] if output.strip() else ''


def get_network_adapters():
    cmd = (
        'powershell -NoProfile -Command "Get-NetAdapter | '
        'Select-Object Name,InterfaceDescription,Status,LinkSpeed,MacAddress | '
        'Format-Table -AutoSize | Out-String"'
    )
    return run_command(cmd)[1]


def repair():
    if not is_admin():
        messagebox.showerror(APP_NAME, 'Run this program as Administrator before repairing network settings.')
        return

    cfg = CONFIG['network']
    repair_cfg = CONFIG.get('repair', {})
    apply_static_ip = bool(repair_cfg.get('apply_static_ip', False))
    ip = str(repair_cfg.get('ip_address', '')).strip()

    if apply_static_ip and not validate_ipv4(ip):
        messagebox.showerror(APP_NAME, 'network_config.json has no valid per-PC IP address.')
        return

    adapter = find_active_adapter()
    if not adapter:
        messagebox.showerror(APP_NAME, 'Could not find an active IPv4 network adapter.')
        return

    if not apply_static_ip:
        messagebox.showwarning(
            APP_NAME,
            'Safe repair is not enabled.\n\n'
            'Each PC may require a unique static IP. Confirm the correct IP for this particular computer '
            'before enabling static-IP repair in network_config.json.'
        )
        return

    commands = [
        f'netsh interface ipv4 set address name="{adapter}" static {ip} {cfg["subnet_mask"]} {cfg["gateway"]}',
        f'netsh interface ipv4 set dns name="{adapter}" static {cfg["preferred_dns"]}',
        f'netsh interface ipv4 add dns name="{adapter}" {cfg["alternate_dns"]} index=2',
        'ipconfig /flushdns'
    ]

    results = []
    for command in commands:
        code, output = run_command(command)
        results.append(f'$ {command}\n{output}\nExit code: {code}')

    text = '\n\n'.join(results)
    log_event('REPAIR', text)
    show_output(text + '\n\nRun diagnosis again to verify the repair.')


def tryfix_window():
    if not is_admin():
        messagebox.showerror(APP_NAME, 'Run this program as Administrator before changing network settings.')
        return

    cfg = CONFIG['network']
    current = parse_ipconfig(get_ipconfig())

    win = tk.Toplevel(root)
    win.title('Trouble box')
    win.geometry('480x330')
    win.resizable(False, False)
    win.transient(root)
    win.grab_set()

    fields = [
        ('IP address', current['ipv4']),
        ('Submask', current['mask'] or cfg['subnet_mask']),
        ('Default gateway', current['gateway'] or cfg['gateway']),
        ('Preferred DNS server', current['dns'][0] if current['dns'] else cfg['preferred_dns']),
        ('Alternative DNS server', current['dns'][1] if len(current['dns']) > 1 else cfg['alternate_dns'])
    ]
    entries = {}

    body = ttk.Frame(win, padding=15)
    body.pack(fill='both', expand=True)
    ttk.Label(body, text='Trouble box', font=('Segoe UI', 15, 'bold')).grid(row=0, column=0, columnspan=2, sticky='w', pady=(0, 12))

    for row, (label, value) in enumerate(fields, start=1):
        ttk.Label(body, text=label + ':').grid(row=row, column=0, sticky='w', pady=5)
        e = ttk.Entry(body, width=35)
        e.insert(0, value)
        e.grid(row=row, column=1, sticky='ew', pady=5)
        entries[label] = e

    ttk.Label(body, text='Enter the correct settings for this PC. Avoid duplicate IP addresses.', foreground='red').grid(
        row=6, column=0, columnspan=2, sticky='w', pady=(8, 10)
    )

    buttons = ttk.Frame(body)
    buttons.grid(row=7, column=0, columnspan=2, sticky='e')

    def reload_current():
        fresh = parse_ipconfig(get_ipconfig())
        values = [
            fresh['ipv4'], fresh['mask'] or cfg['subnet_mask'], fresh['gateway'] or cfg['gateway'],
            fresh['dns'][0] if fresh['dns'] else cfg['preferred_dns'],
            fresh['dns'][1] if len(fresh['dns']) > 1 else cfg['alternate_dns']
        ]
        for e, value in zip(entries.values(), values):
            e.delete(0, tk.END)
            e.insert(0, value)

    def apply_tryfix():
        values = {k: e.get().strip() for k, e in entries.items()}
        if not all(validate_ipv4(v) for v in values.values()):
            messagebox.showerror('Trouble box', 'All five fields must contain valid IPv4 addresses.', parent=win)
            return
        if values['IP address'].startswith('169.254.'):
            messagebox.showerror('Trouble box', 'Do not use an APIPA address as a static IP.', parent=win)
            return

        adapter = find_active_adapter()
        if not adapter:
            messagebox.showerror('Trouble box', 'No active network adapter was found.', parent=win)
            return

        confirm = messagebox.askyesno(
            'Confirm network change',
            f'Adapter: {adapter}\n\n'
            f'IP: {current["ipv4"] or "missing"}  →  {values["IP address"]}\n'
            f'Subnet: {current["mask"] or "missing"}  →  {values["Submask"]}\n'
            f'Gateway: {current["gateway"] or "missing"}  →  {values["Default gateway"]}\n'
            f'DNS: {", ".join(current["dns"]) or "missing"}  →  {values["Preferred DNS server"]}, {values["Alternative DNS server"]}\n\n'
            'Continue?', parent=win
        )
        if not confirm:
            return

        commands = [
            f'netsh interface ipv4 set address name="{adapter}" static {values["IP address"]} {values["Submask"]} {values["Default gateway"]}',
            f'netsh interface ipv4 set dns name="{adapter}" static {values["Preferred DNS server"]}',
            f'netsh interface ipv4 add dns name="{adapter}" {values["Alternative DNS server"]} index=2',
            'ipconfig /flushdns'
        ]
        results = []
        for command in commands:
            code, output = run_command(command)
            results.append(f'$ {command}\n{output}\nExit code: {code}')

        text = '\n\n'.join(results)
        log_event('TRYFIX', text)
        win.destroy()
        show_output(text + '\n\nRunning verification...')
        root.after(500, run_diagnosis)

    ttk.Button(buttons, text='Reload Current', command=reload_current).pack(side='left', padx=5)
    ttk.Button(buttons, text='Apply', command=apply_tryfix).pack(side='left', padx=5)
    ttk.Button(buttons, text='Cancel', command=win.destroy).pack(side='left', padx=5)
    win.bind('<Return>', lambda event: apply_tryfix())
    win.bind('<Escape>', lambda event: win.destroy())


def force_connect_worker():
    if not is_admin():
        root.after(0, lambda: messagebox.showerror(APP_NAME, 'Run this program as Administrator to use Force Connect.'))
        return

    steps = []
    # Enable all disabled physical network adapters.
    code, output = run_command(
        'powershell -NoProfile -Command "Get-NetAdapter | Where-Object {$_.Status -eq \'Disabled\'} | Enable-NetAdapter -Confirm:$false"'
    )
    steps.append(f'ENABLE DISABLED ADAPTERS\n{output}\nExit code: {code}')

    # Restart an adapter that is up but not passing traffic.
    adapter = find_active_adapter()
    if adapter:
        code, output = run_command(
            f'powershell -NoProfile -Command "Restart-NetAdapter -Name \'{adapter.replace(chr(39), chr(39)+chr(39))}\' -Confirm:$false"',
            timeout=45
        )
        steps.append(f'RESTART ADAPTER: {adapter}\n{output}\nExit code: {code}')

    # Refresh DHCP configuration. Static adapters simply report that DHCP is not enabled.
    code, output = run_command('ipconfig /release', timeout=30)
    steps.append(f'RELEASE IP\n{output}\nExit code: {code}')
    code, output = run_command('ipconfig /renew', timeout=45)
    steps.append(f'RENEW IP\n{output}\nExit code: {code}')
    code, output = run_command('ipconfig /flushdns', timeout=15)
    steps.append(f'FLUSH DNS\n{output}\nExit code: {code}')

    # Ask Windows to rescan network devices.
    code, output = run_command('pnputil /scan-devices', timeout=60)
    steps.append(f'SCAN DEVICES\n{output}\nExit code: {code}')

    # Try reconnecting Wi-Fi using an existing saved Windows Wi-Fi profile.
    code, profiles = run_command('netsh wlan show profiles', timeout=15)
    if code == 0:
        names = re.findall(r'All User Profile\s*:\s*(.+)', profiles, re.I)
        if names:
            profile = names[0].strip()
            safe_profile = profile.replace('"', '\\"')
            code, output = run_command(f'netsh wlan connect name="{safe_profile}"', timeout=20)
            steps.append(f'WIFI RECONNECT: {profile}\n{output}\nExit code: {code}')
        else:
            steps.append('WIFI RECONNECT\nNo saved Wi-Fi profile was found.')
    else:
        steps.append(f'WIFI PROFILE CHECK\n{profiles}\nExit code: {code}')

    # Give the adapter a moment, then verify.
    import time
    time.sleep(3)
    current = parse_ipconfig(get_ipconfig())
    gateway_ok = False
    dns_ok = False
    net_ok = False
    if current['gateway']:
        gateway_ok, _ = ping(current['gateway'])
    dns_ok, dns_msg = dns_test()
    net_ok, _ = internet_test()

    result = '\n\n'.join(steps)
    result += (
        '\n\nFORCE CONNECT VERIFICATION\n'
        f'IPv4: {current["ipv4"] or "NOT FOUND"}\n'
        f'Gateway: {current["gateway"] or "NOT FOUND"}\n'
        f'Gateway reachable: {"YES" if gateway_ok else "NO"}\n'
        f'DNS: {"OK" if dns_ok else "FAILED"} ({dns_msg})\n'
        f'Internet reachable: {"YES" if net_ok else "NO"}'
    )
    log_event('FORCE CONNECT', result)
    root.after(0, lambda: finish_force_connect(result, net_ok))


def finish_force_connect(result, internet_ok):
    show_output(result)
    if internet_ok:
        messagebox.showinfo(APP_NAME, 'Force Connect completed and Internet access was verified.')
    else:
        messagebox.showwarning(
            APP_NAME,
            'Force Connect completed its recovery steps, but Internet access could not be verified.\n\n'
            'Check the physical/Wi-Fi connection, IP/gateway settings, or the hospital network itself.'
        )


def force_connect():
    if not is_admin():
        messagebox.showerror(APP_NAME, 'Run this program as Administrator to use Force Connect.')
        return
    show_output('FORCE CONNECT\n\nWorking... Please wait.\n')
    threading.Thread(target=force_connect_worker, daemon=True).start()


def update_driver_worker():
    if not is_admin():
        root.after(0, lambda: messagebox.showerror(APP_NAME, 'Run this program as Administrator to update drivers.'))
        return

    steps = []
    adapters = get_network_adapters()
    steps.append('NETWORK ADAPTERS\n' + adapters)

    # Windows Update Agent: search for applicable driver-class updates and install them.
    ps = r'''$session = New-Object -ComObject Microsoft.Update.Session; $searcher = $session.CreateUpdateSearcher(); $result = $searcher.Search("IsInstalled=0 and Type='Driver'"); Write-Output ("Found driver updates: " + $result.Updates.Count); for ($i=0; $i -lt $result.Updates.Count; $i++) { Write-Output ("UPDATE " + ($i+1) + ": " + $result.Updates.Item($i).Title) }; if ($result.Updates.Count -gt 0) { $updates = New-Object -ComObject Microsoft.Update.UpdateColl; for ($i=0; $i -lt $result.Updates.Count; $i++) { $u=$result.Updates.Item($i); if (-not $u.EulaAccepted) { $u.AcceptEula() }; [void]$updates.Add($u) }; $downloader=$session.CreateUpdateDownloader(); $downloader.Updates=$updates; $d=$downloader.Download(); Write-Output ("Download result: " + $d.ResultCode); $installer=$session.CreateUpdateInstaller(); $installer.Updates=$updates; $r=$installer.Install(); Write-Output ("Install result: " + $r.ResultCode); Write-Output ("Reboot required: " + $r.RebootRequired) }'''
    command = 'powershell -NoProfile -ExecutionPolicy Bypass -Command "' + ps.replace('"', '\\"') + '"'
    code, output = run_command(command, timeout=600)
    steps.append('WINDOWS UPDATE DRIVER PROCESS\n' + output + f'\nExit code: {code}')

    # Rescan devices after the update attempt.
    code, output = run_command('pnputil /scan-devices', timeout=60)
    steps.append('DEVICE RESCAN\n' + output + f'\nExit code: {code}')

    result = '\n\n'.join(steps)
    log_event('UPDATE DRIVER', result)
    root.after(0, lambda: finish_driver_update(result))


def finish_driver_update(result):
    show_output(result)
    if 'Reboot required: True' in result:
        messagebox.showwarning(APP_NAME, 'Network driver update completed, but Windows reports that a restart is required.')
    elif 'Found driver updates: 0' in result:
        messagebox.showinfo(APP_NAME, 'Windows did not find an applicable driver update. The installed network driver may already be current.')
    else:
        messagebox.showinfo(APP_NAME, 'The driver update process has completed. Review the report above and run Diagnosis afterward.')


def update_driver():
    if not is_admin():
        messagebox.showerror(APP_NAME, 'Run this program as Administrator to update drivers.')
        return
    confirm = messagebox.askyesno(
        APP_NAME,
        'Update Driver will ask Windows for applicable network/device driver updates through Windows Update.\n\n'
        'The process may take several minutes and may require a restart. Continue?'
    )
    if not confirm:
        return
    show_output('UPDATE DRIVER\n\nChecking Windows Update for applicable drivers...\nThis may take several minutes.\n')
    threading.Thread(target=update_driver_worker, daemon=True).start()


def show_output(text):
    output.delete('1.0', tk.END)
    output.insert(tk.END, text)
    output.see('1.0')


def run_diagnosis():
    show_output('Running diagnosis...\n')
    root.update_idletasks()
    show_output(diagnose())


def open_config():
    CONFIG_FILE.touch(exist_ok=True)
    import os
    os.startfile(CONFIG_FILE)


root = tk.Tk()
root.title(APP_NAME + f' v{VERSION}')
root.geometry('980x700')
root.minsize(820, 580)

style = ttk.Style()
try:
    style.theme_use('vista')
except tk.TclError:
    pass

header = ttk.Frame(root, padding=15)
header.pack(fill='x')
ttk.Label(header, text=APP_NAME, font=('Segoe UI', 20, 'bold')).pack(anchor='w')
ttk.Label(header, text='Windows network diagnosis, recovery and controlled repair', font=('Segoe UI', 10)).pack(anchor='w')
ttk.Label(header, text='Administrator: YES' if is_admin() else 'Administrator: NO').pack(anchor='w', pady=(7, 0))

bar = ttk.Frame(root, padding=(15, 0, 15, 10))
bar.pack(fill='x')
buttons = [
    ('RUN DIAGNOSIS', run_diagnosis),
    ('REPAIR NETWORK', repair),
    ('TRYFIX', tryfix_window),
    ('FORCE CONNECT', force_connect),
    ('UPDATE DRIVER', update_driver),
    ('OPEN CONFIG', open_config),
]
for label, command in buttons:
    ttk.Button(bar, text=label, command=command).pack(side='left', padx=4)

frame = ttk.Frame(root, padding=(15, 0, 15, 15))
frame.pack(fill='both', expand=True)
output = tk.Text(frame, wrap='word', font=('Consolas', 10), padx=12, pady=12)
scroll = ttk.Scrollbar(frame, orient='vertical', command=output.yview)
output.configure(yscrollcommand=scroll.set)
output.pack(side='left', fill='both', expand=True)
scroll.pack(side='right', fill='y')

output.insert(tk.END, f'''Hospital Network Doctor v{VERSION}\n\n'
'1. Run DIAGNOSIS first.\n'
'2. TRYFIX lets you enter the correct IP, subnet, gateway and DNS settings.\n'
'3. FORCE CONNECT attempts adapter recovery, DHCP refresh, DNS flush, device rescan and saved Wi-Fi reconnection.\n'
'4. UPDATE DRIVER checks Windows Update for applicable driver updates and rescans devices.\n'
'5. Do not use a static IP until the correct unique IP for that PC is confirmed.\n\n'
'Approved baseline from the supplied hospital network reference:\n'
'Gateway: 10.58.27.1\n'
'Subnet: 255.255.255.0\n'
'DNS: 8.8.8.8 / 8.8.4.4\n\n'
'IMPORTANT: Driver updates require Windows Update access. Force Connect cannot repair a dead cable, failed switch port, ISP outage, or a Wi-Fi network that requires credentials which are not already saved.\n''')
root.mainloop()
