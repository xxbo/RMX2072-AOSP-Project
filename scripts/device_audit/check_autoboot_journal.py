"""Exercise the actual static journal parser on Android using disposable files."""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import tempfile


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--serial', required=True)
    p.add_argument('--witness', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    base = '/data/local/tmp/rmx-m1-journal-check'
    adb = ['adb', '-s', a.serial]
    def shell(command):
        return subprocess.run(adb+['shell', command], capture_output=True, text=True, timeout=15)
    shell('mkdir '+base).check_returncode()
    subprocess.run(adb+['push',str(a.witness),base+'/witness'],check=True,capture_output=True)
    shell('chmod 755 '+base+'/witness').check_returncode()
    boot = b'36f78fb1-b358-4aac-996e-a65775b23da6'
    marker = b'RMX-M1-AUTO boot='+boot+b' state='
    retained = marker+b'retained\n'
    cases = [
        ('empty', b'', 0, 'none'),
        ('binary-without-marker', bytes(range(256))*8, 0, 'none'),
        ('binary-retained', bytes(range(256))+retained+b'\x00\xff\x00', 0, retained.decode().strip()),
        ('expired-after-retained', retained+b'\x00'+marker+b'expired\n', 0, (marker+b'expired').decode()),
        ('torn-after-retained', retained+marker+b'retain', 1, ''),
        ('damaged-uuid-after-retained', retained+(marker+b'armed\n').replace(boot, b'x'+boot[1:]), 1, ''),
        ('later-complete-marker', marker+b'torn\x00'+retained, 0, retained.decode().strip()),
        ('oversized', b'\x00'*(2*1024*1024+4097), 1, ''),
    ]
    rows = []
    try:
        with tempfile.TemporaryDirectory() as directory:
            for name,data,code,expected in cases:
                fixture=Path(directory)/'fixture'; fixture.write_bytes(data)
                subprocess.run(adb+['push',str(fixture),base+'/fixture'],check=True,capture_output=True)
                r=shell(base+'/witness autoboot-state '+base+'/fixture')
                row=dict(case=name,sha256=hashlib.sha256(data).hexdigest(),returncode=r.returncode,stdout=r.stdout.strip(),stderr=r.stderr.strip())
                rows.append(row)
                assert r.returncode==code and r.stdout.strip()==expected, row
        r=shell(base+'/witness autoboot-state '+base+'/missing')
        assert r.returncode==0 and r.stdout.strip()=='none'
        rows.append(dict(case='absent-after-cold-power-loss',returncode=0,stdout='none'))
    finally:
        shell('rm -f '+shlex.quote(base+'/fixture')+' '+shlex.quote(base+'/witness')+'; rmdir '+shlex.quote(base)).check_returncode()
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(dict(witness_sha256=hashlib.sha256(a.witness.read_bytes()).hexdigest(),cases=rows),indent=2)+'\n')
    print(f'{len(rows)} on-device journal parser cases passed')


if __name__ == '__main__':
    main()
