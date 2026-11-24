"""Verify additive Turnip and retained peripheral firmware for native Adreno."""
import hashlib
import json
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parents[2]


def acceleration_policy(cil):
    # Hardware shader compilation does not execute JIT code on the CPU.
    for client in (b'surfaceflinger', b'bootanim'):
        statement = b'(allow '+client+b' self (process (execmem)))\n'
        if cil.count(statement) != 1:
            raise ValueError('Expected exactly the reviewed SwiftShader exception')
        cil = cil.replace(statement, b'')
    return cil + (ROOT/'device/realme/bladerunner_48m/m3-vendor/acceleration.cil').read_bytes().replace(b'\r\n', b'\n')


def gpu_firmware(directory):
    proof = json.loads((ROOT/'build/m3-gpu-firmware-source.json').read_text())
    if json.loads((directory/'provenance.json').read_text()) != proof:
        raise ValueError('GPU firmware provenance changed')
    files = {}
    for name, entry in proof['files'].items():
        if '..' in Path(name).parts or not name.startswith('qcom/'):
            raise ValueError('Unexpected GPU firmware path')
        data = (directory/name).read_bytes()
        if len(data) != entry['bytes'] or hashlib.sha256(data).hexdigest() != entry['sha256']:
            raise ValueError('GPU firmware digest mismatch: ' + name)
        files[name] = data
    # adreno_fw_create_bo() skips the first firmware dword. ACK checks the
    # low twelve bits of the first uploaded SQE word, requiring >= 0x095.
    version = struct.unpack_from('<I', files['qcom/a650_sqe.fw'], 4)[0] & 0xfff
    if version < 0x095 or version != proof['files']['qcom/a650_sqe.fw']['version_low_12_bits']:
        raise ValueError('A650 SQE firmware is below the native driver requirement')
    return files, proof


def add_acceleration(files, current):
    directory = current/'turnip'
    proof = json.loads((directory/'provenance.json').read_text())
    pin = json.loads((ROOT/'build/m3-turnip-source.json').read_text())
    if not proof.get('source_verified') or not proof.get('archive_digest_verified') or proof.get('source') != pin:
        raise ValueError('Turnip must come from the verified pinned source build')
    key = '/lib64/hw/vulkan.freedreno.so'
    data = (directory/'vendor'/key.lstrip('/')).read_bytes()
    if proof['files'] != {key: hashlib.sha256(data).hexdigest()} or data[:6] != b'\x7fELF\x02\x01' or data[18:20] != b'\xb7\x00':
        raise ValueError('Unexpected Turnip payload')
    if key in files:
        raise ValueError('Turnip payload must be additive')
    files[key] = data
    firmware, firmware_proof = gpu_firmware(current/'gpu-firmware')
    for name, data in firmware.items():
        files['/firmware/'+name] = data
    files['/etc/selinux/vendor_file_contexts'] += (
        b'/dev/dri u:object_r:gpu_device:s0\n'
        b'/vendor/lib64/hw/vulkan\\.freedreno\\.so u:object_r:same_process_hal_file:s0\n'
        b'/vendor/firmware(/.*)? u:object_r:rmx_gpu_firmware_file:s0\n')
    files['/etc/selinux/vendor_sepolicy.cil'] = acceleration_policy(files['/etc/selinux/vendor_sepolicy.cil'])
    return dict(turnip=proof, retained_gpu_firmware=firmware_proof)
