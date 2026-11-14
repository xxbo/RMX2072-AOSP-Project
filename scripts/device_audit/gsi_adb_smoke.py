"""Exercise authenticated GSI file transfer on the disposable data volume."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import time
import uuid
from gsi_adb_accept import SERIAL, inspect, shell

def run(output, boot):
    before=inspect(output,boot)
    mountinfo=shell('cat /proc/self/mountinfo')
    if not any(x.split()[2]=='7:0' and x.split()[4]=='/data' and ' - ext4 ' in x for x in mountinfo.splitlines() if len(x.split())>6):
        raise ValueError('Expected disposable loop data mount')
    remote='/data/local/tmp/rmx-m1-adb-'+uuid.uuid4().hex
    result=dict(boot_id=boot,bytes=1048576,identity=before['identity'],data_mountinfo=[x for x in mountinfo.splitlines() if x.split()[4] in ('/data','/metadata')])
    with tempfile.TemporaryDirectory(prefix='rmx-m1-adb-') as local:
        src=Path(local)/'probe.bin';dst=Path(local)/'returned.bin'
        src.write_bytes(bytes(range(256))*4096)
        expected=hashlib.sha256(src.read_bytes()).hexdigest()
        shell('mkdir -m 700 '+remote)
        try:
            for label,args in [('push',['push',str(src),remote+'/probe.bin']),('pull',['pull',remote+'/probe.bin',str(dst)])]:
                start=time.monotonic()
                result[label]=subprocess.check_output(['adb','-s',SERIAL]+args,text=True,stderr=subprocess.STDOUT,timeout=30).strip()
                result[label+'_seconds']=round(time.monotonic()-start,3)
            result['device_sha256']=shell('sha256sum '+remote+'/probe.bin').split()[0]
            result['returned_sha256']=hashlib.sha256(dst.read_bytes()).hexdigest()
            assert result['device_sha256']==result['returned_sha256']==expected
            result['maintenance']=shell('service check android.security.maintenance').strip()
            result['shell_identity']=shell('id').strip()
            result['uptime']=shell('cat /proc/uptime').strip()
            result['boot_completed']=shell('getprop sys.boot_completed').strip()
            # A wrong boot must not change the current guard lease/retention.
            rejected=subprocess.run(['adb','-s',SERIAL,'shell','/vendor/bin/hw/rmx-m1-control','--keep',str(uuid.uuid4())],capture_output=True,text=True,timeout=8)
            result['wrong_boot_rejected']=rejected.returncode!=0 and rejected.stdout.strip()=='rejected'
            assert result['wrong_boot_rejected']
            result['after']=inspect(output,boot)['identity']
        finally:
            shell('rm -f '+remote+'/probe.bin; rmdir '+remote)
        result['temporary_files_removed']=shell('test ! -e '+remote+' && echo removed').strip()=='removed'
        assert result['temporary_files_removed']
    (output/'adb-smoke.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--boot-id',required=True);a=p.parse_args()
    print(json.dumps(run(a.output,a.boot_id),indent=2))
