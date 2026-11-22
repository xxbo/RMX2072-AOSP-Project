# M3 Keymaster operations

Target: complete the TEE-backed key import and AES-GCM operations needed by
LockSettings, then observe Launcher. Trial 74's unchanged 6.18/GSI boot stops in
`SyntheticPasswordCrypto.createBlob` because the project HAL's `importKey`
returns `UNIMPLEMENTED`. Audio service entry and heap configuration passed in
that trial; framework boot completion and a desktop did not.

The accepted trial 69 display source/configuration, GSI and scratch volume seeds
remain the baseline. No cold-start test or routine original-partition readback
is part of this work.

## Protocol evidence

The retained original F.20 recovery chunks contain an EROFS vendor filesystem.
Only `libqtikeymaster4.so` (151080 bytes,
`8fb4d8c7ad198c49379400ff52beb6fe6f1482ca53220b27192e4faacb4311d1`)
and `libQSEEComAPI.so` (40816 bytes,
`f5274283690c77730166d928ba55507d171e8c6f40af6195ce2500f43423e27c`)
were extracted for private offline protocol inspection. Both match the previous
F.20 trace pins. The running GSI's `fsck.erofs --path` performed the extraction;
the temporary filesystem copy and extracted device files were removed after
pulling and verifying the two libraries. Original phone partitions were not read.

Observed legacy request layouts in that exact client, little-endian:

| Method | ID | Fixed header bytes | Client function address |
| --- | --- | ---: | --- |
| generate | 0x108 | 12 | 0x14264 (delegates to generate_key_common) |
| import | 0x10b | 24 | 0x14748 |
| delete returned key | 0x10d | 12 | 0x16bfc |
| begin | 0x10f | 24 | 0x15a20 |
| update | 0x111 | 28 | 0x15e74 |
| finish | 0x112 | 36 | 0x1621c |
| abort | 0x113 | 12 | 0x16950 |
| configure | 0x116 | 12 | 0x14074 |
| compute shared HMAC | 0x20f | 12 | 0x178ec |

Parameter entries are 12 bytes: a 32-bit tag followed by an 8-byte scalar or a
32-bit offset/length pair for a byte string. The response starts immediately
after the variable-length request in the same 40960-byte allocation. Update
and finish additionally initialize the response's output offset/capacity at
bytes 8/12 before the call (20-byte and 16-byte response headers respectively).
These client-side observations are not yet a physical acceptance of new methods.

## Candidate transport

The new board-private `/dev/rmx2072_keymaster` ioctl copies bounded userspace
bytes into the existing QSEE shared-memory allocator, resolves `keymaster64`
itself, and uses the previously accepted whitelist SCM call and TIME listener.
Only the method IDs above are admitted. It does not expose physical addresses,
app loading, listener replies, provisioning, delete-all or boot-state overrides.
Requests and replies are wiped after terminal completion. Unknown callbacks or
uncertain listener ownership block further calls until reboot and retain memory
that secure world may still reference. The device is mode 0600; vendor SELinux
access remains to be integrated with the source HAL.

Status: implementation in progress; no new image has been booted and no
LockSettings/Launcher success is claimed.
