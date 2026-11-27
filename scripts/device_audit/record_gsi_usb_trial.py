"""Normalize guarded USB trial evidence after retention or verified F.20 recovery."""
import argparse,hashlib,json
from pathlib import Path

def load(path):return json.loads(path.read_text(encoding='utf-8-sig'))
def rows(path):return [json.loads(x) for x in path.read_text(encoding='utf-8-sig').splitlines()] if path.exists() else []
def requires_stock_readback(disposition):
    # Historical receipts required full reads. Only the explicit new policy
    # may omit them; expected image hashes are never fresh device evidence.
    if disposition.get('stock_full_partition_readback', True):
        return True
    assert disposition['verification_policy']=='reuse-original-backup-write-ack-boot-and-lp-metadata'
    assert disposition['stock_write_acknowledged'] is True
    assert all(disposition[name+'_sha256'] is None for name in ('boot','dtbo','super'))
    expected=disposition['expected_image_sha256']
    assert set(expected)=={'boot','dtbo','super'}
    assert all(isinstance(h,str) and len(h)==64 and all(c in '0123456789abcdef' for c in h) for h in expected.values())
    return False

def record(directory):
    live=directory/'live';inputs=load(directory/'inputs.json');events=rows(live/'host-events.jsonl')
    original=next(e['boot_id'] for e in events if e['event'] in ('handoff_requested','autonomous_handoff_observed'))
    text=(live/('boot-events.txt' if (live/'boot-events.txt').exists() else 'acm.log')).read_text(errors='replace')
    serial=[l for l in text.splitlines() if l.startswith('M1EVENT ')]
    adb=rows(live/'adb.jsonl');physical=rows(directory/'usb.jsonl')
    terminal=directory/'gsi-retained.json'
    if terminal.exists():
        disposition=load(terminal);assert disposition['current_mode']=='Android 17 GSI'
        assert disposition['stable']['identity'][2]==original and disposition['stable']['guardian']=='retained'
    else:
        disposition=load(directory/'restored.json');assert disposition['sys_boot_completed']==1 and disposition['lp_slots']==[0,1]
        assert disposition['boot_id']!=original
    readbacks=rows(directory/'readbacks.jsonl')
    for prefix in ['candidate-super-read']+(['restored-super'] if not terminal.exists() and requires_stock_readback(disposition) else []):
        blocks=[r for r in readbacks if r['label'].startswith(prefix+'-')]
        assert len(blocks)==17 and sum(r['sectors']*4096 for r in blocks)==8866758656
    assert not (directory/'readback.bin').exists()
    return dict(id=inputs['trial'],boot_id=original,inputs=inputs,events=events,serial_events=serial,
                adb=dict(samples=len(adb),states=sorted({line for r in adb for line in r.get('transports',[])}),accept_errors=[r['accept_error'] for r in adb if 'accept_error' in r]),
                physical_usb=dict(samples=len(physical),device_ids=sorted({d['id'] for r in physical for d in r['devices']})),
                disposition=disposition,independent_edl_readbacks=readbacks,
                raw_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in live.iterdir() if p.is_file()},
                console_notes=[l for l in (live/'console-ramoops-0').read_text(errors='replace').splitlines() if any(x in l for x in ('RMX-M1-GUARD','rmx-m1','adbd','functionfs','usb_gadget','watchdog','avc:'))] if (live/'console-ramoops-0').exists() else [])

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--trial-dir',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    a.output.write_text(json.dumps(record(a.trial_dir),indent=2)+'\n',encoding='utf-8')
