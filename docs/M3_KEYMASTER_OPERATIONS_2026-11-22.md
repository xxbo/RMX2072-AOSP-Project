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

The shared `aesSelftest` uses a fresh random temporary AES key, imports it,
encrypts through update/finish, decrypts and compares all plaintext bytes, requires
a modified GCM tag to fail with no output, then deletes the returned blob. It
does not log key bytes, blobs or payloads. This test still requires the new kernel
and HAL on the handset; a codec/build pass does not imply a TEE transaction pass.
The user GSI correctly denies shell access to the private vendor client/runtime.
For this candidate, init sets `RMX_KEYMASTER_AES_SELFTEST=1`: the service runs the
same bounded test through its HAL methods once before HIDL registration, and
logs statuses to `RMXKeymasterTest`. This tests the HAL-to-kernel-to-TEE path;
framework HIDL calls after registration are separate evidence. No shell policy
is relaxed. `check_m3_keymaster.py` only collects these logs on the matched boot.

Status: candidate preparation in progress. No new image has been booted and no
LockSettings/Launcher success is claimed.

## Trial 75: property read denial, restored F.20

The source kernel build
[45029228400](https://github.com/xxbo/RMX2072-AOSP-Project/actions/runs/45029228400)
succeeded. All 36 candidate checks passed; only Keymaster kernel sources changed.
Boot/DTBO and all 17 candidate super chunks passed readback. The GSI boot UUID was
`727f70a2-ac05-44f0-8a1e-5e3d393fe45b`.

Saved ramoops identifies an exact failure before new TEE transactions: the
`rmx_keymaster` domain was denied reading `vendor_security_patch_level_prop`.
The existing TEE version query still returned transport/status success. The new
configure guard then saw an unavailable vendor property and exited with status 1.
Repeated lazy starts could not register the HAL, `android.security.maintenance`
remained unavailable, and GSI ADB never appeared. AES self-test, import, framework
progress and Launcher were **not reached**, not failed cryptographic tests.

The user observed restarting/realme. The guard's previous-boot marker says
`expired`; ramoops records APSS watchdog pretimeout. The host caught recovery
boot `6eeda310-725d-414f-8e8b-ec27959715d0` and requested EDL without manual keys.
F.20 was restored from the existing one-copy recovery set, with write ACKs,
boot completion and both LP metadata slots verified. No full stock partition
readback was performed. Exact result and evidence hashes:
[trial 75](../build/device/m3-keymaster75-result-2026-11-22.json).

Trial 76 adds only read/getattr/open/map for that property to the HAL domain.
The diagnostic random-key allocation also uses nonblocking `getrandom`: a lack
of Linux entropy must fail the test instead of holding HAL registration. The
property check now logs a mismatch explicitly. Kernel, display, GSI and seeds
stay the same. The complete new policy passed strict compilation with the
pinned GSI's own compiler, linker and Bionic files, executed as a temporary tool
on restored F.20. Policy was not loaded and enforcing stayed enabled.
[policy proof](../build/device/m3-keymaster76-policy-2026-11-22.json).

Current target: actual TEE import and temporary AES-GCM acceptance, followed by
LockSettings and Launcher. No desktop acceptance yet.

## Trial 76: real import and framework boot, desktop blocked

Boot `f45b52da-66fc-4b1b-98de-b78df636a718` passed candidate readback,
enforcing/API 37 ADB retention and GSI `sys.boot_completed=1`. Configure,
HMAC sharing parameters, shared-HMAC negotiation, HAL/maintenance registration
and the earlyBootEnded RPC succeeded. The boot-level HMAC key operation still
returned -49; an RPC success is not complete keystore acceptance.

The startup AES self-test failed at import (-49), before HIDL registration.
Later, the actual framework import rejected rollback resistance (-67), then
accepted the framework's ordinary import and returned a 455-byte TEE blob.
LockSettings logged successful synthetic-password initialization for user 0.
This proves import progress, not AES roundtrip, tamper rejection or PIN support.
The first-ADB log preserved these results; later filtered logcat was empty
because rapid graphics crashes wrapped the ring.

SystemUI, Launcher and SetupWizard then failed mapper initialization and buffer
import, culminating in HWUI `drawRenderNode called on a context with no surface!`.
Both DRM nodes are 0660 system:graphics; application UIDs lack that group.
Pinned minigbm `ce79bbee67b3e2ea7abb110e1415e9ceceaa6471` opens render nodes
O_RDWR before falling back to primary nodes. Trial 77 changes only render-node
DAC to 0666, retaining primary 0660 and gpu_device enforcing policy. It keeps
the kernel, display timing/PPS, graphics binaries, HALs, GSI and test seeds.

A separate later failure must not be hidden by boot completion: system_server
PID 2361 faulted executing `[anon:swiftshader_jit]` after an execmem denial in
the PowerManager screen-transition path. Framework restarted to PID 13191
without a kernel reboot. The GSI platform explicitly forbids system_server
execmem. No policy exception is added. USB stay-awake was temporarily enabled
(previous setting 0) to collect the mapper isolation without that sleep path.
A source resource configuration for the CPU-rendering screen transition is a
follow-up; neither unrestricted JIT policy nor Adreno readiness is claimed.

[Result and evidence hashes](../build/device/m3-keymaster76-result-2026-11-22.json).
Current target: let application windows allocate and render, then verify the
physical Launcher. The phone remains on GSI with authenticated ADB.
