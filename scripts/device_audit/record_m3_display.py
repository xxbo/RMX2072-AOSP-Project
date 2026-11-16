"""Collect same-boot physical DRM and Android graphics evidence over retained GSI ADB."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
from gsi_adb_accept import inspect, shell


def evaluate_kms(snapshot):
    flips = [tuple(map(int, row)) for row in re.findall(
        r'^DRMTEST flip=(\d+) sequence=(\d+) time=(\d+)\.(\d{6})$', snapshot, re.M)]
    advancing = len(flips) == 4 and [row[0] for row in flips] == [1, 2, 3, 4]
    for before, after in zip(flips, flips[1:]):
        advancing &= (0 < (after[1]-before[1]) % (1 << 32) < (1 << 31)
                      and after[2:] > before[2:])
    reported = bool(re.search(r'DRMTEST kms_(?:scanout|events)=PASS', snapshot))
    errors = [line for line in snapshot.splitlines() if re.search(
        r"rcg didn't update|cmd dma tx failed|packet \d+ .*failed:|frame done timeout|failed wait_for_idle|kickoff timeout",
        line)]
    return dict(drm_kms_result='PASS_EVENTS_ONLY' if reported and advancing and not errors else 'BLOCKED_OR_FAILED',
                probe_reported_pass=reported, advancing_vblank_events=bool(advancing),
                transport_errors=errors)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--record', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    record = a.record.resolve()
    inputs = json.loads((record/'inputs.json').read_text())
    live = record/'live'
    accepted = json.loads((live/'gsi-accepted.json').read_text())
    boot = accepted['identity'][2]
    proof = inspect(live, boot)
    if proof['identity'][6] != 'retained' or not inputs['boot']['device_tree_build'].get('display'):
        raise ValueError('Requires the retained, matching M3 display candidate')
    snapshot = shell('cat /data/local/tmp/rmx-m3-display.txt', 15)
    if set(re.findall(r'^M3DISPLAY boot_id=(.*)$', snapshot, re.M)) != {boot}:
        raise ValueError('Display snapshot is absent or belongs to another boot')
    (live/'m3-display.txt').write_text(snapshot, encoding='utf-8')
    commands = {
        'scanout-state.txt': 'cat /data/vendor/rmx-m3-diag/scanout.txt',
        'graphics-status.txt': 'getprop init.svc.surfaceflinger; getprop init.svc.zygote; getprop init.svc.vendor.hwcomposer-3; getprop init.svc.vendor.graphics.allocator; getprop sys.boot_completed; service check SurfaceFlinger; service check android.hardware.graphics.composer3.IComposer/default; service check android.hardware.graphics.allocator.IAllocator/default',
        'drm-live.txt': 'ls -l /dev/dri; for p in /sys/class/drm/card*-DSI-*; do echo CONNECTOR=$p; cat $p/status $p/enabled $p/modes; done',
        'surfaceflinger.txt': 'timeout 20 dumpsys SurfaceFlinger',
        'graphics-logcat.txt': 'logcat -b all -d -s SurfaceFlinger libEGL RenderEngine drmhwc minigbm DEBUG',
        'graphics-services.txt': 'getprop ro.hardware.egl; getprop ro.hardware.vulkan; getprop ro.hardware.gralloc; getprop vendor.minigbm.debug; getprop ro.sf.lcd_density; getprop ro.zygote; ps -AZ | grep -E "surfaceflinger|composer|allocator|zygote|system_server"; ls -lZ /dev/dri /vendor/bin/hw /vendor/lib64/egl /vendor/lib64/hw; service list | grep -E "graphics|SurfaceFlinger|activity|package"',
        'graphics-startup-logcat.txt': 'logcat -b all -d -t 1500 -s init servicemanager hwservicemanager linker auditd libc AndroidRuntime',
    }
    observations = {}
    for name,command in commands.items():
        try:
            text = shell(command, 30)
            status = 0
        except subprocess.CalledProcessError as error:
            text = error.output
            status = error.returncode
        (live/name).write_text(text, encoding='utf-8')
        excerpt = '\n'.join(text.splitlines()[:120])[:12000]
        observations[name] = dict(sha256=hashlib.sha256(text.encode()).hexdigest(),
            bytes=len(text.encode()), local_record='live/'+name, text=excerpt,
            text_truncated=excerpt != text.rstrip('\n'), exit_status=status)
    final_boot = shell('cat /proc/sys/kernel/random/boot_id').strip()
    if final_boot != boot:
        raise ValueError('Boot changed during display collection')
    kms = evaluate_kms(snapshot)
    result = dict(utc=datetime.now(timezone.utc).isoformat(), goal='Physical display, then SurfaceFlinger and AOSP desktop',
        trial=inputs['trial'], boot_id=boot, kernel=inputs['kernel'],
        boot_sha256=inputs['boot']['boot_sha256'], dtbo_sha256=inputs['boot']['dtbo_sha256'],
        effective_dtb=inputs['boot']['device_tree_build']['outputs']['effective.dtb'],
        system=inputs['candidate']['signed']['system'], vendor=inputs['candidate']['signed']['vendor'],
        **kms, physical_screen_observation='PENDING_OPERATOR; KMS success is not visual confirmation',
        display_snapshot=snapshot, android_graphics=observations,
        cold_start_test='NOT RUN', watchdog_fault_injection='NOT RUN',
        handset_left='retained Android 17 GSI')
    a.output.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(dict(trial=result['trial'], boot_id=boot, drm_kms_result=kms['drm_kms_result'],
                         physical_screen_observation=result['physical_screen_observation'])))


if __name__ == '__main__':
    main()
