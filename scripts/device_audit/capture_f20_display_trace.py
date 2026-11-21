"""Bounded stock display clock trace with refresh setting restoration."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shlex
import time

from capture_f20_display_baseline import shell


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    a=p.parse_args()
    identity=shell('getprop ro.build.display.id; cat /proc/sys/kernel/random/boot_id; id').splitlines()
    if identity[0]!='RMX2072_11_F.20' or not identity[-1].startswith('uid=0('):
        raise ValueError('Matching stock root shell required')
    a.output.mkdir(parents=True,exist_ok=False)
    root='/sys/kernel/tracing/instances/rmx_m3_f20_20261118'
    saved=shell('settings get system peak_refresh_rate').strip()
    if saved not in ('60.0', '60.000004', '90.0'):
        raise ValueError('Unexpected live peak refresh setting: '+repr(saved))
    shell('mkdir '+root)
    outputs={}
    def save(name,data):
        raw=data.encode('utf-8')
        (a.output/(name+'.txt')).write_bytes(raw)
        outputs[name]=dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
    try:
        shell(f'echo 0 > {root}/tracing_on; echo 512 > {root}/buffer_size_kb')
        for event in ('clk_set_rate','clk_set_rate_complete','clk_set_parent','clk_set_parent_complete','clk_prepare','clk_prepare_complete'):
            path=f'{root}/events/clk/{event}'
            save('format-'+event,shell('cat '+path+'/format'))
            shell(f'echo 1 > {path}/enable')
        save('format-sde_evtlog',shell(f'cat {root}/events/sde/sde_evtlog/format'))
        shell(f'echo 1 > {root}/events/sde/sde_evtlog/enable; echo 1 > {root}/tracing_on')
        shell('settings put system peak_refresh_rate 60.0; input keyevent 224')
        time.sleep(3)
        save('mode60-before-sleep',shell('dumpsys SurfaceFlinger --displays; cat /sys/kernel/oplus_display/mipi_clk_rate_hz'))
        # A display power cycle, not a phone restart or a cold-start test.
        shell('input keyevent 223')
        time.sleep(2)
        shell('input keyevent 224')
        time.sleep(4)
        shell(f'echo 0 > {root}/tracing_on')
        save('trace60',shell('cat '+root+'/trace',30))
        save('mode60',shell('dumpsys SurfaceFlinger --displays; cat /sys/kernel/oplus_display/mipi_clk_rate_hz; cat /sys/kernel/oplus_display/power_status'))
        save('display-log60',shell('dmesg | grep -E "dsi_display_set_mode|clk_rate|bit_clk|DSI.*error" | tail -100'))
    finally:
        shell('input keyevent 224; settings put system peak_refresh_rate '+shlex.quote(saved))
        shell(f'echo 0 > {root}/tracing_on; echo 0 > {root}/events/enable')
        # rmdir removes only this private trace instance, never another tracer.
        shell('rmdir '+root)
        restored=shell('settings get system peak_refresh_rate').strip()
        if restored!=saved:
            raise ValueError('Refresh setting restoration failed')
    if shell('cat /proc/sys/kernel/random/boot_id').strip()!=identity[1]:
        raise ValueError('Stock boot changed')
    (a.output/'trace.json').write_text(json.dumps(dict(utc=datetime.now(timezone.utc).isoformat(),
        boot_id=identity[1],original_peak_refresh_rate=saved,restored_peak_refresh_rate=restored,
        private_instance_removed=True,results=outputs,
        scope='Requested stock 60 Hz and display-only sleep/wake trace. The request does not prove the active mode; inspect mode60 and display-log60. No reboot or register writes. Local SurfaceFlinger dumps are not for public upload.'),indent=2)+'\n',encoding='utf-8')
    print('F20_TRACE_COMPLETE settings restored',flush=True)


if __name__=='__main__':
    main()
