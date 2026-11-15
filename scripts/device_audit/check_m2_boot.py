"""Match the pre-policy source-component witness to this accepted GSI boot."""
import re
from uuid import UUID


def check_m2_boot(text, boot, init_sha256, release, boot_events):
    UUID(boot)
    rows = re.findall(r'^M2BOOT ([a-z_0-9]+)=(.*)$', text, re.M)
    values = dict(rows)
    if len(rows) != len(values):
        raise ValueError('Duplicate M2 component evidence')
    expected = dict(boot_id=boot, kernel_release=release,
                    base_source='20607-q-24a15224-m2', overlay_source='20607-q-24a15224-m2',
                    first_stage_init_sha256=init_sha256, board_id_hex='0000507f')
    if any(values.get(k) != v for k, v in expected.items()) or not re.fullmatch('[0-9a-f]{64}', values.get('runtime_fdt_sha256', '')):
        raise ValueError('Source DT/init witness does not match the candidate and current boot')
    if values.get('root_compatible', '').split() != ['qcom,kona-mtp', 'qcom,kona', 'qcom,mtp']:
        raise ValueError('Runtime tree does not identify the board for SCM/PON guards')
    disks = re.findall(r'^M1EVENT disk=(\S+) ro=(\S+)$', boot_events, re.M)
    if (set(re.findall(r'^M1EVENT boot_id=(.*)$', boot_events, re.M)) != {boot}
            or sorted(disks) != [(name, '1') for name in ('sda', 'sdb', 'sdc', 'sdd', 'sde', 'sdf')]):
        raise ValueError('Six read-only UFS LUNs are not proven on this boot')
    return dict(values, read_only_ufs_luns=[name for name, _ in sorted(disks)])
