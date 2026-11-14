"""Accept a guarded GSI boot only through an authenticated, matching ADB shell."""
import json
from pathlib import Path
import subprocess
import time

RELEASE = '6.18.32-android17-5-maybe-dirty-4k'
SERIAL = 'RMX2072-M1'

def shell(command, timeout=8):
    return subprocess.check_output(['adb','-s',SERIAL,'shell',command], text=True, timeout=timeout, stderr=subprocess.STDOUT).replace('\r','')

def inspect(output, original):
    identity = shell('getprop ro.build.version.sdk; uname -r; cat /proc/sys/kernel/random/boot_id; getenforce; getprop init.svc.adbd; getprop init.svc.vendor.rmx-m1-guard; getprop vendor.rmx.m1.state; getprop sys.usb.state').splitlines()
    if identity[:6] != ['37',RELEASE,original,'Enforcing','running','running'] or len(identity)!=8 or identity[6] not in ('armed','lease','retained') or identity[7]!='adb':
        raise ValueError('GSI identity/guardian/USB state not ready: '+repr(identity))
    init = shell('cat /proc/1/cmdline').strip('\x00\n')
    if '/system/bin/init' not in init or 'second_stage' not in init:
        raise ValueError('Android PID 1 identity not readable: '+repr(init))
    mounts = shell('cat /proc/mounts')
    if not any(' /vendor ext4 ro,' in l for l in mounts.splitlines()):
        raise ValueError('Verified read-only vendor mount absent')
    if not any(' / ext4 ro,' in l or ' /system ext4 ro,' in l for l in mounts.splitlines()):
        raise ValueError('Read-only GSI mount absent')
    backing = shell('readlink -f /sys/class/block/sda10; ls -l /sys/class/block/dm-*/slaves')
    if '/1d84000.ufs/' not in backing or 'sda10' not in backing:
        raise ValueError('UFS super backing not visible')
    return dict(identity=identity,pid1=init,mounts=mounts,backing=backing)

def accept(output, original):
    proof = inspect(output, original)
    reply = shell('/vendor/bin/hw/rmx-m1-control --keep '+original).strip()
    if reply != 'lease': raise ValueError('Guardian rejected same-boot control: '+reply)
    for _ in range(5):
        if shell('getprop vendor.rmx.m1.state').strip() == 'lease':break
        time.sleep(1)
    else:raise ValueError('Guardian did not accept matching boot ACK')
    proof['acknowledged_monotonic'] = time.monotonic()
    (output/'gsi-accepted.json').write_text(json.dumps(proof,indent=2)+'\n')
    return proof

def collect(output):
    for name,cmd in [('logcat.txt','logcat -b all -d'),('properties.txt','getprop'),('processes.txt','ps -A -o USER,PID,PPID,NAME,ARGS'),('watchdog.txt','cat /sys/class/watchdog/watchdog0/state /sys/class/watchdog/watchdog0/timeout; cat /proc/uptime')]:
        try:(output/name).write_text(shell(cmd,30),encoding='utf-8')
        except (OSError,subprocess.SubprocessError) as error:(output/(name+'.error')).write_text(str(error))


def soak_and_retain(output):
    proof = json.loads((output/'gsi-accepted.json').read_text())
    original = proof['identity'][2]
    start = time.monotonic()
    rows=[]
    try:
        while time.monotonic()-start < 190:
            current = inspect(output, original)
            if shell('/vendor/bin/hw/rmx-m1-control --keep '+original).strip() != 'lease':
                raise ValueError('Watchdog lease renewal failed')
            rows.append(dict(elapsed=round(time.monotonic()-start,3),identity=current['identity']))
            time.sleep(10)
        final = inspect(output, original)
        if shell('/vendor/bin/hw/rmx-m1-control --retain '+original).strip() != 'retained':
            raise ValueError('Watchdog retention commit failed')
        if shell('getprop vendor.rmx.m1.state').strip() != 'retained':
            raise ValueError('Retained state not confirmed')
        final.update(soak=rows,seconds=round(time.monotonic()-start,3),guardian='retained')
        (output/'gsi-stable.json').write_text(json.dumps(final,indent=2)+'\n')
        collect(output)
        return final
    except (OSError,subprocess.SubprocessError,ValueError):
        try:shell('/vendor/bin/hw/rmx-m1-control --rollback '+original)
        except (OSError,subprocess.SubprocessError):pass
        raise
