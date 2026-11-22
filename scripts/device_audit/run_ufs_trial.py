"""Run a bounded RMX2072 UFS trial with one verified recovery set.

Workspace layout: recovery/f20, recovery/tools, recovery/OplusEdlTool/Tools,
serial-deps, current/{boot,kernel,candidate,volumes}, and records. All large
readback files are removed only after their expected digest matches. No
partition outside boot, DTBO and super is programmed. Original userdata is untouched.
The guarded profile keeps GSI running only after authenticated identity checks,
a renewable watchdog lease and a 190-second ADB soak; failures recover to F.20.
The original recovery set is reused. Re-reading complete stock partitions is
opt-in; normal recovery checks loader acknowledgements, boot identity and LP metadata.
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


def validate_scratch_resize(old, new):
    """Only the explicit 512 MiB -> 2 GiB RAM data seed expansion is allowed."""
    if (set(old) != {'data', 'metadata'} or set(new) != set(old)
            or old['metadata'] != new['metadata']
            or old['data']['bytes'] != 512 << 20 or new['data']['bytes'] != 2048 << 20):
        raise ValueError('Scratch resize must preserve metadata and expand only RAM data to 2 GiB')
    mutable = {'bytes', 'sha256', 'gzip_sha256'}
    if (set(old['data']) != set(new['data'])
            or {k:v for k,v in old['data'].items() if k not in mutable}
            != {k:v for k,v in new['data'].items() if k not in mutable}
            or new['data'].get('uuid') != '56baa650-68d8-498b-95f3-a9ac4e11127d'
            or any(not re.fullmatch(r'[0-9a-f]{64}', new['data'].get(k, ''))
                   for k in ('sha256', 'gzip_sha256'))):
        raise ValueError('Scratch resize changed identity or lacks checked digests')


def validate_vendor_update(previous, stable, candidate, scratch, live, resize_scratch_data=False):
    """Permit only a project-vendor update over an accepted retained GSI."""
    old = previous['candidate']
    if resize_scratch_data:
        validate_scratch_resize(previous['scratch'], scratch)
    digest = validate_boot_only(previous, stable, old,
                                previous['scratch'] if resize_scratch_data else scratch, live)
    if (old['source_sha256'] != candidate['source_sha256'] or old['bytes'] != candidate['bytes']
            or old['signed']['system'] != candidate['signed']['system']
            or old['signed']['vendor']['key_sha256'] != candidate['signed']['vendor']['key_sha256']
            or not 0 < candidate['signed']['vendor']['bytes'] <= 264 << 20):
        raise ValueError('Vendor update must retain the GSI, signing key and recovery geometry')
    old_active, new_active = old['partitions_after'][0], candidate['partitions_after'][0]
    if {n:h for n,h in old_active.items() if n != 'vendor'} != {n:h for n,h in new_active.items() if n != 'vendor'}:
        raise ValueError('Vendor update changed another active logical partition')
    for parts in (old['parts'], candidate['parts']):
        if len(parts) != 17 or any(not re.fullmatch(r'[0-9a-f]{64}', h) for h in parts):
            raise ValueError('Vendor update requires complete 17-chunk manifests')
    # Compare both actual layouts, not just the new candidate against F.20.
    # A chunk returning to stock bytes must also be rewritten.
    return digest, [n for n, (before, after) in enumerate(zip(old['parts'], candidate['parts'])) if before != after]


def verify_stock_readbacks(original, read_boot, read_super, enabled=False):
    """Reuse the acquisition by default; never imply a fresh stock readback."""
    if not enabled:
        return False
    read_boot('restored', original['partitions']['boot']['sha256'])
    read_super('restored-super', [x['sha256'] for x in original['partitions']['super']['parts']])
    return True


def verify_stock_phone_digest(phone, expected, enabled=False):
    """Do not scan the handset's full stock super during routine trials."""
    if not enabled:
        return None
    actual = phone('sha256sum /dev/block/by-name/super', 240).split()[0]
    if actual != expected:
        raise ValueError('Stock super digest mismatch')
    return actual


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', type=Path, required=True)
    parser.add_argument('--trial', required=True)
    parser.add_argument('--restore-only', action='store_true')
    parser.add_argument('--verify-stock-partitions', action='store_true', help='Explicit diagnostic: re-read stock boot/DTBO/super and compute phone-side super hash; default reuses the verified original set')
    parser.add_argument('--recovery-gate', type=Path, help='Restore only: validate now, wait for this explicit JSON handoff before capturing EDL')
    parser.add_argument('--retain-gsi', action='store_true')
    retained = parser.add_mutually_exclusive_group()
    retained.add_argument('--boot-only-from', type=Path, help='Previous retained trial record; read all super bytes, then program boot and its paired DTBO')
    retained.add_argument('--vendor-update-from', type=Path, help='Verify the retained layout, update only vendor-related container changes and paired boot, then read back the complete candidate')
    parser.add_argument('--resize-scratch-data', action='store_true', help='With vendor update only: permit the checked 512 MiB to 2 GiB RAM data seed expansion, preserving metadata')
    parser.add_argument('--record-suffix', default='', help='New evidence directory for repeating the exact current image')
    parser.add_argument('--resume-prewrite', type=Path, help='Resume only an interrupted first boot READ after a verified Firehose drain; recheck every byte before writing')
    args = parser.parse_args()
    if args.resize_scratch_data and not args.vendor_update_from:
        parser.error('--resize-scratch-data requires --vendor-update-from')
    sys.path.insert(0, str(args.workspace.resolve()/'serial-deps'))
    from serial.tools.list_ports import comports
    from check_super_chunks import chunks, verify, stock_restore_xml
    w=args.workspace.resolve();p=w/'current';stock=w/'recovery/f20';tools=w/'recovery/OplusEdlTool/Tools';loader=w/'recovery/tools/devprg_865_1';audit=Path(__file__).resolve().parent
    trial=args.trial;assert re.fullmatch(r'ufs-host-g3-gsi17-firststage-ufs-\d{2}',trial)
    restore_only=args.restore_only
    from_gsi = args.boot_only_from or args.vendor_update_from
    assert not args.recovery_gate or restore_only
    assert not from_gsi or (args.retain_gsi and not restore_only)
    assert not args.record_suffix or re.fullmatch(r'[a-z0-9-]{1,32}',args.record_suffix)
    assert not args.resume_prewrite or (args.boot_only_from and args.record_suffix and args.retain_gsi)
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
     if initial and args.resume_prewrite:
      ports=[x.device for x in comports() if (x.vid,x.pid)==(0x05c6,0x9008)]
      assert len(ports)==1
      port=ports[0];configured=True
      event('Resuming drained Firehose at first read; all boot/DTBO/super reads will run again')
      return
     if initial:subprocess.run(['adb','-s','RMX2072-M1' if from_gsi else '3c8304a6','reboot','edl'],check=True,timeout=15)
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
    def read_boot(label,expected,dtbo_expected=None):
     read(label+'-boot',4,79366,24576,expected)
     read(label+'-dtbo',4,104298,6144,dtbo_expected or orig['partitions']['dtbo']['sha256'])
    def read_super(label,parts):
     for i,(_,start,sectors) in enumerate(chunks()):
      read(label+'-'+str(i).zfill(2),0,start,sectors,parts[i]);event(label+' verified '+str(i+1)+'/17')
    def write_boot(label,path,expected):
     assert sha(path)==expected
     root=ET.Element('data');ET.SubElement(root,'program',dict(SECTOR_SIZE_IN_BYTES='4096',physical_partition_number='4',start_sector='79366',num_partition_sectors='24576',filename=path.name,label='boot'))
     fh(label,root,path.parent)
    def write_dtbo(label,path,expected):
     assert path.stat().st_size==25165824 and sha(path)==expected
     root=ET.Element('data');ET.SubElement(root,'program',dict(SECTOR_SIZE_IN_BYTES='4096',physical_partition_number='4',start_sector='104298',num_partition_sectors='6144',filename=path.name,label='dtbo'))
     fh(label,root,path.parent)
    def restore():
     event('Restoring the verified original super, DTBO and F.20 reader boot')
     fh('restore-super',ET.parse(stock/'stock-super-restore.xml').getroot(),stock)
     write_boot('restore-boot',stock/'boot.img',orig['partitions']['boot']['sha256'])
     write_dtbo('restore-dtbo',stock/'dtbo.img',orig['partitions']['dtbo']['sha256'])
     full_stock_readback=verify_stock_readbacks(orig,read_boot,read_super,args.verify_stock_partitions)
     reset('stock-reset');end=time.monotonic()+210
     while time.monotonic()<end:
      try:
       if phone('getprop sys.boot_completed',5)=='1':break
      except (OSError,subprocess.SubprocessError):pass
      time.sleep(2)
     else:raise RuntimeError('F.20 boot completion not observed')
     assert phone('getprop ro.build.display.id')=='RMX2072_11_F.20'
     for slot in (0,1):assert phone(f'lpdump -s {slot}')==(stock/f'slot{slot}.txt').read_text().strip()
     super_digest=verify_stock_phone_digest(phone,orig['partitions']['super']['sha256'],args.verify_stock_partitions)
     restored=dict(firmware='RMX2072_11_F.20',sys_boot_completed=1,boot_id=phone('cat /proc/sys/kernel/random/boot_id'),super_sha256=super_digest,boot_sha256=orig['partitions']['boot']['sha256'] if full_stock_readback else None,dtbo_sha256=orig['partitions']['dtbo']['sha256'] if full_stock_readback else None,lp_slots=[0,1],stock_full_partition_readback=full_stock_readback,stock_write_acknowledged=True,expected_image_sha256={name:orig['partitions'][name]['sha256'] for name in ('boot','dtbo','super')},verification_policy='full-stock-readback' if full_stock_readback else 'reuse-original-backup-write-ack-boot-and-lp-metadata')
     (dest/'restored.json').write_text(json.dumps(restored,indent=2)+'\n')
     event('F.20 restored; boot completion and both LP slots match; '+('full stock readback and super digest match' if full_stock_readback else 'original backup reused, full stock partition readback NOT RUN'))
    
    assert sha(loader)=='9955d332f67bd610621d092520fa65626743e10a5b781c4f2ae532b99934dea9'
    assert verify(stock,'f7785aedd24616b251143cbcf6006612274b1cae9dac8dea1f634c5800c50532')['parts']==orig['partitions']['super']['parts']
    assert sha(stock/'boot.img')==orig['partitions']['boot']['sha256'] and sha(stock/'dtbo.img')==orig['partitions']['dtbo']['sha256']
    if restore_only:
     (dest/'recovery-ready.json').write_text(json.dumps(dict(original_images_verified=True,full_stock_partition_readback_requested=args.verify_stock_partitions,utc=datetime.now(timezone.utc).isoformat()))+'\n')
     event('Original recovery inputs verified; waiting for EDL')
     if args.recovery_gate:
      end=time.monotonic()+600
      while not args.recovery_gate.exists() and time.monotonic()<end:time.sleep(.2)
      gate=json.loads(args.recovery_gate.read_text())
      assert gate['trial']==trial and gate['allow_recovery'] is True
      event('Recovery gate released: '+json.dumps(gate))
     enter('recovery-entry');restore();sys.exit(0)
    assert sha(p/'boot/boot-diag.img')==boot['boot_sha256']
    # Reject a partially refreshed current directory before entering EDL.
    assert sha(p/'kernel/Image')==boot['kernel_sha256']
    assert json.loads((p/'kernel/provenance.json').read_text())['image_sha256']==boot['kernel_sha256']
    assert sha(p/'ramdisk/ramdisk.cpio.gz')==boot['ramdisk_sha256']
    assert json.loads((p/'ramdisk/ramdisk-provenance.json').read_text())['gzip_sha256']==boot['ramdisk_sha256']
    if args.retain_gsi:
     assert json.loads((p/'usb-build.json').read_text())['kernel']==boot['kernel_sha256']
    candidate_dtbo_sha=boot['dtbo_sha256']
    if candidate_dtbo_sha!=orig['partitions']['dtbo']['sha256']:
     assert boot.get('source_device_trees') is True
     assert sha(p/'boot/dtbo-diag.img')==candidate_dtbo_sha
     assert (p/'boot/dtbo-diag.img').stat().st_size==25165824
    assert [x['sha256'] for x in verify(p/'candidate',candidate['sha256'])['parts']]==candidate['parts']
    expected_rows=ET.fromstring(stock_restore_xml())
    for row in list(expected_rows):
     if int(row.attrib['filename'][11:13]) not in candidate['changed_chunks']:expected_rows.remove(row)
    actual_rows=ET.parse(p/'candidate/candidate.xml').getroot()
    assert [(x.tag,x.attrib) for x in actual_rows]==[(x.tag,x.attrib) for x in expected_rows]
    assert [(x.tag,x.attrib) for x in ET.parse(stock/'stock-super-restore.xml').getroot()]==[(x.tag,x.attrib) for x in ET.fromstring(stock_restore_xml())]
    assert json.loads((w/'recovery/edl-verification/verification.json').read_text())['independent_edl_reads_verified']
    previous_boot_sha=orig['partitions']['boot']['sha256']
    previous_dtbo_sha=orig['partitions']['dtbo']['sha256']
    update_chunks=[]
    if from_gsi:
     from gsi_adb_accept import inspect
     prior=from_gsi.resolve()
     assert prior.parent==w/'records' and prior!=dest
     previous=json.loads((prior/'inputs.json').read_text())
     stable=json.loads((prior/'live/gsi-stable.json').read_text())
     if args.resume_prewrite:
      interrupted=args.resume_prewrite.resolve()
      assert interrupted.parent==w/'records' and interrupted!=dest and interrupted.name==trial
      saved=json.loads((interrupted/'inputs.json').read_text())
      # This entry point cannot resume any write, reset or later experiment.
      xmls=list(interrupted.glob('*.xml'))
      assert {x.name for x in xmls}=={'before-boot.xml'}
      root=ET.parse(xmls[0]).getroot()
      assert len(root)==1 and root[0].tag=='read' and root[0].attrib==dict(SECTOR_SIZE_IN_BYTES='4096',physical_partition_number='4',start_sector='79366',num_partition_sectors='24576',filename='readback.bin')
      timeline=[json.loads(x) for x in (interrupted/'timeline.jsonl').read_text().splitlines()]
      assert [x['event'] for x in timeline]==['Retained GSI identity and unchanged container/volumes; complete recovery and candidate inputs verified','entry Sahara ready']
      drain=json.loads((interrupted/'interrupted-read-drain.json').read_text())
      tail=bytes.fromhex(drain['tail_hex'])
      assert drain['bytes_drained']>0 and tail.endswith(b'<response value="ACK" rawmode="false" /></data>')
      assert saved['trial']==trial and saved['boot']==boot and saved['candidate']==candidate
      assert saved['scratch']==json.loads((p/'volumes/scratch.json').read_text())
      assert saved['kernel']==json.loads((p/'kernel/provenance.json').read_text())
      assert saved['ramdisk']==json.loads((p/'ramdisk/ramdisk-provenance.json').read_text())
      assert saved['usb_build']==json.loads((p/'usb-build.json').read_text())
      source=json.loads((interrupted/'boot-only-source.json').read_text())
      assert source['previous_record']==prior.name and source['previous_boot_sha256']==previous['boot']['boot_sha256'] and source['chunks_to_write']==[]
      proof=source['live']
      (dest/'prewrite-resume.json').write_text(json.dumps(dict(interrupted_record=interrupted.name,scope='Saved pre-EDL identity only; fresh complete partition verification mandatory',drain=drain),indent=2)+'\n')
     else:
      proof=inspect(prior/'live',stable['identity'][2])
     scratch=json.loads((p/'volumes/scratch.json').read_text())
     if args.vendor_update_from:
      previous_boot_sha,update_chunks=validate_vendor_update(previous,stable,candidate,scratch,proof,args.resize_scratch_data)
     else:
      previous_boot_sha=validate_boot_only(previous,stable,candidate,scratch,proof)
     previous_dtbo_sha=previous['boot']['dtbo_sha256']
     assert re.fullmatch(r'[0-9a-f]{64}',previous_dtbo_sha)
     (dest/('vendor-update-source.json' if args.vendor_update_from else 'boot-only-source.json')).write_text(json.dumps(dict(previous_record=prior.name,previous_boot_sha256=previous_boot_sha,live=proof,chunks_to_write=update_chunks,resize_scratch_data=args.resize_scratch_data),indent=2)+'\n')
    else:
     info=phone('getprop ro.product.model; getprop ro.build.display.id; getprop sys.boot_completed; getprop ro.boot.flash.locked').splitlines()
     assert info==['RMX2072','RMX2072_11_F.20','1','0']
     assert int(phone('cat /sys/class/power_supply/battery/capacity'))>=25
     verify_stock_phone_digest(phone,candidate['source_sha256'],args.verify_stock_partitions)
     for slot in (0,1):assert phone(f'lpdump -s {slot}')==(stock/f'slot{slot}.txt').read_text().strip()
     geometry=phone('readlink -f /dev/block/by-name/super; cat /sys/class/block/sda10/start /sys/class/block/sda10/size /sys/class/block/sda/queue/logical_block_size').splitlines()
     assert geometry==['/dev/block/sda10','1544256','17317888','4096']
    if args.retain_gsi:
     rd=json.loads((p/'ramdisk/ramdisk-provenance.json').read_text())
     assert rd.get('guarded_adb') and rd['trial_id']==trial
    (dest/'inputs.json').write_text(json.dumps(dict(trial=trial,source_commit=subprocess.check_output(['git','-C',str(audit.parents[1]),'rev-parse','HEAD'],text=True).strip(),kernel=json.loads((p/'kernel/provenance.json').read_text()),boot=boot,candidate=candidate,scratch=json.loads((p/'volumes/scratch.json').read_text()),usb_build=json.loads((p/'usb-build.json').read_text()) if args.retain_gsi else None,ramdisk=json.loads((p/'ramdisk/ramdisk-provenance.json').read_text())),indent=2)+'\n')
    event(('Retained GSI identity and checked vendor-update plan' if args.vendor_update_from else 'Retained GSI identity and unchanged container/volumes' if args.boot_only_from else 'F.20 identity and geometry')+'; complete recovery and candidate inputs verified')
    enter('entry',True)
    try:
     if from_gsi or args.verify_stock_partitions:read_boot('before',previous_boot_sha,previous_dtbo_sha)
     if args.boot_only_from:read_super('candidate-super-read',candidate['parts'])
     if args.vendor_update_from:read_super('previous-super-read',previous['candidate']['parts'])
     write_boot('test-boot',p/'boot/boot-diag.img',boot['boot_sha256'])
     if candidate_dtbo_sha!=previous_dtbo_sha:
      path=stock/'dtbo.img' if candidate_dtbo_sha==orig['partitions']['dtbo']['sha256'] else p/'boot/dtbo-diag.img'
      write_dtbo('test-dtbo',path,candidate_dtbo_sha)
     if args.vendor_update_from:
      update=ET.fromstring(stock_restore_xml())
      for row in list(update):
       if int(row.attrib['filename'][11:13]) not in update_chunks:update.remove(row)
      if len(update):fh('candidate-super-update',update,p/'candidate')
     elif not args.boot_only_from:fh('candidate-super',ET.parse(p/'candidate/candidate.xml').getroot(),p/'candidate')
     read_boot('candidate',boot['boot_sha256'],candidate_dtbo_sha)
     if not args.boot_only_from:read_super('candidate-super-read',candidate['parts'])
    except BaseException:
     restore();raise
    event('Candidate boot and full super readback passed; starting physical test')
    env=dict(os.environ,PYTHONPATH=str(w/'serial-deps'))
    with (dest/'observer.log').open('xb') as log,(dest/'usb-observer.log').open('xb') as usb_log:
     observer=subprocess.Popen([sys.executable,'-u',audit/'observe_ufs_first_stage.py','--trial',trial,'--output',dest/'live','--observe-adb']+(['--retain-gsi'] if args.retain_gsi else [])+(['--autonomous'] if args.retain_gsi and rd.get('autonomous_ufs') else [])+(['--staged-display'] if args.retain_gsi and rd.get('display_staged') else []),stdout=log,stderr=subprocess.STDOUT,env=env)
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
        if boot.get('source_device_trees'):
         from check_m2_boot import check_m2_boot
         from gsi_adb_accept import shell
         accepted=json.loads((dest/'live/gsi-accepted.json').read_text())
         text=shell('cat /data/local/tmp/rmx-m2-boot.txt')
         checked=check_m2_boot(text,accepted['identity'][2],rd['first_stage_init_sha256'],accepted['identity'][1],(dest/'live/boot-events.txt').read_text(),display=boot.get('device_tree_build',{}).get('display',False))
         (dest/'live/m2-components.txt').write_text(text)
         (dest/'live/m2-components.json').write_text(json.dumps(checked,indent=2)+'\n')
        soak_and_retain(dest/'live');retained=True
       except (OSError,subprocess.SubprocessError,ValueError) as error:
        event('GSI acceptance failed; requesting guarded rollback: '+str(error))
        from observe_ufs_first_stage import previous_boot
        from gsi_adb_accept import shell
        from uuid import UUID
        original=json.loads((dest/'live/gsi-accepted.json').read_text())['identity'][2]
        try:shell('/vendor/bin/hw/rmx-m1-control --rollback '+original)
        except (OSError,subprocess.SubprocessError):pass
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
     gated=bool(rd.get('display_staged'))
     (dest/'gsi-retained.json').write_text(json.dumps(dict(current_mode='Android 17 GSI',candidate_super_retained=True,stock_restored=False,retention_scope='current-boot-only',host_start_required_after_every_reboot=gated,stable=json.loads((dest/'live/gsi-stable.json').read_text())),indent=2)+'\n')
     event('GSI ADB stable in this boot; guardian retained and phone left running Android 17')
     if gated:
      event('HOST-GATED DISPLAY IMAGE: every reboot still requires the observer to release the display gate; without it the 180-second EDL timer runs. Current-boot retention does not establish unattended restart.')
     return
    try:read_boot('return',boot['boot_sha256'],candidate_dtbo_sha)
    except BaseException:
     restore();raise
    adb_log=dest/'live/adb.jsonl'
    identities=[]
    event_path=dest/'live/host-events.jsonl'
    events=[json.loads(line) for line in event_path.read_text().splitlines()] if event_path.exists() else []
    original_boot=next((row['boot_id'] for row in events if row['event'] in ('handoff_requested','autonomous_handoff_observed','staged_display_handoff_observed')),None)
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
