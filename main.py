# ================================================================
# HOSPITAL NETWORK DOCTOR
# ================================================================
# Application purpose:
#   This is a Windows-based network diagnosis and recovery tool
#   designed for use in a hospital environment.
#
# Main capabilities:
#   - Diagnose the current network configuration
#   - Check IPv4, subnet mask, gateway and DNS
#   - Test gateway connectivity
#   - Test DNS resolution
#   - Test Internet connectivity
#   - Repair network settings using manually supplied values
#   - Provide a "Trouble box" for entering network configuration
#   - Force network reconnection/recovery
#   - Rescan network devices
#   - Reconnect to an existing saved Wi-Fi profile
#   - Search Windows Update for applicable driver updates
#   - Display Ethernet physical/link/Internet status
#   - Maintain a log of important operations
#
# IMPORTANT:
#   Some operations require Administrator privileges because
#   Windows does not allow normal users to modify certain network
#   and driver settings.
# ================================================================


# ------------------------------------------------
# STANDARD PYTHON / SYSTEM LIBRARY IMPORTS
# ------------------------------------------------

# ctypes allows Python to communicate with Windows system APIs.
# It is used here to check whether the program is running
# with Administrator privileges.
import ctypes

# json is used for reading and writing the network configuration
# stored inside network_config.json.
import json

# platform provides information about the operating system.
# The diagnosis report uses it to identify the OS.
import platform

# re (regular expressions) is used to extract IP addresses,
# DNS servers and other information from command output.
import re

# socket provides networking-related functions.
# It is used here to test DNS resolution.
import socket

# subprocess allows Python to execute Windows commands such as:
#   ipconfig
#   ping
#   netsh
#   pnputil
#   PowerShell commands
import subprocess

# tkinter is Python's built-in GUI framework.
# It provides the main application window.
import tkinter as tk

# ttk provides modern-looking Tkinter widgets.
from tkinter import ttk, messagebox

# datetime is used to create timestamps for logs and reports.
from datetime import datetime

# Path provides a convenient and reliable way to work with files
# and directories.
from pathlib import Path

# threading allows long-running network operations to execute
# in the background without freezing the graphical interface.
import threading


# ================================================================
# APPLICATION INFORMATION
# ================================================================

# Name displayed throughout the application.
APP_NAME = 'Hospital Network Doctor'

# Current application version.
# Increment this whenever a significant version of the application
# is released.
VERSION = '2.0'

# BASE represents the directory where this Python script is located.
#
# Example:
# If main.py is located at:
# C:\HospitalNetworkDoctor\main.py
#
# BASE becomes:
# C:\HospitalNetworkDoctor
BASE = Path(__file__).resolve().parent

# Configuration file used by the application.
#
# This file stores hospital network settings and repair options.
CONFIG_FILE = BASE / 'network_config.json'

# Log file used to record diagnosis, repair and recovery operations.
LOG_FILE = BASE / 'network_doctor.log'


# ================================================================
# DEFAULT NETWORK CONFIGURATION
# ================================================================
# These are the baseline network values used by the application
# when a configuration file does not already exist.
#
# IMPORTANT:
# The IP address itself is intentionally NOT specified here because
# individual computers may require different unique static IPs.
# ================================================================

DEFAULT_CONFIG = {
    'network': {

        # Standard IPv4 subnet mask used by the hospital network.
        'subnet_mask': '255.255.255.0',

        # Default gateway used by the supplied hospital network
        # configuration.
        'gateway': '10.58.27.1',

        # Primary DNS server.
        'preferred_dns': '8.8.8.8',

        # Secondary/fallback DNS server.
        'alternate_dns': '8.8.4.4'
    },

    'repair': {

        # Individual computer's static IP address.
        # It is intentionally blank by default because each computer
        # may require a unique address.
        'ip_address': '',

        # Determines whether the automated repair function is allowed
        # to apply the static IP configuration.
        #
        # False = do not automatically apply a static IP.
        # True  = allow the repair function to use the configured IP.
        'apply_static_ip': False
    }
}


# ================================================================
# CONFIGURATION LOADING
# ================================================================

def load_config():
    """
    Load the application's network configuration.

    If network_config.json does not exist, this function creates it
    using DEFAULT_CONFIG.

    If the configuration file exists but cannot be read correctly,
    the function falls back to DEFAULT_CONFIG.

    Returns:
        dict:
            The network configuration used by the application.
    """

    # Check whether the configuration file exists.
    if not CONFIG_FILE.exists():

        # Create the configuration file using readable JSON formatting.
        CONFIG_FILE.write_text(
            json.dumps(DEFAULT_CONFIG, indent=4),
            encoding='utf-8'
        )

    try:
        # Read the configuration file and convert JSON into a Python
        # dictionary.
        return json.loads(
            CONFIG_FILE.read_text(encoding='utf-8')
        )

    except Exception:
        # If anything goes wrong while reading the configuration,
        # use a copy of the default configuration instead.
        return DEFAULT_CONFIG.copy()


# Load configuration once when the application starts.
CONFIG = load_config()


# ================================================================
# ADMINISTRATOR PRIVILEGE CHECK
# ================================================================

def is_admin():
    """
    Determine whether the application is running with
    Windows Administrator privileges.

    Returns:
        bool:
            True  -> program is running as Administrator.
            False -> program is not running as Administrator.
    """

    try:
        # Windows Shell32 API function used to determine whether
        # the current process has Administrator privileges.
        return bool(ctypes.windll.shell32.IsUserAnAdmin())

    except Exception:
        # If the Windows API cannot be accessed, assume the program
        # is not running as Administrator.
        return False


# ================================================================
# COMMAND EXECUTION ENGINE
# ================================================================

def run_command(command, timeout=60):
    """
    Execute a Windows command and capture its output.

    Args:
        command:
            Command to execute.

        timeout:
            Maximum amount of time allowed for the command.

    Returns:
        tuple:
            (return_code, output)

    Return code meanings:
        0   = command completed successfully
        -2  = command timed out
        -1  = Python encountered an execution error
    """

    try:
        # Execute the command through the Windows shell.
        p = subprocess.run(
            command,
            shell=True,

            # Capture standard output.
            capture_output=True,

            # Return output as strings rather than bytes.
            text=True,

            # Explicitly use UTF-8 when reading command output.
            encoding='utf-8',

            # Replace characters that cannot be decoded.
            errors='replace',

            # Prevent a command from running indefinitely.
            timeout=timeout
        )

        # Return Windows' exit code together with both stdout
        # and stderr.
        return p.returncode, (p.stdout + '\n' + p.stderr).strip()

    except subprocess.TimeoutExpired:
        # Special handling when the command takes too long.
        return -2, 'Command timed out.'

    except Exception as exc:
        # Return the exception message if another problem occurs.
        return -1, str(exc)


