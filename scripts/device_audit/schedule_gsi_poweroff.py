"""Schedule an authorized GSI power-off, allowing the operator to unplug USB."""
import argparse,json,subprocess,time
from datetime import datetime,timezone
from pathlib import Path
from gsi_adb_accept import SERIAL,inspect,shell

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--evidence',type=Path,required=True)
p.add_argument('--output',type=Path,required=True)
p.add_argument('--delay',type=int,default=75)
p.add_argument('--require-power-drivers',action='store_true')
a=p.parse_args()
if not 30<=a.delay<=120:p.error('Use a bounded 30..120 second operator window')
boot=shell('cat /proc/sys/kernel/random/boot_id').strip()
proof=inspect(a.evidence,boot)
assert proof['identity'][6]=='retained'
power=None
if a.require_power_drivers:
    from check_power_ready import check_power_ready
    power=check_power_ready(shell('cat /data/local/tmp/rmx-m1-power.txt'),boot)
a.output.mkdir(parents=True,exist_ok=False)
script=a.output/'poweroff.sh'
script.write_text('#!/system/bin/sh\nset -eu\nsleep '+str(a.delay)+'\n[ "$(cat /proc/sys/kernel/random/boot_id)" = "'+boot+'" ]\necho "poweroff_requested uptime=$(cat /proc/uptime)"\n/system/bin/reboot -p\n',encoding='utf-8',newline='\n')
remote='/data/local/tmp/rmx-m1-poweroff.sh'
subprocess.run(['adb','-s',SERIAL,'push',str(script),remote],check=True,timeout=15)
start=time.monotonic();utc=datetime.now(timezone.utc).isoformat()
reply=shell('nohup /system/bin/sh '+remote+' > /data/local/tmp/rmx-m1-poweroff.log 2>&1 < /dev/null & echo scheduled_pid=$!')
record=dict(boot_id=boot,utc=utc,monotonic=start,delay_seconds=a.delay,planned_host_monotonic=start+a.delay,reply=reply.strip(),before_identity=proof['identity'],power_drivers=power,command='/system/bin/reboot -p',operator_action='Unplug before deadline; remain disconnected until separately prompted to power on')
(a.output/'scheduled.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps(record,indent=2))
