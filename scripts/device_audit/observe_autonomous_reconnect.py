"""Wait for a new autonomous boot after a separately recorded operator power cycle.

This observer never requests Android handoff or sets the device clock. USB
absence alone does not establish cold power-off; preserve the operator steps.
"""
import argparse,json,subprocess,time
from datetime import datetime,timezone
from pathlib import Path
from uuid import UUID
from gsi_adb_accept import SERIAL,shell,fetch_autonomous,accept,soak_and_retain

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--previous-boot',type=UUID,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--timeout',type=int,default=900)
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
    start=time.monotonic();last=None
    (a.output/'observer.json').write_text(json.dumps(dict(previous_boot=str(a.previous_boot),utc=datetime.now(timezone.utc).isoformat(),starts_android=False,sets_clock=False),indent=2)+'\n')
    with (a.output/'transports.jsonl').open('w') as log:
        while time.monotonic()-start<a.timeout:
            row=dict(elapsed=round(time.monotonic()-start,3),utc=datetime.now(timezone.utc).isoformat())
            try:
                listing=subprocess.check_output(['adb','devices','-l'],text=True,timeout=3)
                row['transports']=[x for x in listing.splitlines() if x.strip() and not x.startswith('List of devices')]
                if any(x.startswith(SERIAL) and x.split()[1]=='device' for x in row['transports']):
                    boot=shell('cat /proc/sys/kernel/random/boot_id').strip();UUID(boot);row['boot_id']=boot
                    if boot!=str(a.previous_boot):
                        assert fetch_autonomous(a.output)==boot
                        proof=accept(a.output,boot)
                        print('Accepted new autonomous GSI boot '+boot,flush=True)
                        log.write(json.dumps(row)+'\n');log.flush()
                        result=soak_and_retain(a.output)
                        (a.output/'result.json').write_text(json.dumps(dict(current_mode='Android 17 GSI',stable=result,previous_boot=str(a.previous_boot),cold_power_cycle='Requires separate operator/USB evidence'),indent=2)+'\n')
                        print('New autonomous boot retained',flush=True)
                        return
            except (OSError,subprocess.SubprocessError,ValueError) as error:
                row['error']=str(error)
            log.write(json.dumps(row)+'\n');log.flush()
            state=(row.get('transports'),row.get('boot_id'),row.get('error'))
            if state!=last:print(json.dumps(row),flush=True);last=state
            time.sleep(1)
    raise TimeoutError('No accepted new autonomous GSI boot; inspect USB and recover F20')

if __name__=='__main__':main()
