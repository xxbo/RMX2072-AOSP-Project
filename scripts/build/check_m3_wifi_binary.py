"""Reject the observed SVE register forms in the baseline supplicant ELF.

This complements pinned ARMv8-A build settings; it is not a general proof of
every instruction's reachability. The device must still pass startup and RF.
"""
import hashlib
from pathlib import Path
import re
import struct
import subprocess
import tempfile


def sve_register_instructions(disassembly):
    found = []
    for line in disassembly.splitlines():
        match = re.match(r'^\s*[0-9a-f]+:\s+[0-9a-f]{8}\s+(.+)$', line, re.I)
        if not match:
            continue
        instruction = re.sub(r'<[^>]*>', '', match.group(1)).split('//')[0]
        if re.search(r'\b(?:z\d+\.[bhsdq]|p\d+(?:\.[bhsd]|/[zm]))\b', instruction):
            found.append(line.strip())
    return found


def check_binary(data, objdump, scratch):
    if len(data) < 64 or data[:6] != b'\x7fELF\x02\x01' or struct.unpack_from('<H', data, 18)[0] != 183:
        raise ValueError('Supplicant must be a real little-endian ARM64 ELF')
    with tempfile.TemporaryDirectory(prefix='wifi-isa-', dir=scratch) as directory:
        path = Path(directory)/'wpa_supplicant'
        path.write_bytes(data)
        assembly = subprocess.check_output([str(objdump), '-d', str(path)], text=True)
        assembly = assembly.replace(str(path), 'wpa_supplicant')
    if not re.search(r'^\s*[0-9a-f]+:\s+[0-9a-f]{8}\s+', assembly, re.M):
        raise ValueError('No AArch64 instructions decoded')
    unsupported = sve_register_instructions(assembly)
    if unsupported:
        raise ValueError('Unexpected SVE register instructions in baseline supplicant: ' + repr(unsupported[:8]))
    return dict(sha256=hashlib.sha256(data).hexdigest(), machine='AArch64',
                sve_register_instruction_count=0,
                disassembly_sha256=hashlib.sha256(assembly.encode()).hexdigest(),
                scope='SVE register operand screen plus pinned ARMv8-A build; device startup/RF pending')