# ================================================================
# LOGGING SYSTEM
# ================================================================

def log_event(title, body):
    """
    Add an event to the application's log file.

    Every log entry receives a timestamp.

    Example:

        [2026-10-02 15:00:00] DIAGNOSIS
        Network diagnosis information...

    Args:
        title:
            Short name of the event.

        body:
            Detailed information about the event.
    """

    try:
        # Open the log file in append mode so previous logs
        # are preserved.
        with LOG_FILE.open('a', encoding='utf-8') as f:

            # Write timestamp, title and event details.
            f.write(
                f'\n[{datetime.now():%Y-%m-%d %H:%M:%S}] {title}\n'
                f'{body}\n'
            )

    except Exception:
        # Logging failure should never crash the application.
        pass


# ================================================================
# IP CONFIGURATION FUNCTIONS
# ================================================================

def get_ipconfig():
    """
    Run Windows ipconfig /all and return its output.

    ipconfig /all provides information such as:
        - IPv4 address
        - Subnet mask
        - Default gateway
        - DNS servers
        - Network adapters
        - DHCP information
    """

    return run_command('ipconfig /all')[1]


def parse_ipconfig(text):
    """
    Extract important network information from ipconfig /all output.

    The function searches the command output for:
        - IPv4 address
        - Subnet mask
        - Default gateway
        - DNS servers

    Args:
        text:
            Raw output produced by ipconfig /all.

    Returns:
        dict:
            Dictionary containing parsed network information.
    """

    # Structure used to store the extracted information.
    result = {
        'ipv4': '',
        'mask': '',
        'gateway': '',
        'dns': []
    }

    # Split command output into individual lines.
    lines = text.splitlines()

    # Used to determine whether subsequent lines belong
    # to the DNS server list.
    dns_section = False

    # Process every line returned by ipconfig.
    for raw in lines:

        # Remove unnecessary whitespace.
        line = raw.strip()

        # Ignore completely empty lines.
        if not line:
            continue

        # --------------------------------------------------------
        # SEARCH FOR IPV4 ADDRESS
        # --------------------------------------------------------

        m = re.search(
            r'IPv4 Address[^:]*:\s*([\d.]+)',
            line,
            re.I
        )

        # Only use the first IPv4 address discovered.
        if m and not result['ipv4']:
            result['ipv4'] = m.group(1)

        # --------------------------------------------------------
        # SEARCH FOR SUBNET MASK
        # --------------------------------------------------------

        m = re.search(
            r'Subnet Mask[^:]*:\s*([\d.]+)',
            line,
            re.I
        )

        if m and not result['mask']:
            result['mask'] = m.group(1)

        # --------------------------------------------------------
        # SEARCH FOR DEFAULT GATEWAY
        # --------------------------------------------------------

        m = re.search(
            r'Default Gateway[^:]*:\s*([\d.]+)',
            line,
            re.I
        )

        # Ignore the meaningless 0.0.0.0 gateway value.
        if m and m.group(1) != '0.0.0.0':
            result['gateway'] = m.group(1)

        # --------------------------------------------------------
        # SEARCH FOR DNS SERVERS
        # --------------------------------------------------------

        m = re.search(
            r'DNS Servers[^:]*:\s*([\d.]+)',
            line,
            re.I
        )

        if m:
            # Store the first DNS server.
            result['dns'].append(m.group(1))

            # Tell the parser that following indented lines may
            # contain additional DNS servers.
            dns_section = True

        elif dns_section and re.fullmatch(r'[\d.]+', line):

            # Additional DNS servers may appear on separate
            # indented lines.
            result['dns'].append(line)

        elif not raw.startswith((' ', '\t')):

            # Leaving the indented DNS section means the parser
            # should stop treating subsequent lines as DNS entries.
            dns_section = False

    # Return all extracted network information.
    return result


# ================================================================
# NETWORK CONNECTIVITY TESTING
# ================================================================

def ping(host):
    """
    Ping a specified host using Windows ping.

    The application sends two ICMP requests.

    Args:
        host:
            IP address or hostname to ping.

    Returns:
        tuple:
            (True/False, command_output)
    """

    code, output = run_command(
        f'ping -n 2 -w 1500 "{host}"',
        timeout=10
    )

    # A return code of zero means ping succeeded.
    return code == 0, output


def dns_test():
    """
    Test DNS resolution.

    Instead of directly pinging a hostname, the function asks
    the operating system to resolve www.google.com to an IP address.

    Returns:
        tuple:
            (True, success_message)
            or
            (False, failure_message)
    """

    try:
        # Attempt to resolve Google's hostname.
        socket.gethostbyname('www.google.com')

        return True, 'DNS resolution succeeded.'

    except Exception as exc:

        # Return the specific DNS error.
        return False, f'DNS resolution failed: {exc}'


def internet_test():
    """
    Test basic Internet reachability.

    Google DNS server 8.8.8.8 is used as the destination.

    Returns:
        tuple:
            (True/False, ping_output)
    """

    ok, output = ping('8.8.8.8')

    return ok, output


# ================================================================
# IPV4 VALIDATION
# ================================================================

def validate_ipv4(ip):
    """
    Validate whether a supplied string looks like a valid IPv4 address.

    A valid IPv4 address contains four numeric sections.

    Example:
        192.168.1.10

    Each section must be between 0 and 255.

    Returns:
        True  -> valid IPv4 format
        False -> invalid IPv4 format
    """

    # Remove surrounding spaces and split on periods.
    parts = ip.strip().split('.')

    # IPv4 must contain exactly four sections.
    if len(parts) != 4:
        return False

    try:
        # Every section must be between 0 and 255.
        return all(0 <= int(p) <= 255 for p in parts)

    except ValueError:
        # A non-numeric section makes the address invalid.
        return False


# ================================================================
# NETWORK DIAGNOSIS
# ================================================================

