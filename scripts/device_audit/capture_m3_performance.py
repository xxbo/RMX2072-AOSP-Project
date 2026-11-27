"""Read rendering, clock and frame evidence from one authenticated GSI boot.

Does not change governors, frequencies, display modes, services or settings.
Permission errors are saved as evidence, not interpreted as absent hardware.
"""
import argparse
import json
from pathlib import Path
import shlex
import subprocess
import time
import re


def latency_layer_name(line):
    # Android 17 --list wraps the real name/id in RequestedLayerState. Passing
    # the wrapper back to --latency returns only the period, with no samples.
    match = re.fullmatch(r'RequestedLayerState\{(.+?#\d+)(?:\s+.*)?\}', line)
    return match[1] if match else line


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--record', type=Path, required=True)
    p.add_argument('--phase', choices=('baseline', 'interaction', 'idle'), required=True)
    p.add_argument('--seconds', type=int, default=30)
    a = p.parse_args()
    if not 1 <= a.seconds <= 120:
        p.error('Capture between 1 and 120 seconds')
    live = a.record.resolve() / 'live'
    boot = json.loads((live / 'gsi-accepted.json').read_text())['identity'][2]
    out = live / ('performance-' + a.phase)
    out.mkdir(exist_ok=False)

    def shell(command, timeout=20):
        started = time.monotonic()
        r = subprocess.run(['adb', '-s', 'RMX2072-M1', 'shell', command],
                           capture_output=True, timeout=timeout)
        return dict(command=command, returncode=r.returncode,
                    seconds=round(time.monotonic() - started, 3),
                    stdout=r.stdout.decode(errors='replace').replace('\r', ''),
                    stderr=r.stderr.decode(errors='replace').replace('\r', ''))

    def identity():
        r = shell('cat /proc/sys/kernel/random/boot_id', 5)
        if r['returncode'] or r['stdout'].strip() != boot:
            raise ValueError('Expected accepted GSI boot is no longer connected')

    identity()
    (out / 'identity.json').write_text(json.dumps(dict(boot_id=boot,
        phase=a.phase, started_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())), indent=2)+'\n')
    clock_command = '''cat /proc/uptime
for p in /sys/devices/system/cpu/cpufreq/policy* /sys/class/devfreq/* /sys/class/thermal/thermal_zone*; do
 [ -d "$p" ] || continue
 echo "PATH=$p"
 for f in scaling_driver scaling_governor scaling_cur_freq scaling_min_freq scaling_max_freq governor cur_freq min_freq max_freq type temp; do
  [ ! -e "$p/$f" ] || { echo "FIELD=$f"; cat "$p/$f"; }
 done
done'''
    with (out / 'samples.jsonl').open('w', encoding='utf-8') as f:
        end = time.monotonic() + a.seconds
        while time.monotonic() < end:
            identity()
            f.write(json.dumps(shell(clock_command), ensure_ascii=False)+'\n')
            f.flush()
            time.sleep(1)
    commands = {
        'layer-list': 'timeout 12 dumpsys SurfaceFlinger --list',
        'display-period': 'timeout 12 dumpsys SurfaceFlinger --latency',
        'graphics': 'getprop ro.hardware.vulkan; getprop ro.hardware.egl; ls -lZ /dev/dri; timeout 12 dumpsys SurfaceFlinger',
        'display': 'timeout 12 dumpsys display',
        'launcher-frames': 'timeout 12 dumpsys gfxinfo com.android.launcher3 framestats',
        'settings-frames': 'timeout 12 dumpsys gfxinfo com.android.settings framestats',
        'startup-display': 'cat /data/local/tmp/rmx-m3-display.txt',
        'logcat': 'logcat -b all -d',
    }
    for name, command in commands.items():
        result = shell(command)
        (out / (name+'.json')).write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
        if name == 'layer-list':
            layers = [latency_layer_name(n) for n in result['stdout'].splitlines() if any(package in n
                      for package in ('com.android.launcher3', 'com.android.settings'))]
            for index, layer in enumerate(layers[:8]):
                latency = shell('timeout 12 dumpsys SurfaceFlinger --latency '+shlex.quote(layer))
                latency['layer'] = layer
                (out / f'layer-present-{index}.json').write_text(
                    json.dumps(latency, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    identity()
    print(json.dumps(dict(boot_id=boot, phase=a.phase, output=str(out), same_boot=True)))


if __name__ == '__main__':
    main()
