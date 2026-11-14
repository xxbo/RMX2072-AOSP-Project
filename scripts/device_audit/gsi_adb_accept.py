"""Accept a guarded GSI boot only through an authenticated, matching ADB shell."""
import json
import re
from pathlib import Path
import subprocess
import time
from datetime import datetime, timezone

RELEASE = '6.18.32-android17-5-maybe-dirty-4k'
SERIAL = 'RMX2072-M1'

def shell(command, timeout=8):
    return subprocess.check_output(['adb','-s',SERIAL,'shell',command], text=True, timeout=timeout, stderr=subprocess.STDOUT).replace('\r','')

def fetch_autonomous(output):
    """Fetch pre-policy evidence; this observation never requests Android startup."""
    boot=shell('cat /proc/sys/kernel/random/boot_id').strip()
    from uuid import UUID
    UUID(boot)
    evidence=shell('cat /data/local/tmp/rmx-m1-boot.txt')
    if 'M1EVENT autonomous=1\n' not in evidence or set(re.findall(r'^M1EVENT boot_id=(.*)$',evidence,re.M))!={boot}:
        raise ValueError('Autonomous evidence absent or from another boot')
    (output/'boot-events.txt').write_text(evidence,encoding='utf-8')
    with (output/'host-events.jsonl').open('a') as log:
        log.write(json.dumps(dict(event='autonomous_handoff_observed',boot_id=boot,monotonic=time.monotonic(),utc=datetime.now(timezone.utc).isoformat()))+'\n')
    return boot

def verified_ufs_graph(mounts, backing):
    rows = [x.split() for x in mounts.splitlines()]
    roots = []
    for point in ('/', '/vendor'):
        row = next((x for x in rows if len(x)>=4 and x[1]==point and x[2]=='ext4' and x[3].split(',')[0]=='ro'),None)
        if not row or not re.fullmatch(r'/dev/block/dm-\d+',row[0]):
            raise ValueError('Unexpected verified mount source: '+point)
        roots.append(row[0].rsplit('/',1)[1])
    graph={};node=None
    for line in backing.splitlines():
        if line.startswith('NODE='):
            node=line[5:];graph[node]=[]
        elif line.startswith('SLAVE=') and node:graph[node].append(line[6:])
    def leaves(node, seen):
        if node in seen:raise ValueError('Device mapper cycle')
        if node=='sda10':return {node}
        if not re.fullmatch(r'dm-\d+',node) or not graph.get(node):raise ValueError('Incomplete UFS mapping')
        return set().union(*(leaves(child,seen|{node}) for child in graph[node]))
    if '/1d84000.ufs/' not in backing or any(leaves(x,set())!={'sda10'} for x in roots):
        raise ValueError('System/vendor do not both map to UFS super')
    return graph

def inspect(output, original):
    identity = shell('getprop ro.build.version.sdk; uname -r; cat /proc/sys/kernel/random/boot_id; getenforce; getprop init.svc.adbd; getprop init.svc.vendor.rmx-m1-guard; getprop vendor.rmx.m1.state; getprop sys.usb.state').splitlines()
    if identity[:5] != ['37',RELEASE,original,'Enforcing','running'] or len(identity)!=8 or identity[5] not in ('','running') or identity[6] not in ('armed','lease','retained') or identity[7]!='adb':
        raise ValueError('GSI identity/guardian/USB state not ready: '+repr(identity))
    init = shell('cat /proc/1/cmdline').strip('\x00\n')
    if '/system/bin/init' not in init or 'second_stage' not in init:
        raise ValueError('Android PID 1 identity not readable: '+repr(init))
    mounts = shell('cat /proc/mounts')
    if not any(' /vendor ext4 ro,' in l for l in mounts.splitlines()):
        raise ValueError('Verified read-only vendor mount absent')
    if not any(' / ext4 ro,' in l or ' /system ext4 ro,' in l for l in mounts.splitlines()):
        raise ValueError('Read-only GSI mount absent')
    backing = shell('readlink -f /sys/class/block/sda10; for n in /sys/class/block/dm-*; do echo NODE=${n##*/}; for s in $n/slaves/*; do [ ! -e "$s" ] || echo SLAVE=${s##*/}; done; done')
    try:
        graph = verified_ufs_graph(mounts,backing)
        evidence = 'live ADB sysfs graph'
    except ValueError:
        # A production GSI denies shell access to sysfs_dm. Use the independent
        # pre-policy witness only when it names this boot and these exact mounts.
        if 'SLAVE=' in backing or '/1d84000.ufs/' not in backing:
            raise ValueError('Unexpected or incomplete live UFS backing')
        transcript_path=output/('boot-events.txt' if (output/'boot-events.txt').is_file() else 'acm.log')
        if not (output/'host-events.jsonl').is_file() or not transcript_path.is_file():
            raise ValueError('Restricted sysfs requires independent same-boot UFS witness')
        events = [json.loads(x) for x in (output/'host-events.jsonl').read_text().splitlines()]
        if not any(x.get('event') in ('handoff_requested','autonomous_handoff_observed') and x.get('boot_id')==original for x in events):
            raise ValueError('UFS witness does not match current boot')
        transcript = transcript_path.read_text(errors='replace')
        if set(re.findall(r'^M1EVENT boot_id=(.*)$',transcript,re.M)) != {original} or not re.search(r'^M1EVENT ufs_super=.*/1d84000.ufs/.* dev=8:10 ro=1$',transcript,re.M):
            raise ValueError('UFS witness boot identity or physical device invalid')
        for partition,point in [('system','/'),('vendor','/vendor')]:
            dev = re.findall(r'M1EVENT verified_ufs_mount='+partition+r' dev=254:(\d+)',transcript)
            if len(set(dev))!=1 or not any(x.split()[:3]==['/dev/block/dm-'+dev[0],point,'ext4'] and x.split()[3].split(',')[0]=='ro' for x in mounts.splitlines() if len(x.split())>=4):
                raise ValueError('UFS witness mount does not match live ADB: '+partition)
            tables=re.findall(r'M1EVENT table='+partition+r' (.*)',transcript)
            if not tables or any(not re.fullmatch(r'\d+ \d+ linear 8:10 \d+',x) for x in tables):
                raise ValueError('UFS witness linear backing invalid: '+partition)
            if not re.search(r'M1EVENT status='+partition+r'-verity \d+ \d+ verity V ',transcript):
                raise ValueError('UFS witness verity validation absent: '+partition)
            lower = re.findall(r'Created logical partition '+partition+r' on device /dev/block/dm-(\d+)',transcript)
            lower += re.findall(r'^M1EVENT linear_mapper='+partition+r' dev=254:(\d+)$',transcript,re.M)
            if len(set(lower))!=1 or not re.search(r'M1EVENT table='+partition+r'-verity \d+ \d+ verity 1 254:'+lower[0]+r' 254:'+lower[0]+r' ',transcript):
                raise ValueError('UFS witness verity chain invalid: '+partition)
        graph = None
        evidence = 'same-boot '+('autonomous device' if transcript_path.name=='boot-events.txt' else 'ACM')+' witness plus matching live ADB mounts (sysfs_dm restricted)'
    return dict(identity=identity,pid1=init,mounts=mounts,backing=backing,ufs_graph=graph,ufs_evidence=evidence)

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
        from gsi_adb_smoke import run as transfer_smoke
        transfer_smoke(output, original)
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