def diagnose():
    """
    Perform a complete network diagnosis.

    The diagnosis checks:

        1. Current IP configuration
        2. APIPA address
        3. Subnet mask
        4. Default gateway
        5. DNS configuration
        6. Gateway connectivity
        7. DNS resolution
        8. Internet reachability

    A readable report is generated and saved to the log.
    """

    # Get the approved hospital network configuration.
    cfg = CONFIG['network']

    # Obtain current Windows network configuration.
    current = parse_ipconfig(get_ipconfig())

    # Build the diagnosis report.
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

    # Number of detected problems.
    failures = 0

    # ------------------------------------------------------------
    # CHECK IPV4 ADDRESS
    # ------------------------------------------------------------

    # 169.254.x.x is an APIPA address.
    # Windows can assign this type of address when DHCP fails.
    if current['ipv4'].startswith('169.254.'):

        out.append(
            'FAIL - APIPA address detected (169.254.x.x).'
        )

        failures += 1

    elif current['ipv4']:

        out.append(
            'PASS - IPv4 address is assigned.'
        )

    else:

        out.append(
            'FAIL - No IPv4 address detected.'
        )

        failures += 1

    # ------------------------------------------------------------
    # CHECK SUBNET MASK
    # ------------------------------------------------------------

    if current['mask'] == cfg['subnet_mask']:

        out.append(
            'PASS - Subnet mask matches approved configuration.'
        )

    else:

        out.append(
            f"FAIL - Subnet mask is "
            f"{current['mask'] or 'missing'}; "
            f"expected {cfg['subnet_mask']}."
        )

        failures += 1

    # ------------------------------------------------------------
    # CHECK DEFAULT GATEWAY
    # ------------------------------------------------------------

    if current['gateway'] == cfg['gateway']:

        out.append(
            'PASS - Default gateway matches approved configuration.'
        )

    else:

        out.append(
            f"FAIL - Gateway is "
            f"{current['gateway'] or 'missing'}; "
            f"expected {cfg['gateway']}."
        )

        failures += 1

    # ------------------------------------------------------------
    # CHECK DNS
    # ------------------------------------------------------------

    # At least one of the approved DNS servers must be present.
    if (
        cfg['preferred_dns'] in current['dns']
        or cfg['alternate_dns'] in current['dns']
    ):

        out.append(
            'PASS - At least one approved DNS server is present.'
        )

    else:

        out.append(
            'FAIL - Approved DNS servers were not detected.'
        )

        failures += 1

    # ------------------------------------------------------------
    # CONNECTIVITY TESTS
    # ------------------------------------------------------------

    out += ['', 'CONNECTIVITY TESTS']

    # Test the gateway if one exists.
    if current['gateway']:

        ok, _ = ping(current['gateway'])

        out.append(
            ('PASS' if ok else 'FAIL')
            + f' - Gateway ping ({current["gateway"]})'
        )

        # Convert False into 1 failure and True into 0 failures.
        failures += int(not ok)

    else:

        out.append(
            'SKIP - No gateway to test.'
        )

    # ------------------------------------------------------------
    # DNS CONNECTIVITY TEST
    # ------------------------------------------------------------

    ok_dns, dns_msg = dns_test()

    out.append(
        ('PASS' if ok_dns else 'FAIL')
        + ' - '
        + dns_msg
    )

    failures += int(not ok_dns)

    # ------------------------------------------------------------
    # INTERNET CONNECTIVITY TEST
    # ------------------------------------------------------------

    ok_net, _ = internet_test()

    out.append(
        ('PASS' if ok_net else 'FAIL')
        + ' - Internet reachability (8.8.8.8)'
    )

    failures += int(not ok_net)

    # ------------------------------------------------------------
    # FINAL DIAGNOSIS RESULT
    # ------------------------------------------------------------

    out += [
        '',
        f'FINAL RESULT: '
        f'{"PROBLEM DETECTED" if failures else "NO OBVIOUS PROBLEM"}'
    ]

    if failures:

        out.append(
            'Review FAIL items before making network changes.'
        )

    else:

        out.append(
            'The PC passed the basic configuration and connectivity checks.'
        )

    # Convert the list of report lines into one large text block.
    text = '\n'.join(out)

    # Save the diagnosis into the application log.
    log_event('DIAGNOSIS', text)

    # Return the report to the GUI.
    return text


# ================================================================
# ACTIVE NETWORK ADAPTER DETECTION
# ================================================================

def find_active_adapter():
    """
    Find the first active network adapter that has an IPv4 address.

    PowerShell is used because it provides structured network
    information that is easier to query than raw ipconfig output.

    Returns:
        str:
            Interface name, or an empty string if none is found.
    """

    cmd = (
        'powershell -NoProfile -Command "Get-NetIPConfiguration | '
        'Where-Object {$_.IPv4Address -and $_.NetAdapter.Status -eq \'Up\'} | '
        'Select-Object -First 1 -ExpandProperty InterfaceAlias"'
    )

    # Execute the PowerShell command.
    _, output = run_command(cmd)

    # Return the first adapter name.
    return output.strip().splitlines()[0] if output.strip() else ''


# ================================================================
# NETWORK ADAPTER INFORMATION
# ================================================================

def get_network_adapters():
    """
    Retrieve information about installed network adapters.

    Information includes:
        - Adapter name
        - Interface description
        - Status
        - Link speed
        - MAC address
    """

    cmd = (
        'powershell -NoProfile -Command "Get-NetAdapter | '
        'Select-Object Name,InterfaceDescription,Status,LinkSpeed,MacAddress | '
        'Format-Table -AutoSize | Out-String"'
    )

    return run_command(cmd)[1]


# ================================================================
# AUTOMATED NETWORK REPAIR
# ================================================================

