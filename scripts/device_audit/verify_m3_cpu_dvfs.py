"""Bounded per-policy load/idle capture; never writes frequency or thermal controls."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--adb', default='adb')
    p.add_argument('--probe', required=True, type=Path)
    p.add_argument('--record', required=True, type=Path)
    p.add_argument('--output', required=True, type=Path)
    a = p.parse_args()
    boot = json.loads((a.record / 'live/gsi-stable.json').read_text())['identity'][2]
    a.output.mkdir(parents=True, exist_ok=False)
    base = [a.adb, '-s', 'RMX2072-M1']
    remote = '/data/local/tmp/rmx-cpu-policy-load'
    samples, loads = [], []
    process = None

    def shell(command, timeout=15):
        r = subprocess.run(base + ['shell', command], capture_output=True, timeout=timeout)
        text = r.stdout.decode('utf-8', 'replace').replace('\r', '')
        errors = r.stderr.decode('utf-8', 'replace')
        if r.returncode or re.search(r'Permission denied|Operation not permitted', text + errors):
            raise RuntimeError(text + errors)
        return text

    def identity():
        if shell('cat /proc/sys/kernel/random/boot_id; getenforce; '
                 'getprop vendor.rmx.m1.state; getprop sys.boot_completed').splitlines() != [boot, 'Enforcing', 'retained', '1']:
            raise RuntimeError('Expected retained boot is no longer available')

    def controls():
        return shell('for p in /sys/devices/system/cpu/cpufreq/policy*; do '
                     'echo "$p"; for f in affected_cpus scaling_driver scaling_governor '
                     'scaling_min_freq scaling_max_freq scaling_available_frequencies; do '
                     'echo "$f"; cat "$p/$f" || exit 1; done; done')

    def sample(phase):
        text = shell('for n in 0 4 7; do printf "CPU %s " "$n"; '
                     'cat /sys/devices/system/cpu/cpufreq/policy$n/scaling_cur_freq || exit 1; done; '
                     'for p in /sys/class/thermal/thermal_zone*; do '
                     'printf "TEMP %s " "$(cat "$p/type")"; cat "$p/temp" || exit 1; done')
        hz = {int(n): int(khz) * 1000 for n, khz in re.findall(r'^CPU (\d+) (\d+)$', text, re.M)}
        temps = {name: int(v) for name, v in re.findall(r'^TEMP (\S+) (-?\d+)$', text, re.M)}
        if set(hz) != {0, 4, 7} or not all(n in temps for n in
                ('m3-little-thermal', 'm3-big-thermal', 'm3-gpu-thermal')):
            raise RuntimeError('Incomplete CPU/TSENS sample: ' + text)
        row = dict(monotonic=time.monotonic(), phase=phase, hz=hz, temperatures_mC=temps)
        samples.append(row)
        measured = [temps[n] for n in ('m3-little-thermal', 'm3-big-thermal', 'm3-gpu-thermal')]
        if min(measured) < -10000 or max(measured) >= 65000:
            raise RuntimeError('Temperature outside the bounded probe window')

    def capture(phase, seconds):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            sample(phase)
            time.sleep(.2)

    try:
        identity()
        before = controls()
        (a.output / 'controls-before.txt').write_text(before, encoding='utf-8')
        battery = shell('dumpsys battery')
        (a.output / 'battery-before.txt').write_text(battery, encoding='utf-8')
        temperature = re.search(r'^\s*temperature: (\d+)\s*$', battery, re.M)
        if not temperature or int(temperature[1]) >= 400:
            raise RuntimeError('Battery temperature unavailable or too warm for this probe')
        sample('preflight')
        subprocess.run(base + ['push', str(a.probe), remote], check=True, capture_output=True)
        shell('chmod 700 ' + remote)
        capture('baseline', 3)
        for cpu in (0, 4, 7):
            identity()
            process = subprocess.Popen(base + ['shell', f'timeout 8 {remote} {cpu} 4'],
                                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            capture('load-' + str(cpu), 4)
            raw, _ = process.communicate(timeout=6)
            text = raw.decode('utf-8', 'replace').replace('\r', '')
            (a.output / f'load-{cpu}.txt').write_text(text, encoding='utf-8')
            if process.returncode:
                raise RuntimeError('CPU workload failed: ' + text)
            result = json.loads(text)
            if not result['affinity_verified'] or result['last_cpu'] != cpu or result['iterations'] <= 0:
                raise RuntimeError('CPU affinity/work not confirmed')
            loads.append(result)
            capture('recovery-' + str(cpu), 5)
        identity()
        after = controls()
        (a.output / 'controls-after.txt').write_text(after, encoding='utf-8')
        if after != before:
            raise RuntimeError('CPU governor/bounds/topology changed during capture')
        result = dict(boot_id=boot, same_boot=True, controls_unchanged=True,
                      probe_sha256=hashlib.sha256(a.probe.read_bytes()).hexdigest(), loads=loads,
                      phases={phase: {str(cpu): sorted({s['hz'][cpu] for s in samples if s['phase'] == phase})
                              for cpu in (0, 4, 7)} for phase in dict.fromkeys(s['phase'] for s in samples)},
                      scope='Driver-reported CPU frequency under a short pinned integer load; not scheduler placement, sustained performance or thermal throttling acceptance')
        (a.output / 'result.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(result))
    finally:
        (a.output / 'samples.json').write_text(json.dumps(samples, indent=2) + '\n', encoding='utf-8')
        if process is not None and process.poll() is None:
            process.terminate()
            process.wait(timeout=5)
        # alarm() and Android timeout bound the remote workload if ADB is lost.
        try:
            shell('rm -f ' + remote)
        except (RuntimeError, subprocess.TimeoutExpired):
            pass


if __name__ == '__main__':
    main()
