#!/usr/bin/env python3
"""Record selected settings from a built kernel config; never accesses a device."""
import argparse
import hashlib
import json
import pathlib

KEYS = '''HWSPINLOCK HWSPINLOCK_QCOM QCOM_SMEM QCOM_SCM QCOM_LLCC
WATCHDOG WATCHDOG_HANDLE_BOOT_ENABLED WATCHDOG_OPEN_TIMEOUT QCOM_WDT
DEVTMPFS SCSI_UFS_QCOM PHY_QCOM_QMP_UFS QCOM_INLINE_CRYPTO_ENGINE
USB_DWC3_QCOM USB_CONFIGFS_ACM DRM_MSM DMABUF_HEAPS
DMABUF_HEAPS_SYSTEM DMABUF_HEAPS_CMA ANDROID_BINDER_IPC ANDROID_BINDERFS
DM_DEFAULT_KEY DM_VERITY FS_ENCRYPTION QCOM_Q6V5_ADSP QCOM_Q6V5_MSS
QCOM_Q6V5_PAS'''.split()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True, type=pathlib.Path)
    parser.add_argument('--output', required=True, type=pathlib.Path)
    args = parser.parse_args()
    raw = args.config.read_bytes()
    lines = raw.decode().splitlines()
    values = {}
    for key in KEYS:
        name = 'CONFIG_' + key
        assignment = next((line for line in lines if line.startswith(name + '=')), None)
        values[name] = (assignment.split('=', 1)[1] if assignment else
                        'n' if '# ' + name + ' is not set' in lines else 'absent')
    report = dict(scope='Selected compiled configuration values, not a boot-failure diagnosis',
                  config_sha256=hashlib.sha256(raw).hexdigest(), configuration=values)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