def repair():
    """
    Perform controlled network repair using values stored
    in network_config.json.

    Because assigning a static IP incorrectly can cause an
    IP conflict, this function only proceeds when:

        apply_static_ip = True

    is explicitly enabled in the configuration file.
    """

    # Network configuration changes require Administrator privileges.
    if not is_admin():

        messagebox.showerror(
            APP_NAME,
            'Run this program as Administrator before repairing network settings.'
        )

        return

    # Load the approved network configuration.
    cfg = CONFIG['network']

    # Get repair-specific configuration.
    repair_cfg = CONFIG.get('repair', {})

    # Determine whether static IP repair is enabled.
    apply_static_ip = bool(
        repair_cfg.get('apply_static_ip', False)
    )

    # Read the computer's configured IP address.
    ip = str(
        repair_cfg.get('ip_address', '')
    ).strip()

    # If static IP repair is enabled, make sure the IP is valid.
    if apply_static_ip and not validate_ipv4(ip):

        messagebox.showerror(
            APP_NAME,
            'network_config.json has no valid per-PC IP address.'
        )

        return

    # Find the active network adapter.
    adapter = find_active_adapter()

    if not adapter:

        messagebox.showerror(
            APP_NAME,
            'Could not find an active IPv4 network adapter.'
        )

        return

    # Prevent accidental use of static IP repair.
    if not apply_static_ip:

        messagebox.showwarning(
            APP_NAME,
            'Safe repair is not enabled.\n\n'
            'Each PC may require a unique static IP. Confirm the correct IP for this particular computer '
            'before enabling static-IP repair in network_config.json.'
        )

        return

    # ------------------------------------------------------------
    # COMMANDS USED FOR REPAIR
    # ------------------------------------------------------------

    commands = [

        # Assign the static IPv4 address, subnet mask and gateway.
        f'netsh interface ipv4 set address name="{adapter}" static {ip} {cfg["subnet_mask"]} {cfg["gateway"]}',

        # Set the preferred DNS server.
        f'netsh interface ipv4 set dns name="{adapter}" static {cfg["preferred_dns"]}',

        # Add the alternate DNS server.
        f'netsh interface ipv4 add dns name="{adapter}" {cfg["alternate_dns"]} index=2',

        # Clear the local DNS resolver cache.
        'ipconfig /flushdns'
    ]

    results = []

    # Execute each repair command.
    for command in commands:

        code, output = run_command(command)

        results.append(
            f'$ {command}\n'
            f'{output}\n'
            f'Exit code: {code}'
        )

    # Combine all command results into one report.
    text = '\n\n'.join(results)

    # Record repair activity.
    log_event('REPAIR', text)

    # Display the result.
    show_output(
        text
        + '\n\nRun diagnosis again to verify the repair.'
    )


# ================================================================
# TRYFIX WINDOW
# ================================================================

def tryfix_window():
    """
    Open the manual network configuration window.

    This provides fields for:
        - IP address
        - Subnet mask
        - Default gateway
        - Preferred DNS
        - Alternative DNS
    """

    # Administrator privileges are required.
    if not is_admin():

        messagebox.showerror(
            APP_NAME,
            'Run this program as Administrator before changing network settings.'
        )

        return

    # Load approved configuration.
    cfg = CONFIG['network']

    # Read the current network configuration.
    current = parse_ipconfig(get_ipconfig())

    # Create a child window.
    win = tk.Toplevel(root)

    win.title('Trouble box')
    win.geometry('480x330')

    # Prevent resizing.
    win.resizable(False, False)

    # Keep this window associated with the main window.
    win.transient(root)

    # Prevent interaction with the main window while this dialog
    # is active.
    win.grab_set()

    # ------------------------------------------------------------
    # INPUT FIELDS
    # ------------------------------------------------------------

    fields = [
        ('IP address', current['ipv4']),
        ('Submask', current['mask'] or cfg['subnet_mask']),
        ('Default gateway', current['gateway'] or cfg['gateway']),
        ('Preferred DNS server', current['dns'][0] if current['dns'] else cfg['preferred_dns']),
        ('Alternative DNS server', current['dns'][1] if len(current['dns']) > 1 else cfg['alternate_dns'])
    ]

    # Dictionary used to store each Entry widget.
    entries = {}

    # Main content container.
    body = ttk.Frame(win, padding=15)
    body.pack(fill='both', expand=True)

    # Window heading.
    ttk.Label(
        body,
        text='Trouble box',
        font=('Segoe UI', 15, 'bold')
    ).grid(
        row=0,
        column=0,
        columnspan=2,
        sticky='w',
        pady=(0, 12)
    )

    # Create each network configuration input field.
    for row, (label, value) in enumerate(fields, start=1):

        # Display field label.
        ttk.Label(
            body,
            text=label + ':'
        ).grid(
            row=row,
            column=0,
            sticky='w',
            pady=5
        )

        # Create input field.
        e = ttk.Entry(
            body,
            width=35
        )

        # Put current network value into the field.
        e.insert(0, value)

        # Position input field.
        e.grid(
            row=row,
            column=1,
            sticky='ew',
            pady=5
        )

        # Store the field so it can later be read.
        entries[label] = e

    # Warning message reminding the technician about unique IPs.
    ttk.Label(
        body,
        text='Enter the correct settings for this PC. Avoid duplicate IP addresses.',
        foreground='red'
    ).grid(
        row=6,
        column=0,
        columnspan=2,
        sticky='w',
        pady=(8, 10)
    )

    # Container for action buttons.
    buttons = ttk.Frame(body)

    buttons.grid(
        row=7,
        column=0,
        columnspan=2,
        sticky='e'
    )

    # ------------------------------------------------------------
    # RELOAD CURRENT NETWORK VALUES
    # ------------------------------------------------------------

    def reload_current():
        """
        Refresh all fields with the computer's current network values.
        """

        # Read the network configuration again.
        fresh = parse_ipconfig(get_ipconfig())

        # Build the values to place into the form.
        values = [
            fresh['ipv4'],
            fresh['mask'] or cfg['subnet_mask'],
            fresh['gateway'] or cfg['gateway'],
            fresh['dns'][0] if fresh['dns'] else cfg['preferred_dns'],
            fresh['dns'][1] if len(fresh['dns']) > 1 else cfg['alternate_dns']
        ]

        # Update each Entry widget.
        for e, value in zip(entries.values(), values):

            e.delete(0, tk.END)
            e.insert(0, value)

    # ------------------------------------------------------------
    # APPLY MANUAL NETWORK FIX
    # ------------------------------------------------------------

    def apply_tryfix():
        """
        Validate the values entered into the Trouble box,
        confirm the changes with the user and apply them.
        """

        # Read all five fields.
        values = {
            k: e.get().strip()
            for k, e in entries.items()
        }

        # Every field must contain a valid IPv4 address.
        if not all(
            validate_ipv4(v)
            for v in values.values()
        ):

            messagebox.showerror(
                'Trouble box',
                'All five fields must contain valid IPv4 addresses.',
                parent=win
            )

            return

        # APIPA addresses should not be manually assigned
        # as static addresses.
        if values['IP address'].startswith('169.254.'):

            messagebox.showerror(
                'Trouble box',
                'Do not use an APIPA address as a static IP.',
                parent=win
            )

            return

        # Locate the active network adapter.
        adapter = find_active_adapter()

        if not adapter:

            messagebox.showerror(
                'Trouble box',
                'No active network adapter was found.',
                parent=win
            )

            return

        # --------------------------------------------------------
        # CONFIRM NETWORK CHANGE
        # --------------------------------------------------------

        confirm = messagebox.askyesno(
            'Confirm network change',

            f'Adapter: {adapter}\n\n'
            f'IP: {current["ipv4"] or "missing"}  →  {values["IP address"]}\n'
            f'Subnet: {current["mask"] or "missing"}  →  {values["Submask"]}\n'
            f'Gateway: {current["gateway"] or "missing"}  →  {values["Default gateway"]}\n'
            f'DNS: {", ".join(current["dns"]) or "missing"}  →  {values["Preferred DNS server"]}, {values["Alternative DNS server"]}\n\n'
            'Continue?',
            parent=win
        )

        # If the user selects No, do nothing.
        if not confirm:
            return

        # --------------------------------------------------------
        # NETWORK CONFIGURATION COMMANDS
        # --------------------------------------------------------

        commands = [

            # Apply static IP, subnet mask and gateway.
            f'netsh interface ipv4 set address name="{adapter}" static {values["IP address"]} {values["Submask"]} {values["Default gateway"]}',

            # Apply preferred DNS.
            f'netsh interface ipv4 set dns name="{adapter}" static {values["Preferred DNS server"]}',

            # Add alternative DNS.
            f'netsh interface ipv4 add dns name="{adapter}" {values["Alternative DNS server"]} index=2',

            # Clear DNS cache.
            'ipconfig /flushdns'
        ]

        results = []

        # Run each command individually.
        for command in commands:

            code, output = run_command(command)

            results.append(
                f'$ {command}\n'
                f'{output}\n'
                f'Exit code: {code}'
            )

        # Create a complete repair report.
        text = '\n\n'.join(results)

        # Save repair information to the log.
        log_event('TRYFIX', text)

        # Close the Trouble box.
        win.destroy()

        # Show the repair results.
        show_output(
            text
            + '\n\nRunning verification...'
        )

        # Wait 500 milliseconds and then run diagnosis.
        root.after(
            500,
            run_diagnosis
        )

    # ------------------------------------------------------------
    # TROUBLE BOX BUTTONS
    # ------------------------------------------------------------

    ttk.Button(
        buttons,
        text='Reload Current',
        command=reload_current
    ).pack(
        side='left',
        padx=5
    )

    ttk.Button(
        buttons,
        text='Apply',
        command=apply_tryfix
    ).pack(
        side='left',
        padx=5
    )

    ttk.Button(
        buttons,
        text='Cancel',
        command=win.destroy
    ).pack(
        side='left',
        padx=5
    )

    # Pressing Enter applies the network settings.
    win.bind(
        '<Return>',
        lambda event: apply_tryfix()
    )

    # Pressing Escape closes the window.
    win.bind(
        '<Escape>',
        lambda event: win.destroy()
    )


