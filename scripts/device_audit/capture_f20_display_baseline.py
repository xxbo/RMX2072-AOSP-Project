"""Read the live F.20 display/debug interfaces before selecting register ranges."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import time


def shell(command, timeout=20):
    return subprocess.check_output(['adb', '-s', '3c8304a6', 'exec-out',
        'su -c ' + shlex.quote(command)], timeout=timeout,
        stderr=subprocess.STDOUT).decode('utf-8', errors='replace').replace('\r', '')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--wait-seconds', type=int, default=600)
    a = p.parse_args()
    a.output.mkdir(parents=True, exist_ok=False)
    deadline = time.monotonic() + a.wait_seconds
    while time.monotonic() < deadline:
        try:
            identity = shell('getprop ro.build.display.id; getprop sys.boot_completed; uname -r; cat /proc/sys/kernel/random/boot_id; id', 5).splitlines()
            if identity[:3] == ['RMX2072_11_F.20', '1', '4.19.157-perf+'] and len(identity) == 5 and identity[4].startswith('uid=0('):
                break
        except (OSError, subprocess.SubprocessError):
            pass
        time.sleep(2)
    else:
        raise TimeoutError('Matching completed F.20 root ADB did not appear')
    print('F20_DISPLAY_BASELINE_READY ' + identity[3], flush=True)
    queries = {
        'debug-mounts': 'grep debugfs /proc/mounts; ls -ld /sys/kernel/debug /d',
        'debug-inventory': 'find /sys/kernel/debug/dri -maxdepth 4 -type f; ls /sys/kernel/debug | grep -Ei "dsi|mdss|display|sde"',
        'clock-inventory': 'ls /sys/kernel/debug/clk',
        'drm-sysfs': 'for p in /sys/class/drm/card*-DSI-*; do echo PATH=$p; for f in status enabled modes; do echo FIELD=$f; cat "$p/$f"; done; done',
        'display-services': 'dumpsys SurfaceFlinger --displays; dumpsys display',
        'refresh-settings': 'for k in peak_refresh_rate min_refresh_rate screen_refresh_rate user_refresh_rate; do echo KEY=$k; settings get system "$k"; done',
        'display-log': 'dmesg | grep -Ei "dsi_display_set_mode|dsi_panel_parse|RM19795|DSC|PLL.*lock|DSI.*error" | tail -150',
        'display-clock-rates': 'for n in disp_cc_mdss_mdp_clk_src disp_cc_mdss_mdp_clk disp_cc_mdss_byte0_clk disp_cc_mdss_pclk0_clk disp_cc_mdss_esc0_clk disp_cc_mdss_vsync_clk dsi0vco_clk dsi0_pll_out_div_clk dsi0_pll_bit_clk dsi0_phy_pll_out_byteclk dsi0_phy_pll_out_dsiclk; do echo CLOCK=$n; for f in clk_rate clk_parent clk_prepare_count clk_enable_count; do echo FIELD=$f; cat /sys/kernel/debug/clk/$n/$f; done; done',
    }
    results = {}
    for name, command in queries.items():
        try:
            value = shell(command, 30)
            status = 0
        except subprocess.CalledProcessError as error:
            value = error.output.decode('utf-8', errors='replace') if isinstance(error.output, bytes) else error.output
            status = error.returncode
        except subprocess.TimeoutExpired:
            value, status = 'Timed out; not a complete capture\n', 'TIMEOUT'
        data = value.encode('utf-8')
        (a.output / (name + '.txt')).write_bytes(data)
        results[name] = dict(bytes=len(data), sha256=hashlib.sha256(data).hexdigest(), exit_status=status)
        print(name, len(data), status, flush=True)
    if shell('cat /proc/sys/kernel/random/boot_id').strip() != identity[3]:
        raise ValueError('Stock boot changed during collection')
    (a.output / 'baseline.json').write_text(json.dumps(dict(
        utc=datetime.now(timezone.utc).isoformat(), identity=identity, results=results,
        scope='Read-only live F.20 inventory and display/clock state; no register writes or refresh changes. Local raw service dumps are not for public upload.'), indent=2) + '\n', encoding='utf-8')
    print('F20_DISPLAY_INVENTORY_COMPLETE', flush=True)


if __name__ == '__main__':
    main()
