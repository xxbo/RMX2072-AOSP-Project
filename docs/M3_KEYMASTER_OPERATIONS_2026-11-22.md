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
`libqtikeymaster4.so` (151080 bytes,
`8fb4d8c7ad198c49379400ff52beb6fe6f1482ca53220b27192e4faacb4311d1`)
and `libQSEEComAPI.so` (40816 bytes,
`f5274283690c77730166d928ba55507d171e8c6f40af6195ce2500f43423e27c`)
were extracted for private offline protocol inspection. Both match the previous
F.20 trace pins. The running GSI's `fsck.erofs --path` performed the extraction;
the temporary filesystem copy and extracted device files were removed after
pulling and verifying the libraries. Two helpers were subsequently extracted
from the same retained filesystem: `libkeymasterdeviceutils.so` (19832 bytes,
`e7b223728a88d76eec8b615eb4c1a1e9eb857bd4b20f9a5f762a5a60766f0603`)
and `libkeymasterutils.so` (51848 bytes,
`8d92872bfe7aead75eecece9206dae52ec2087d6e669ac7f7d2136831def78ba`).
Their temporary device copies were also removed. Original phone partitions were
not read.

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
32-bit offset/length pair for a byte string. Indirect byte-string offsets are
relative to the parameter block, not the overall request: confirmed from
`KeymasterBuffer::get_indirect_buf_offset_from_main` in the helper library.
The response starts immediately
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
access is restricted to the source HAL domain, including the exact ioctl number.

## Source HAL and validation before trial 75

The source HAL now serializes configure, RAW AES/HMAC import, AES/HMAC generation,
shared HMAC, begin/update/finish/abort and deletion of a supplied wrapped blob.
The configuration is gated to the actual GSI OS/patch and project vendor patch
properties. Returned characteristics are decoded from the successful TEE-created
v4 blob; request parameters are never echoed as hardware-enforced attributes.
Unknown versions, inconsistent counts and invalid offsets fail closed. If a
created blob has unsupported metadata, cleanup deletes exactly that returned blob.

The current operation scope is no-auth AES/HMAC. Real authentication and
verification tokens, RSA/EC operations, upgrade/attestation and characteristic
queries remain unsupported. This is not a complete Keymaster implementation or
an acceptance of a secure PIN flow. Default empty tokens may carry a zero-filled
32-byte MAC through the compatibility layer; nonzero tokens are rejected.

Validation completed before booting the candidate:

- NDK source service/client build and private VNDK dependency/RUNPATH checks passed.
  Exact binary and source hashes are in
  `build/device/m3-keymaster-runtime-2026-11-22.json`.
- The static `wire-test.cpp` executed on the existing trial 74 GSI. Relative
  indirect offsets, bounded requests/replies, authorization metadata, truncation,
  overflow and count rejection passed. It performs no TEE call.
- Strict GSI SELinux compilation, with neverallow checks, passed for the exact
  composed vendor policy. Proof: `build/device/m3-keymaster-policy-2026-11-22.json`.
  That compilation did not load policy or alter the running phone.
- The kernel diff from accepted display source `c8ce89da` to `9241fa08` changes
  only the three Keymaster probe/transport files. Candidate preflight also checks
  unchanged display source hashes, kernel configuration, DT outputs, GSI, seeds,
  graphics/USB guard and existing health/power/audio payloads.

The client `--aes-selftest` uses a fresh random temporary AES key, imports it,
encrypts through update/finish, decrypts and compares all plaintext bytes, requires
a modified GCM tag to fail with no output, then deletes the returned blob. It
does not log key bytes, blobs or payloads. This test still requires the new kernel
and HAL on the handset; a codec/build pass does not imply a TEE transaction pass.

Status: candidate preparation in progress. No new image has been booted and no
LockSettings/Launcher success is claimed.