# ================================================================
# FORCE CONNECT WORKER
# ================================================================
# This function performs several network recovery operations.
#
# It is intentionally run in a separate thread because commands
# such as driver/device scans and DHCP renewal can take time.
# ================================================================

def force_connect_worker():

    # Administrator privileges are required.
    if not is_admin():

        root.after(
            0,
            lambda: messagebox.showerror(
                APP_NAME,
                'Run this program as Administrator to use Force Connect.'
            )
        )

        return

    # List used to store the result of every recovery step.
    steps = []

    # ------------------------------------------------------------
    # ENABLE DISABLED PHYSICAL NETWORK ADAPTERS
    # ------------------------------------------------------------

    code, output = run_command(
        'powershell -NoProfile -Command "Get-NetAdapter | Where-Object {$_.Status -eq \'Disabled\'} | Enable-NetAdapter -Confirm:$false"'
    )

    steps.append(
        f'ENABLE DISABLED ADAPTERS\n'
        f'{output}\n'
        f'Exit code: {code}'
    )

    # ------------------------------------------------------------
    # RESTART ACTIVE NETWORK ADAPTER
    # ------------------------------------------------------------
    # If Windows reports an active adapter, restart it to refresh
    # the network interface.
    # ------------------------------------------------------------

    adapter = find_active_adapter()

    if adapter:

        code, output = run_command(
            f'powershell -NoProfile -Command "Restart-NetAdapter -Name \'{adapter.replace(chr(39), chr(39)+chr(39))}\' -Confirm:$false"',
            timeout=45
        )

        steps.append(
            f'RESTART ADAPTER: {adapter}\n'
            f'{output}\n'
            f'Exit code: {code}'
        )

    # ------------------------------------------------------------
    # RELEASE CURRENT IP CONFIGURATION
    # ------------------------------------------------------------

    code, output = run_command(
        'ipconfig /release',
        timeout=30
    )

    steps.append(
        f'RELEASE IP\n'
        f'{output}\n'
        f'Exit code: {code}'
    )

    # ------------------------------------------------------------
    # REQUEST A NEW DHCP CONFIGURATION
    # ------------------------------------------------------------

    code, output = run_command(
        'ipconfig /renew',
        timeout=45
    )

    steps.append(
        f'RENEW IP\n'
        f'{output}\n'
        f'Exit code: {code}'
    )

    # ------------------------------------------------------------
    # CLEAR DNS CACHE
    # ------------------------------------------------------------

    code, output = run_command(
        'ipconfig /flushdns',
        timeout=15
    )

    steps.append(
        f'FLUSH DNS\n'
        f'{output}\n'
        f'Exit code: {code}'
    )

    # ------------------------------------------------------------
    # RESCAN WINDOWS NETWORK DEVICES
    # ------------------------------------------------------------

    code, output = run_command(
        'pnputil /scan-devices',
        timeout=60
    )

    steps.append(
        f'SCAN DEVICES\n'
        f'{output}\n'
        f'Exit code: {code}'
    )

    # ------------------------------------------------------------
    # RECONNECT USING A SAVED WI-FI PROFILE
    # ------------------------------------------------------------

    # Ask Windows for saved Wi-Fi profiles.
    code, profiles = run_command(
        'netsh wlan show profiles',
        timeout=15
    )

    if code == 0:

        # Extract profile names from Windows command output.
        names = re.findall(
            r'All User Profile\s*:\s*(.+)',
            profiles,
            re.I
        )

        if names:

            # Use the first saved profile.
            profile = names[0].strip()

            # Escape quotation marks before placing the name
            # inside the command.
            safe_profile = profile.replace(
                '"',
                '\\"'
            )

            # Ask Windows to connect to the saved Wi-Fi network.
            code, output = run_command(
                f'netsh wlan connect name="{safe_profile}"',
                timeout=20
            )

            steps.append(
                f'WIFI RECONNECT: {profile}\n'
                f'{output}\n'
                f'Exit code: {code}'
            )

        else:

            steps.append(
                'WIFI RECONNECT\n'
                'No saved Wi-Fi profile was found.'
            )

    else:

        steps.append(
            f'WIFI PROFILE CHECK\n'
            f'{profiles}\n'
            f'Exit code: {code}'
        )

    # ------------------------------------------------------------
    # WAIT BEFORE VERIFYING CONNECTION
    # ------------------------------------------------------------

    # Imported here because the delay is only needed by this
    # background operation.
    import time

    # Give Windows a few seconds to reconnect.
    time.sleep(3)

    # Read the network configuration after recovery.
    current = parse_ipconfig(get_ipconfig())

    # Default verification values.
    gateway_ok = False
    dns_ok = False
    net_ok = False

    # Test the gateway if one is available.
    if current['gateway']:

        gateway_ok, _ = ping(
            current['gateway']
        )

    # Test DNS.
    dns_ok, dns_msg = dns_test()

    # Test Internet.
    net_ok, _ = internet_test()

    # Combine all recovery steps into one report.
    result = '\n\n'.join(steps)

    # Add verification results.
    result += (
        '\n\nFORCE CONNECT VERIFICATION\n'
        f'IPv4: {current["ipv4"] or "NOT FOUND"}\n'
        f'Gateway: {current["gateway"] or "NOT FOUND"}\n'
        f'Gateway reachable: {"YES" if gateway_ok else "NO"}\n'
        f'DNS: {"OK" if dns_ok else "FAILED"} ({dns_msg})\n'
        f'Internet reachable: {"YES" if net_ok else "NO"}'
    )

    # Save Force Connect operation to the log.
    log_event(
        'FORCE CONNECT',
        result
    )

    # Schedule the GUI update on the main Tkinter thread.
    root.after(
        0,
        lambda: finish_force_connect(
            result,
            net_ok
        )
    )


