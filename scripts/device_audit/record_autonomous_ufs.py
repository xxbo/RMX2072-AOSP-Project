"""Publish a compact autonomous UFS trial from saved handset evidence."""
import argparse
import hashlib
import json
from pathlib import Path
import re


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--workspace',type=Path,required=True)
    p.add_argument('--trial',required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--restore-suffix',default='expiry-restore')
    a=p.parse_args()
    assert re.fullmatch(r'ufs-host-g3-gsi17-firststage-ufs-\d{2}',a.trial)
    assert re.fullmatch(r'[a-z0-9-]+',a.restore_suffix)
    root=a.workspace/'records'; trial=root/a.trial; live=trial/'live'
    fault=root/(a.trial+'-expiry'); restore=root/(a.trial+'-'+a.restore_suffix)
    load=lambda path:json.loads(path.read_text(encoding='utf-8'))
    stable=load(live/'gsi-stable.json'); boot=stable['identity'][2]
    events=(live/'boot-events.txt').read_text(encoding='utf-8')
    assert set(re.findall(r'^M1EVENT boot_id=(.*)$',events,re.M))=={boot}
    record=dict(trial=a.trial,inputs=load(trial/'inputs.json'),boot_id=boot,
                identity=stable['identity'],pid1=stable['pid1'],ufs_evidence=stable['ufs_evidence'],
                ufs_events=[line for line in events.splitlines() if re.match(r'M1EVENT (autonomous|previous_guard|ufs_super|linear_mapper|verified_ufs_mount|table=|status=|boot_usb_state|clock_source)',line)],
                soak_seconds=stable['seconds'],soak=stable['soak'],
                guard_mode=stable['guard_mode_during_soak'],adb_smoke=load(live/'adb-smoke.json'),
                local_readiness=load(live/'local-readiness.json'),
                independent_readbacks=[json.loads(x) for x in (trial/'readbacks.jsonl').read_text().splitlines()],
                disconnected_cold_start='NOT RUN on this artifact',current_mode='GSI after warm-boot acceptance')
    if (fault/'fault.json').exists():
        record['fault']=load(fault/'fault.json')
        record['fault_transports']=[json.loads(x) for x in (fault/'transport.jsonl').read_text().splitlines()]
        for name in ('result','failure','intermediate-boot','edl-window-failure','host-tools'):
            if (fault/(name+'.json')).exists():record['fault_'+name]=load(fault/(name+'.json'))
        for name in ('console-ramoops-0','pmsg-ramoops-0'):
            if (fault/name).exists():
                record[name+'_selected']=[s for s in (fault/name).read_text(errors='replace').splitlines() if 'RMX-M1-' in s or 'watchdog0: pretimeout event' in s]
        if (fault/'recovery-providers.txt').exists():record['recovery_providers']=(fault/'recovery-providers.txt').read_text(errors='replace')
        if (fault/'recovery-watchdog.log').exists():record['recovery_watchdog']=(fault/'recovery-watchdog.log').read_text(errors='replace')
        record['current_mode']='See fault/restore records; warm retention is historical'
    if (trial/'boot-only-source.json').exists():
        source=load(trial/'boot-only-source.json')
        record['boot_only_update']={key:source[key] for key in ('previous_record','previous_boot_sha256')}
    if (restore/'restored.json').exists():
        record['restored']=load(restore/'restored.json')
        record['restore_readbacks']=[json.loads(x) for x in (restore/'readbacks.jsonl').read_text().splitlines()]
        record['current_mode']='F.20 restored and verified'
    record['raw_sha256']={str(path.relative_to(root)).replace('\\','/'):hashlib.sha256(path.read_bytes()).hexdigest()
                         for directory in (trial,live,fault,restore) if directory.exists()
                         for path in directory.iterdir() if path.is_file() and path.stat().st_size<10000000}
    a.output.write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
    print(record['current_mode'])


if __name__=='__main__':main()
