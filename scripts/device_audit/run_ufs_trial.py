"""Run a bounded RMX2072 UFS trial with one verified recovery set.

Workspace layout: recovery/f20, recovery/tools, recovery/OplusEdlTool/Tools,
serial-deps, current/{boot,kernel,candidate,volumes}, and records. All large
readback files are removed only after their expected digest matches. No
partition outside boot and super is programmed. Original userdata is untouched.
The guarded profile keeps GSI running only after authenticated identity checks,
a renewable watchdog lease and a 190-second ADB soak; failures recover to F.20.
"""
from pathlib import Path
from xml.etree import ElementTree as ET
from datetime import datetime, timezone
import argparse
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import time
from uuid import UUID


def validate_boot_only(previous, stable, candidate, scratch, live):
    """Require an unchanged container/volume seed and a retained same-boot GSI."""
    if previous['candidate'] != candidate or previous['scratch'] != scratch:
        raise ValueError('Boot-only update requires identical super and scratch inputs')
    boot = stable['identity'][2]
    UUID(boot)
    if (stable.get('guardian') != 'retained' or stable.get('seconds', 0) < 190 or
        stable['identity'][6] != 'retained' or live['identity'][2] != boot or
        live['identity'][6] != 'retained'):
        raise ValueError('Boot-only update requires the accepted retained boot')
    digest = previous['boot']['boot_sha256']
    if not re.fullmatch(r'[0-9a-f]{64}', digest):
        raise ValueError('Previous boot digest invalid')
    return digest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', type=Path, required=True)
    parser.add_argument('--trial', required=True)
    parser.add_argument('--restore-only', action='store_true')
    parser.add_argument('--recovery-gate', type=Path, help='Restore only: validate now, wait for this explicit JSON handoff before capturing EDL')
    parser.add_argument('--retain-gsi', action='store_true')
    parser.add_argument('--boot-only-from', type=Path, help='Previous retained trial record; read all super bytes, then program only boot')
    parser.add_argument('--record-suffix', default='', help='New evidence directory for repeating the exact current image')
    args = parser.parse_args()
    sys.path.insert(0, str(args.workspace.resolve()/'serial-deps'))
    from serial.tools.list_ports import comports
    from check_super_chunks import chunks, verify, stock_restore_xml
    w=args.workspace.resolve();p=w/'current';stock=w/'recovery/f20';tools=w/'recovery/OplusEdlTool/Tools';loader=w/'recovery/tools/devprg_865_1';audit=Path(__file__).resolve().parent
    trial=args.trial;assert re.fullmatch(r'ufs-host-g3-gsi17-firststage-ufs-\d{2}',trial)
    restore_only=args.restore_only
    assert not args.recovery_gate or restore_only
    assert not args.boot_only_from or (args.retain_gsi and not restore_only)
    assert not args.record_suffix or re.fullmatch(r'[a-z0-9-]{1,32}',args.record_suffix)
    dest=w/'records'/(trial+('-'+args.record_suffix if args.record_suffix else '')+('-restore' if restore_only else ''));dest.mkdir(parents=True,exist_ok=False)
    orig=json.loads((stock/'acquisition.json').read_text());candidate={} if restore_only else json.loads((p/'candidate/candidate.json').read_text());boot={} if restore_only else json.loads((p/'boot/control.json').read_text())
    port=None;configured=False
    def sha(path):
     with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
    def phone(cmd,timeout=180):
     return subprocess.check_output(['adb','-s','3c8304a6','exec-out','su -c '+shlex.quote(cmd)],timeout=timeout,stderr=subprocess.DEVNULL).decode().strip()
    def event(message):
     with (dest/'timeline.jsonl').open('a') as out:out.write(json.dumps(dict(utc=datetime.now(timezone.utc).isoformat(),event=message))+'\n')
     print(message,flush=True)
    def run(label,args,timeout=900):
     with (dest/(label+'.log')).open('xb') as out:subprocess.run([str(a) for a in args],stdout=out,stderr=subprocess.STDOUT,check=True,timeout=timeout,cwd=dest)
    def enter(label,initial=False,timeout=400):
     nonlocal port,configured
     if initial:subprocess.run(['adb','-s','RMX2072-M1' if args.boot_only_from else '3c8304a6','reboot','edl'],check=True,timeout=15)
     end=time.monotonic()+timeout
     while time.monotonic()<end:
      ports=[x.device for x in comports() if (x.vid,x.pid)==(0x05c6,0x9008)]
      if len(ports)==1:break
      if len(ports)>1:raise RuntimeError('Multiple EDL devices')
      time.sleep(.5)
     else:raise RuntimeError('EDL did not return')
     port=ports[0];configured=False
     run(label,[tools/'QSaharaServer.exe','-p','\\\\.\\'+port,'-s','13:'+str(loader)],60)
     assert 'Sahara protocol completed' in (dest/(label+'.log')).read_text(errors='replace')
     event(label+' Sahara ready')
    def fh(label,root,search=None):
     nonlocal configured
     xml=dest/(label+'.xml');xml.write_bytes(ET.tostring(root,encoding='utf-8',xml_declaration=True))
     cmd=[tools/'fh_loader.exe','--port=\\\\.\\'+port,'--memoryname=ufs','--mainoutputdir='+str(dest),'--sendxml='+str(xml),'--noprompt']
     if configured:cmd.append('--skip_configure')
     if search:cmd.append('--search_path='+str(search))
     run(label,cmd)
     assert 'All Finished Successfully' in (dest/(label+'.log')).read_text(errors='replace')
     configured=True
    def reset(label):
     root=ET.Element('data');ET.SubElement(root,'power',dict(value='reset'));fh(label,root)
    def read(label,lun,start,sectors,expected):
     root=ET.Element('data');ET.SubElement(root,'read',dict(SECTOR_SIZE_IN_BYTES='4096',physical_partition_number=str(lun),start_sector=str(start),num_partition_sectors=str(sectors),filename='readback.bin'))
     fh(label,root);path=dest/'readback.bin'
     assert path.stat().st_size==sectors*4096 and sha(path)==expected
     row=dict(label=label,lun=lun,start_sector=start,sectors=sectors,sha256=expected,utc=datetime.now(timezone.utc).isoformat())
     with (dest/'readbacks.jsonl').open('a') as out:out.write(json.dumps(row)+'\n')
     assert path.resolve().parent==dest.resolve() and path.name=='readback.bin'
     path.unlink()
    def read_boot(label,expected):
     read(label+'-boot',4,79366,24576,expected)
     read(label+'-dtbo',4,104298,6144,orig['partitions']['dtbo']['sha256'])
    def read_super(label,parts):
     for i,(_,start,sectors) in enumerate(chunks()):
      read(label+'-'+str(i).zfill(2),0,start,sectors,parts[i]);event(label+' verified '+str(i+1)+'/17')
    def write_boot(label,path,expected):
     assert sha(path)==expected
     root=ET.Element('data');ET.SubElement(root,'program',dict(SECTOR_SIZE_IN_BYTES='4096',physical_partition_number='4',start_sector='79366',num_partition_sectors='24576',filename=path.name,label='boot'))
     fh(label,root,path.parent)
    def restore():
     event('Restoring the verified original super and F.20 reader boot')
     fh('restore-super',ET.parse(stock/'stock-super-restore.xml').getroot(),stock)
     write_boot('restore-boot',stock/'boot.img',orig['partitions']['boot']['sha256'])
     read_boot('restored',orig['partitions']['boot']['sha256'])
     read_super('restored-super',[x['sha256'] for x in orig['partitions']['super']['parts']])
     reset('stock-reset');end=time.monotonic()+210
     while time.monotonic()<end:
      try:
       if phone('getprop sys.boot_completed',5)=='1':break
      except (OSError,subprocess.SubprocessError):pass
      time.sleep(2)
     else:raise RuntimeError('F.20 boot completion not observed')
     assert phone('getprop ro.build.display.id')=='RMX2072_11_F.20'
     for slot in (0,1):assert phone(f'lpdump -s {slot}')==(stock/f'slot{slot}.txt').read_text().strip()
     assert phone('sha256sum /dev/block/by-name/super',240).split()[0]==orig['partitions']['super']['sha256']
     restored=dict(firmware='RMX2072_11_F.20',sys_boot_completed=1,boot_id=phone('cat /proc/sys/kernel/random/boot_id'),super_sha256=orig['partitions']['super']['sha256'],boot_sha256=orig['partitions']['boot']['sha256'],dtbo_sha256=orig['partitions']['dtbo']['sha256'],lp_slots=[0,1])
     (dest/'restored.json').write_text(json.dumps(restored,indent=2)+'\n');event('F.20 restored; boot completion, both LP slots and full super digest match')
    
    assert sha(loader)=='9955d332f67bd610621d092520fa65626743e10a5b781c4f2ae532b99934dea9'
    assert verify(stock,'f7785aedd24616b251143cbcf6006612274b1cae9dac8dea1f634c5800c50532')['parts']==orig['partitions']['super']['parts']
    assert sha(stock/'boot.img')==orig['partitions']['boot']['sha256'] and sha(stock/'dtbo.img')==orig['partitions']['dtbo']['sha256']
    if restore_only:
     (dest/'recovery-ready.json').write_text(json.dumps(dict(original_images_verified=True,utc=datetime.now(timezone.utc).isoformat()))+'\n')
     event('Original recovery inputs verified; waiting for EDL')
     if args.recovery_gate:
      end=time.monotonic()+600
      while not args.recovery_gate.exists() and time.monotonic()<end:time.sleep(.2)
      gate=json.loads(args.recovery_gate.read_text())
      assert gate['trial']==trial and gate['allow_recovery'] is True
      event('Recovery gate released: '+json.dumps(gate))
     enter('recovery-entry');restore();sys.exit(0)
    assert sha(p/'boot/boot-diag.img')==boot['boot_sha256']
    assert [x['sha256'] for x in verify(p/'candidate',candidate['sha256'])['parts']]==candidate['parts']
    expected_rows=ET.fromstring(stock_restore_xml())
    for row in list(expected_rows):
     if int(row.attrib['filename'][11:13]) not in candidate['changed_chunks']:expected_rows.remove(row)
    actual_rows=ET.parse(p/'candidate/candidate.xml').getroot()
    assert [(x.tag,x.attrib) for x in actual_rows]==[(x.tag,x.attrib) for x in expected_rows]
    assert [(x.tag,x.attrib) for x in ET.parse(stock/'stock-super-restore.xml').getroot()]==[(x.tag,x.attrib) for x in ET.fromstring(stock_restore_xml())]
    assert json.loads((w/'recovery/edl-verification/verification.json').read_text())['independent_edl_reads_verified']
    previous_boot_sha=orig['partitions']['boot']['sha256']
    if args.boot_only_from:
     from gsi_adb_accept import inspect
     prior=args.boot_only_from.resolve()
     assert prior.parent==w/'records' and prior!=dest
     previous=json.loads((prior/'inputs.json').read_text())
     stable=json.loads((prior/'live/gsi-stable.json').read_text())
     proof=inspect(prior/'live',stable['identity'][2])
     previous_boot_sha=validate_boot_only(previous,stable,candidate,json.loads((p/'volumes/scratch.json').read_text()),proof)
     (dest/'boot-only-source.json').write_text(json.dumps(dict(previous_record=prior.name,previous_boot_sha256=previous_boot_sha,live=proof),indent=2)+'\n')
    else:
     info=phone('getprop ro.product.model; getprop ro.build.display.id; getprop sys.boot_completed; getprop ro.boot.flash.locked').splitlines()
     assert info==['RMX2072','RMX2072_11_F.20','1','0']
     assert int(phone('cat /sys/class/power_supply/battery/capacity'))>=25
     assert phone('sha256sum /dev/block/by-name/super',240).split()[0]==candidate['source_sha256']
     geometry=phone('readlink -f /dev/block/by-name/super; cat /sys/class/block/sda10/start /sys/class/block/sda10/size /sys/class/block/sda/queue/logical_block_size').splitlines()
     assert geometry==['/dev/block/sda10','1544256','17317888','4096']
    if args.retain_gsi:
     rd=json.loads((p/'ramdisk/ramdisk-provenance.json').read_text())
     assert rd.get('guarded_adb') and rd['trial_id']==trial
    (dest/'inputs.json').write_text(json.dumps(dict(trial=trial,source_commit=subprocess.check_output(['git','-C',str(audit.parents[1]),'rev-parse','HEAD'],text=True).strip(),kernel=json.loads((p/'kernel/provenance.json').read_text()),boot=boot,candidate=candidate,scratch=json.loads((p/'volumes/scratch.json').read_text()),usb_build=json.loads((p/'usb-build.json').read_text()) if args.retain_gsi else None,ramdisk=json.loads((p/'ramdisk/ramdisk-provenance.json').read_text())),indent=2)+'\n')
    event(('Retained GSI identity and unchanged container/volumes' if args.boot_only_from else 'F.20 identity and geometry')+'; complete recovery and candidate inputs verified')
    enter('entry',True)
    try:
     read_boot('before',previous_boot_sha)
     if args.boot_only_from:read_super('candidate-super-read',candidate['parts'])
     write_boot('test-boot',p/'boot/boot-diag.img',boot['boot_sha256'])
     if not args.boot_only_from:fh('candidate-super',ET.parse(p/'candidate/candidate.xml').getroot(),p/'candidate')
     read_boot('candidate',boot['boot_sha256'])
     if not args.boot_only_from:read_super('candidate-super-read',candidate['parts'])
    except BaseException:
     restore();raise
    event('Candidate boot and full super readback passed; starting physical test')
    env=dict(os.environ,PYTHONPATH=str(w/'serial-deps'))
    with (dest/'observer.log').open('xb') as log,(dest/'usb-observer.log').open('xb') as usb_log:
     observer=subprocess.Popen([sys.executable,'-u',audit/'observe_ufs_first_stage.py','--trial',trial,'--output',dest/'live','--observe-adb']+(['--retain-gsi'] if args.retain_gsi else [])+(['--autonomous'] if args.retain_gsi and rd.get('autonomous_ufs') else []),stdout=log,stderr=subprocess.STDOUT,env=env)
     usb=subprocess.Popen(['pwsh','-NoProfile','-File',audit/'watch_trial_usb.ps1','-Output',dest/'usb.jsonl','-HandoffEvents',dest/'live/host-events.jsonl'],stdout=usb_log,stderr=subprocess.STDOUT)
     end=time.monotonic()+20
     while not (dest/'usb.jsonl').exists() and time.monotonic()<end:
      if usb.poll() is not None:raise RuntimeError('USB observer failed before reset')
      time.sleep(.3)
     assert (dest/'usb.jsonl').exists()
     reset('test-reset')
     retained = False
     until = time.monotonic()+450
     while time.monotonic()<until:
      if args.retain_gsi and (dest/'live/gsi-accepted.json').exists():
       from gsi_adb_accept import soak_and_retain
       event('Authenticated API 37 ADB accepted; checking same-boot watchdog stability for 190 seconds')
       try:
        soak_and_retain(dest/'live');retained=True
       except (OSError,subprocess.SubprocessError,ValueError) as error:
        event('ADB soak failed; watchdog lease will expire: '+str(error))
        from observe_ufs_first_stage import previous_boot
        from uuid import UUID
        original=json.loads((dest/'live/gsi-accepted.json').read_text())['identity'][2]
        previous_boot(trial,UUID(original),dest/'live',time.monotonic()+300,return_on_accepted=False)
       break
      if any((x.vid,x.pid)==(0x05c6,0x9008) for x in comports()):break
      time.sleep(1)
     if not retained:enter('return')
     try:observer.wait(timeout=10)
     except subprocess.TimeoutExpired:observer.terminate();observer.wait(5)
     try:usb.wait(timeout=10)
     except subprocess.TimeoutExpired:usb.terminate();usb.wait(5)
    if retained:
     (dest/'gsi-retained.json').write_text(json.dumps(dict(current_mode='Android 17 GSI',candidate_super_retained=True,stock_restored=False,stable=json.loads((dest/'live/gsi-stable.json').read_text())),indent=2)+'\n')
     event('GSI ADB stable across old timers; guardian retained and phone left running Android 17')
     return
    read_boot('return',boot['boot_sha256'])
    adb_log=dest/'live/adb.jsonl'
    identities=[]
    event_path=dest/'live/host-events.jsonl'
    events=[json.loads(line) for line in event_path.read_text().splitlines()] if event_path.exists() else []
    original_boot=next((row['boot_id'] for row in events if row['event'] in ('handoff_requested','autonomous_handoff_observed')),None)
    expected_release=(p/'kernel/kernel.release').read_text().strip()
    if adb_log.exists():
     for line in adb_log.read_text().splitlines():
      for serial,identity in json.loads(line).get('identity',{}).items():
       if len(identity)>=5 and identity[1]=='37' and identity[2]=='running' and identity[3]==expected_release and identity[4]==original_boot:
        identities.append(dict(serial=serial,identity=identity))
    if identities and not args.retain_gsi:
     (dest/'gsi-retained.json').write_text(json.dumps(dict(gsi_adb_observed=identities,current_mode='EDL after bounded watchdog trial',candidate_super_retained=True,stock_restored=False),indent=2)+'\n')
     event('API 37 ADB was observed; retaining GSI layout for follow-up boot and watchdog handoff')
    else:restore()


if __name__ == '__main__':
    main()
