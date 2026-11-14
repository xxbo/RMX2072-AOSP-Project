"""Match the pre-policy source-component witness to this accepted GSI boot."""
import re
from uuid import UUID


def check_m2_boot(text, boot, init_sha256, release):
    UUID(boot)
    rows = re.findall(r'^M2BOOT ([a-z_0-9]+)=(.*)$', text, re.M)
    values = dict(rows)
    if len(rows) != len(values):
        raise ValueError('Duplicate M2 component evidence')
    expected = dict(boot_id=boot, kernel_release=release,
                    base_source='20607-q-24a15224-m2', overlay_source='20607-q-24a15224-m2',
                    first_stage_init_sha256=init_sha256)
    if any(values.get(k) != v for k, v in expected.items()) or not re.fullmatch('[0-9a-f]{64}', values.get('runtime_fdt_sha256', '')):
        raise ValueError('Source DT/init witness does not match the candidate and current boot')
    return values
