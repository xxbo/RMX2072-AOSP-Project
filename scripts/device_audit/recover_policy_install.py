"""Read the previous panic from a fresh M1 diagnostic boot, then request software EDL."""
import argparse
import json
from pathlib import Path
import re
from uuid import UUID

from serve_gsi_usb import console_query, read_console_file, read_until_line, transcript
from usb_edl_return import ACM, END, QUERY, parse_identity


def recover(live):
    from serial import Serial
    from serial.tools.list_ports import comports

    run = json.loads((live/'result.json').read_text())
    trial = run['trial']
    if not re.fullmatch(r'ufs-host-g3-gsi17-firststage-vendor-load-\d+', trial):
        raise ValueError('Unexpected trial')
    original = UUID(re.search(r'^M1EVENT boot_id=([\w-]+)$', (live/'policy-events.txt').read_text(), re.M)[1])
    ports = [port for port in comports() if (port.vid, port.pid) == ACM]
    if len(ports) != 1:
        raise ValueError('Expected one diagnostic ACM')
    with Serial(ports[0].device, 115200, timeout=.25, write_timeout=4) as console:
        console.write(QUERY)
        ident = parse_identity(read_until_line(console, END, 12))
        if ident['trial'] != trial or ident['kernel'] != run['identity']['kernel']:
            raise ValueError('Wrong diagnostic image')
        console.write(b"\nprintf '\\nREC_''BEGIN\\n'; cat /proc/sys/kernel/random/boot_id; printf '\\nREC_''END\\n'\n")
        rows = read_until_line(console, b'REC_END', 8).replace(b'\r', b'').splitlines()
        fresh = UUID(rows[rows.index(b'REC_BEGIN')+1].decode())
        if fresh == original:
            raise ValueError('Original policy trial is still running')
        with (live/'intermediate-boot.json').open('x', encoding='utf-8') as out:
            json.dump(dict(boot_id=str(fresh), identity=ident), out)
        try:
            console.write(b"mkdir -p /run/prev; mount -t pstore pstore /run/prev; "
                          b"{ ls -l /run/prev; for p in /run/prev/*; do echo FILE=$p; "
                          b"grep -aE 'M1EVENT|init:|enforcing|reboot:|panic|avc:|sys.boot_completed|BOOT_ID|boot_id|second.stage' "
                          b"\"$p\" | tail -180; done; } >/run/gsi17-run.log; printf '\\nREC_''SAVED\\n'\n")
            read_until_line(console, b'REC_SAVED', 8)
            for name in ('console-ramoops-0', 'dmesg-ramoops-0.enc.z', 'dmesg-ramoops-0', 'pmsg-ramoops-0'):
                path = b'/run/prev/'+name.encode()
                if console_query(console, b'test -s '+path+b' && echo present') == b'present':
                    (live/name).write_bytes(read_console_file(console, path))
            with (live/'intermediate-pstore.txt').open('x', encoding='utf-8') as out:
                out.write(transcript(console))
        finally:
            console.write(b'/bin/reboot-edl edl\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', required=True, type=Path)
    recover(parser.parse_args().live)
