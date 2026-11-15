"""Read-only capture at the first new authenticated GSI ADB connection."""
from pathlib import Path
import argparse, json, re, subprocess, time

p = argparse.ArgumentParser()
p.add_argument('--workspace', type=Path, required=True)
p.add_argument('--trial', required=True)
p.add_argument('--previous-boot', required=True)
a = p.parse_args()
if not re.fullmatch(r'ufs-host-g3-gsi17-firststage-ufs-\d{2}', a.trial):
    p.error('Unexpected trial name')
work = a.workspace.resolve()
record = work/'records'/a.trial/'live'
def shell(command, timeout=10):
    return subprocess.check_output(['adb', '-s', 'RMX2072-M1', 'shell', command], timeout=timeout, stderr=subprocess.STDOUT).decode(errors='replace').replace('\r', '')
end = time.monotonic() + 1500
while time.monotonic() < end:
    try:
        boot = shell('cat /proc/sys/kernel/random/boot_id', 3).strip()
        if boot and boot != a.previous_boot and record.is_dir():
            events = shell('cat /data/local/tmp/rmx-m1-boot.txt', 3)
            # The witness records the boot UUID, not the trial name. Match it
            # to this runner's independently captured diagnostic handoff.
            host_events = record/'host-events.jsonl'
            if ('M1EVENT boot_id='+boot in events and host_events.exists()
                    and boot in host_events.read_text()):
                break
    except (OSError, subprocess.SubprocessError):
        pass
    time.sleep(2)
else:
    raise TimeoutError('No new matching authenticated GSI ADB')
commands = {
    'identity': 'cat /proc/sys/kernel/random/boot_id; uname -r; getenforce; getprop vendor.rmx.m1.state; getprop sys.boot_completed',
    'drm-labels': 'ls -ldZ /dev/dri; ls -lZ /dev/dri; ps -AZ | grep -E "surfaceflinger|composer|allocator|zygote|system_server|keymaster"',
    'services': 'service check android.security.maintenance; service check SurfaceFlinger; service check android.hardware.graphics.composer3.IComposer/default; service check android.hardware.graphics.allocator.IAllocator/default; service check activity; service check window',
    'display': 'cat /data/local/tmp/rmx-m3-display.txt',
    'logcat': 'logcat -b all -d',
}
print('FIRST_NEW_ADB '+boot, flush=True)
for iteration in range(4):
    for name,command in commands.items():
        if iteration and name in ('display', 'drm-labels'):
            continue
        try:
            result = shell(command, 25)
        except (OSError, subprocess.SubprocessError) as error:
            result = str(error)
        (record/f'graphics-first-{iteration}-{name}.txt').write_text(result, encoding='utf-8')
        if name in ('identity', 'services'):
            print(str(iteration)+' '+name+' '+result, flush=True)
    if iteration < 3:
        time.sleep(15)
print('CAPTURE_COMPLETE', flush=True)