# ================================================================
# FORCE CONNECT RESULT HANDLER
# ================================================================

def finish_force_connect(result, internet_ok):
    """
    Display the Force Connect results and inform the user
    whether Internet access was successfully verified.
    """

    # Display complete recovery report.
    show_output(result)

    # If Internet access works, show success message.
    if internet_ok:

        messagebox.showinfo(
            APP_NAME,
            'Force Connect completed and Internet access was verified.'
        )

    else:

        # If Internet access still fails, explain that some problems
        # cannot be fixed by software alone.
        messagebox.showwarning(
            APP_NAME,
            'Force Connect completed its recovery steps, but Internet access could not be verified.\n\n'
            'Check the physical/Wi-Fi connection, IP/gateway settings, or the hospital network itself.'
        )


# ================================================================
# FORCE CONNECT BUTTON HANDLER
# ================================================================

def force_connect():
    """
    Start the Force Connect process.

    The actual recovery work runs in a background thread so that
    the GUI remains responsive.
    """

    # Administrator privileges are required.
    if not is_admin():

        messagebox.showerror(
            APP_NAME,
            'Run this program as Administrator to use Force Connect.'
        )

        return

    # Inform the user that the recovery process is running.
    show_output(
        'FORCE CONNECT\n\n'
        'Working... Please wait.\n'
    )

    # Start the background worker.
    threading.Thread(
        target=force_connect_worker,
        daemon=True
    ).start()


# ================================================================
# DRIVER UPDATE WORKER
# ================================================================

def update_driver_worker():
    """
    Search Windows Update for applicable driver updates
    and install them.

    This operation runs in a background thread because Windows
    Update operations can take several minutes.
    """

    # Driver installation requires Administrator privileges.
    if not is_admin():

        root.after(
            0,
            lambda: messagebox.showerror(
                APP_NAME,
                'Run this program as Administrator to update drivers.'
            )
        )

        return

    # Store the steps performed by the driver update process.
    steps = []

    # Get current network adapter information.
    adapters = get_network_adapters()

    steps.append(
        'NETWORK ADAPTERS\n'
        + adapters
    )

    # ------------------------------------------------------------
    # WINDOWS UPDATE DRIVER SEARCH AND INSTALLATION
    # ------------------------------------------------------------
    # This PowerShell script communicates with the Windows Update
    # Agent and searches for applicable driver-class updates.
    # ------------------------------------------------------------

    ps = r'''$session = New-Object -ComObject Microsoft.Update.Session; $searcher = $session.CreateUpdateSearcher(); $result = $searcher.Search("IsInstalled=0 and Type='Driver'"); Write-Output ("Found driver updates: " + $result.Updates.Count); for ($i=0; $i -lt $result.Updates.Count; $i++) { Write-Output ("UPDATE " + ($i+1) + ": " + $result.Updates.Item($i).Title) }; if ($result.Updates.Count -gt 0) { $updates = New-Object -ComObject Microsoft.Update.UpdateColl; for ($i=0; $i -lt $result.Updates.Count; $i++) { $u=$result.Updates.Item($i); if (-not $u.EulaAccepted) { $u.AcceptEula() }; [void]$updates.Add($u) }; $downloader=$session.CreateUpdateDownloader(); $downloader.Updates=$updates; $d=$downloader.Download(); Write-Output ("Download result: " + $d.ResultCode); $installer=$session.CreateUpdateInstaller(); $installer.Updates=$updates; $r=$installer.Install(); Write-Output ("Install result: " + $r.ResultCode); Write-Output ("Reboot required: " + $r.RebootRequired) }'''

    # Build the final PowerShell command.
    command = (
        'powershell -NoProfile -ExecutionPolicy Bypass -Command "'
        + ps.replace('"', '\\"')
        + '"'
    )

    # Execute the driver update process.
    code, output = run_command(
        command,
        timeout=600
    )

    steps.append(
        'WINDOWS UPDATE DRIVER PROCESS\n'
        + output
        + f'\nExit code: {code}'
    )

    # ------------------------------------------------------------
    # RESCAN DEVICES AFTER DRIVER UPDATE
    # ------------------------------------------------------------

    code, output = run_command(
        'pnputil /scan-devices',
        timeout=60
    )

    steps.append(
        'DEVICE RESCAN\n'
        + output
        + f'\nExit code: {code}'
    )

    # Combine all results.
    result = '\n\n'.join(steps)

    # Save driver update activity to the log.
    log_event(
        'UPDATE DRIVER',
        result
    )

    # Return result to GUI thread.
    root.after(
        0,
        lambda: finish_driver_update(result)
    )


