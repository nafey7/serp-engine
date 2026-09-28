"""The conditions a test ran under, saved next to its results so the numbers can be read fairly.

Where the machine is and whose network it is on, how far Google is (round trip, time to open
a secure connection), how fast the line downloads, and the machine and software versions.
Every probe is best effort: a failed one is recorded as missing, never fatal.
Only Google's empty test address (generate_204) is contacted, never a search.
"""

import json
import os
import platform
import shutil
import statistics
import subprocess
import time
from importlib.metadata import PackageNotFoundError, version

from .proxies import ProxyPool

CURL_TIMES = "%{time_namelookup} %{time_connect} %{time_appconnect} %{time_starttransfer} %{remote_ip}"


def collect(cfg, chrome_version: str = "") -> dict:
    return {
        "measured_at": time.strftime("%Y-%m-%d %H:%M:%S %Z (UTC%z)"),
        "location": _location(),
        "proxies": [ProxyPool.label(p) for p in cfg.proxies] or ["none (direct connection)"],
        "google_settings": {"hl": cfg.hl, "gl": cfg.gl},
        "network_to_google": _google_timings(),
        "download_speed": _download_speed(),
        "machine": _machine(),
        "software": {
            "python": platform.python_version(),
            "chrome": chrome_version or "not started",
            **{pkg: _version(pkg) for pkg in ("curl_cffi", "patchright", "beautifulsoup4", "lxml")},
        },
        "browser_settings": {
            "channel": cfg.browser_channel, "headless": cfg.headless, "images_blocked": cfg.block_images,
        },
    }


def to_markdown(env: dict) -> str:
    loc, net, dl, m = env["location"], env["network_to_google"], env["download_speed"], env["machine"]
    lines = [
        f"- Measured: {env['measured_at']}",
        f"- Location: {loc.get('city', '?')}, {loc.get('region', '?')}, {loc.get('country', '?')} "
        f"(network: {loc.get('org', '?')}, IP {loc.get('ip_masked', '?')})",
        f"- Proxies: {', '.join(env['proxies'])}",
        f"- Google: hl={env['google_settings']['hl']}, gl={env['google_settings']['gl']}",
    ]
    if net.get("samples"):
        lines.append(
            f"- Network to Google ({net['samples']} probes of generate_204, median): round trip "
            f"{net['tcp_connect_ms']} ms, new secure connection {net['tls_ready_ms']} ms, "
            f"reply {net['first_byte_ms']} ms; served by {', '.join(net['google_ips'])}"
        )
    if dl.get("mbps"):
        lines.append(f"- Download speed: {dl['mbps']} Mbit/s ({dl['bytes'] // 1_000_000} MB from {dl['source']})")
    lines.append(f"- Machine: {m['os']}, {m['cpu']}, {m['cpus']} CPUs, {m['ram_gb']} GB RAM")
    sw = env["software"]
    lines.append(f"- Software: Python {sw['python']}, Chrome {sw['chrome']}, patchright {sw['patchright']}, "
                 f"curl_cffi {sw['curl_cffi']}")
    b = env["browser_settings"]
    lines.append(f"- Browser: {b['channel']}, headless={b['headless']}, images blocked={b['images_blocked']}")
    return "\n".join(lines)


def _location() -> dict:
    try:
        out = subprocess.run(["curl", "-s", "-m", "8", "https://ipinfo.io/json"], capture_output=True, text=True).stdout
        d = json.loads(out)
    except Exception:
        return {}
    ip = d.get("ip", "")
    # Enough to show the network, not enough to identify the line.
    masked = ".".join(ip.split(".")[:2] + ["x", "x"]) if ip.count(".") == 3 else "hidden"
    return {k: d.get(k, "") for k in ("city", "region", "country", "org", "timezone")} | {"ip_masked": masked}


def _google_timings(samples: int = 5) -> dict:
    if not shutil.which("curl"):
        return {}
    rows = []
    for _ in range(samples):
        out = subprocess.run(
            ["curl", "-s", "-o", "/dev/null", "-m", "10", "-w", CURL_TIMES, "https://www.google.com/generate_204"],
            capture_output=True, text=True,
        ).stdout.split()
        if len(out) == 5:
            rows.append(out)
    if not rows:
        return {}
    med = lambda i, base=0: int(statistics.median(float(r[i]) - (float(r[base]) if base else 0) for r in rows) * 1000)
    return {
        "samples": len(rows),
        "dns_ms": med(0),
        "tcp_connect_ms": med(1, 0),        # one network round trip
        "tls_ready_ms": med(2, 0),          # connect + secure handshake, after DNS
        "first_byte_ms": med(3, 0),         # whole exchange, after DNS
        "google_ips": sorted({r[4] for r in rows}),
    }


def _download_speed(size: int = 10_000_000) -> dict:
    url = f"https://speed.cloudflare.com/__down?bytes={size}"
    speeds = []
    for _ in range(2):
        out = subprocess.run(["curl", "-s", "-o", "/dev/null", "-m", "30", "-w", "%{speed_download}", url],
                             capture_output=True, text=True).stdout
        try:
            speeds.append(float(out))
        except ValueError:
            pass
    return {"source": "speed.cloudflare.com", "bytes": size, "mbps": round(max(speeds) * 8 / 1e6, 1)} if speeds else {}


def _machine() -> dict:
    ram = 0
    try:
        if platform.system() == "Darwin":
            ram = int(subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True).stdout)
        else:
            ram = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
    except Exception:
        pass
    cpu = platform.processor() or platform.machine()
    if platform.system() == "Darwin":
        cpu = subprocess.run(["sysctl", "-n", "machdep.cpu.brand_string"], capture_output=True, text=True).stdout.strip() or cpu
    return {"os": f"{platform.system()} {platform.release()}", "cpu": cpu, "cpus": os.cpu_count(),
            "ram_gb": round(ram / 2**30) if ram else "?"}


def _version(pkg: str) -> str:
    try:
        return version(pkg)
    except PackageNotFoundError:
        return "?"