# ================================================================
# DRIVER UPDATE RESULT HANDLER
# ================================================================

def finish_driver_update(result):
    """
    Display the driver update report and provide an appropriate
    status message.
    """

    # Show detailed report.
    show_output(result)

    # Windows explicitly says a restart is needed.
    if 'Reboot required: True' in result:

        messagebox.showwarning(
            APP_NAME,
            'Network driver update completed, but Windows reports that a restart is required.'
        )

    # Windows found no applicable driver updates.
    elif 'Found driver updates: 0' in result:

        messagebox.showinfo(
            APP_NAME,
            'Windows did not find an applicable driver update. '
            'The installed network driver may already be current.'
        )

    else:

        messagebox.showinfo(
            APP_NAME,
            'The driver update process has completed. '
            'Review the report above and run Diagnosis afterward.'
        )


# ================================================================
# UPDATE DRIVER BUTTON HANDLER
# ================================================================

def update_driver():
    """
    Start the driver update process after asking the technician
    for confirmation.
    """

    # Administrator privileges are required.
    if not is_admin():

        messagebox.showerror(
            APP_NAME,
            'Run this program as Administrator to update drivers.'
        )

        return

    # Confirm that the technician really wants to start the
    # Windows Update driver process.
    confirm = messagebox.askyesno(
        APP_NAME,
        'Update Driver will ask Windows for applicable network/device driver updates through Windows Update.\n\n'
        'The process may take several minutes and may require a restart. Continue?'
    )

    # Stop if the user selects No.
    if not confirm:
        return

    # Display progress message.
    show_output(
        'UPDATE DRIVER\n\n'
        'Checking Windows Update for applicable drivers...\n'
        'This may take several minutes.\n'
    )

    # Run the update in the background.
    threading.Thread(
        target=update_driver_worker,
        daemon=True
    ).start()


# ================================================================
# GUI OUTPUT FUNCTION
# ================================================================

def show_output(text):
    """
    Replace the contents of the main output text area
    with the supplied text.
    """

    # Remove previous output.
    output.delete(
        '1.0',
        tk.END
    )

    # Insert new output.
    output.insert(
        tk.END,
        text
    )

    # Scroll to the beginning of the output.
    output.see('1.0')


# ================================================================
# DIAGNOSIS BUTTON HANDLER
# ================================================================

def run_diagnosis():
    """
    Start a network diagnosis and display its results.
    """

    # Inform the user that diagnosis is running.
    show_output(
        'Running diagnosis...\n'
    )

    # Force Tkinter to refresh the interface immediately.
    root.update_idletasks()

    # Perform diagnosis and display its result.
    show_output(
        diagnose()
    )


# ================================================================
# OPEN CONFIGURATION FILE
# ================================================================

def open_config():
    """
    Open the network configuration file using the Windows
    default application associated with JSON files.
    """

    # Ensure the file exists.
    CONFIG_FILE.touch(
        exist_ok=True
    )

    # Import os only when needed.
    import os

    # Ask Windows to open the file.
    os.startfile(
        CONFIG_FILE
    )


# ================================================================
# ETHERNET STATUS DETECTION
# ================================================================
# This section provides the Ethernet status indicator requested
# for the application.
#
# Possible statuses:
#
#   1. INTERNET
#      Physical Ethernet connection exists and Internet works.
#
#   2. NO INTERNET
#      Physical Ethernet connection exists but Internet cannot
#      be reached.
#
#   3. NO CABLE
#      No physical Ethernet connection is detected.
# ================================================================

def get_ethernet_status():
    """
    Return Ethernet physical/link/internet status for the status indicator.
    """

    # PowerShell command used to query physical network adapters.
    #
    # Wi-Fi/Wireless/WLAN adapters are excluded because this
    # indicator is specifically intended for Ethernet.
    ps = "$adapters = Get-NetAdapter -Physical -ErrorAction SilentlyContinue | " \
         "Where-Object {$_.Name -notmatch 'Wi-Fi|Wireless|WLAN'} | " \
         "Select-Object Name, MediaConnectionState, Status, LinkSpeed; " \
         "$adapters | ForEach-Object { " \
         "Write-Output ('NAME=' + $_.Name); " \
         "Write-Output ('STATE=' + $_.MediaConnectionState); " \
         "Write-Output ('STATUS=' + $_.Status) }"

    # Convert the PowerShell script into a Windows command.
    command = (
        'powershell -NoProfile -Command "'
        + ps.replace('"', '\\"')
        + '"'
    )

    # Execute the adapter status query.
    code, output = run_command(
        command,
        timeout=10
    )

    # If PowerShell fails or provides no output,
    # assume that no cable is detected.
    if code != 0 or not output.strip():

        return 'no_cable', 'NO CABLE'

    # Used to determine whether an Ethernet adapter is connected.
    connected = False

    # Inspect every line returned by PowerShell.
    for line in output.splitlines():

        # Normalize the line for easier comparison.
        line = line.strip().upper()

        # Either of these states indicates an active connection.
        if (
            line == 'STATE=CONNECTED'
            or line == 'STATUS=UP'
        ):

            connected = True
            break

    # If no active physical connection was detected,
    # display NO CABLE.
    if not connected:

        return 'no_cable', 'NO CABLE'

    # ------------------------------------------------------------
    # INTERNET TEST
    # ------------------------------------------------------------

    # Physical Ethernet is connected, so now test whether
    # Internet access actually works.
    internet_ok, _ = internet_test()

    if internet_ok:

        # Ethernet + Internet.
        return (
            'internet',
            'CONNECTED WITH INTERNET'
        )

    # Ethernet exists but Internet is unavailable.
    return (
        'no_internet',
        'CONNECTED WITHOUT INTERNET'
    )


# ================================================================
# ETHERNET STATUS MONITOR
# ================================================================

def update_ethernet_indicator():
    """
    Refresh the Ethernet status badge without blocking the GUI.

    The network test is executed in a background thread because
    ping/network checks can take time.
    """

    # Background worker responsible for checking status.
    def worker():

        # Get current Ethernet state.
        status, message = get_ethernet_status()

        # Schedule GUI modification on Tkinter's main thread.
        root.after(
            0,
            lambda: set_ethernet_indicator(
                status,
                message
            )
        )

    # Start background network check.
    threading.Thread(
        target=worker,
        daemon=True
    ).start()


# ================================================================
# UPDATE ETHERNET STATUS BADGE
# ================================================================

def set_ethernet_indicator(status, message):
    """
    Update the top-right Ethernet icon/status badge.

    Status colors:

        Green:
            Connected with Internet.

        Red:
            Ethernet connected but Internet unavailable.

        Grey:
            No physical Ethernet cable detected.
    """

    # ------------------------------------------------------------
    # CONNECTED + INTERNET
    # ------------------------------------------------------------

    if status == 'internet':

        ethernet_badge.configure(
            text='  🖧  CONNECTED WITH INTERNET  ',
            foreground='white',
            background='#16a34a'
        )

    # ------------------------------------------------------------
    # CONNECTED + NO INTERNET
    # ------------------------------------------------------------

    elif status == 'no_internet':

        ethernet_badge.configure(
            text='  🖧  CONNECTED WITHOUT INTERNET  ',
            foreground='white',
            background='#dc2626'
        )

    # ------------------------------------------------------------
    # NO PHYSICAL CABLE
    # ------------------------------------------------------------

    else:

        ethernet_badge.configure(
            text='  🖧  NO CABLE  ',
            foreground='#333333',
            background='#d1d5db'
        )

    # Schedule another status check after five seconds.
    #
    # This creates a continuous monitoring loop:
    #
    # check → update → wait 5 sec → check again
    root.after(
        5000,
        update_ethernet_indicator
    )


# ================================================================
# MAIN TKINTER APPLICATION WINDOW
# ================================================================
# Everything below this point builds the graphical interface.
# ================================================================

# Create the main application window.
root = tk.Tk()

# Set the window title including application version.
root.title(
    APP_NAME
    + f' v{VERSION}'
)

# Set initial window size.
root.geometry(
    '980x700'
)

# Prevent the application from becoming too small to use.
root.minsize(
    820,
    580
)


# ================================================================
# TKINTER STYLE
# ================================================================

# Create ttk style manager.
style = ttk.Style()

try:

    # Use the Windows Vista-style theme when available.
    style.theme_use('vista')

except tk.TclError:

    # If the theme isn't available, simply continue using
    # Tkinter's default theme.
    pass


# ================================================================
# APPLICATION HEADER
# ================================================================

# Main header container.
header = ttk.Frame(
    root,
    padding=15
)

header.pack(
    fill='x'
)


# ------------------------------------------------
# LEFT SIDE OF HEADER
# ------------------------------------------------

header_left = ttk.Frame(
    header
)

header_left.pack(
    side='left',
    fill='x',
    expand=True
)

# Application name.
ttk.Label(
    header_left,
    text=APP_NAME,
    font=('Segoe UI', 20, 'bold')
).pack(
    anchor='w'
)

# Application description.
ttk.Label(
    header_left,
    text='Windows network diagnosis, recovery and controlled repair',
    font=('Segoe UI', 10)
).pack(
    anchor='w'
)

# Display whether the application currently has Administrator
# privileges.
ttk.Label(
    header_left,
    text='Administrator: YES' if is_admin() else 'Administrator: NO'
).pack(
    anchor='w',
    pady=(7, 0)
)


# ================================================================
# ETHERNET STATUS BADGE
# ================================================================
# This badge is positioned in the top-right corner.
#
# It will later be updated automatically by
# update_ethernet_indicator().
# ================================================================

ethernet_badge = tk.Label(
    header,

    # Initial state before the first network check completes.
    text='  🖧  CHECKING...  ',

    # Font used by the status badge.
    font=('Segoe UI', 10, 'bold'),

    # Horizontal padding.
    padx=10,

    # Vertical padding.
    pady=7,

    # Flat visual style.
    relief='flat'
)

# Place the badge on the right side of the header.
ethernet_badge.pack(
    side='right',
    anchor='ne',
    padx=(10, 0)
)


# ================================================================
# MAIN BUTTON BAR
# ================================================================

bar = ttk.Frame(
    root,
    padding=(15, 0, 15, 10)
)

bar.pack(
    fill='x'
)


# Each tuple contains:
#
#   1. Button text
#   2. Function executed when the button is clicked
buttons = [
    ('RUN DIAGNOSIS', run_diagnosis),
    ('REPAIR NETWORK', repair),
    ('TRYFIX', tryfix_window),
    ('FORCE CONNECT', force_connect),
    ('UPDATE DRIVER', update_driver),
    ('OPEN CONFIG', open_config),
]

# Create every button in the button list.
for label, command in buttons:

    ttk.Button(
        bar,
        text=label,
        command=command
    ).pack(
        side='left',
        padx=4
    )


# ================================================================
# MAIN OUTPUT AREA
# ================================================================

# Main container for output text and scrollbar.
frame = ttk.Frame(
    root,
    padding=(15, 0, 15, 15)
)

frame.pack(
    fill='both',
    expand=True
)


# Text area used to display:
#   - diagnosis reports
#   - repair results
#   - driver update information
#   - Force Connect results
#   - system messages
output = tk.Text(
    frame,
    wrap='word',
    font=('Consolas', 10),
    padx=12,
    pady=12
)


# Vertical scrollbar connected to the output text area.
scroll = ttk.Scrollbar(
    frame,
    orient='vertical',
    command=output.yview
)

# Tell the Text widget to update the scrollbar position.
output.configure(
    yscrollcommand=scroll.set
)


# Place the text area.
output.pack(
    side='left',
    fill='both',
    expand=True
)

# Place the scrollbar.
scroll.pack(
    side='right',
    fill='y'
)


# ================================================================
# INITIAL APPLICATION MESSAGE
# ================================================================
# This message appears immediately when the program starts.
# It explains the recommended order of using the application.
# ================================================================

output.insert(
    tk.END,
    f'''Hospital Network Doctor v{VERSION}\n\n'
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
 
 
# ================================================================
# START ETHERNET STATUS MONITOR
# ================================================================
# Wait 100 milliseconds after the GUI starts before performing
# the first Ethernet status check.
#
# After the first check, set_ethernet_indicator() schedules
# another check every five seconds.
# ================================================================

root.after(
    100,
    update_ethernet_indicator
)


# ================================================================
# START THE APPLICATION
# ================================================================
# root.mainloop() starts Tkinter's event loop.
#
# From this point:
#   - Buttons respond to clicks
#   - Windows remain open
#   - Background workers can report results
#   - Ethernet monitoring continues
#
# The program stays here until the user closes the window.
# ================================================================

root.mainloop()