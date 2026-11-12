# Rust Driver Porting Strategy — RMX2072 / Android 17 GKI 6.18

## Decision

Rust is the preferred language for newly written RMX2072 drivers, provided the required subsystem APIs are available in the pinned Android Common Kernel source. Existing C drivers remain reference implementations for hardware sequencing, userspace ABI and vendor behavior; they are not to be mechanically translated line by line.

The pinned 6.18 ARM64 distribution has built with its official Kleaf toolchain. The manifest syncs the matching Rust toolchain, and the generic arm64 defconfig has CONFIG_RUST=y. The Rust NFC prototype belongs to the peripheral workstream. M1–M3 can use working upstream drivers in their existing language. [Handset milestones](../plan.md#milestones-and-acceptance)

## Important maturity qualification

Linux Rust support was merged in v6.1, but the kernel's Rust documentation still describes the subsystem as an evolving development effort. A kernel version having CONFIG_RUST=y does not mean every C driver API has a Rust equivalent, nor does it guarantee that a particular Rust driver is production-ready.

For every driver, inspect the exact pinned source tree under common/rust/kernel/ and its Kconfig/build integration. Do not infer availability from the latest rust.docs.kernel.org pages alone.

## Rust subsystem API outlook

The Android Common Kernel source line has Rust abstractions for I2C driver registration, regulator state management and miscdevice registration/file operations in its Rust kernel crate. These are promising building blocks for NQ-NCI: I2C transport, optional regulator control and the existing /dev/nq-nci userspace endpoint may be implementable mostly in Rust.

The exact pinned release tag remains the authority. For the Rust prototype, archive an inventory of the modules exported by common/rust/kernel/lib.rs and the corresponding source files before the Rust driver skeleton is written. In particular, GPIO consumer access and the required IRQ/wakeup model need an exact-source check; a small C shim may be the safest initial bridge for GPIO lines and IRQ plumbing.

## Expected architecture

- Rust owns the driver state machine, device state, data parsing, sequencing policy, retry policy and resource lifetime wherever safe kernel abstractions exist.
- Use kernel Rust abstractions (rather than raw FFI) for supported buses, locks, allocation and resource types.
- Keep any C compatibility layer narrow and explicit. It should expose only missing kernel operations, not duplicate the driver's state machine.
- Document every unsafe block with its safety invariant.
- Preserve device-tree bindings and the existing userspace ABI unless a separate migration is planned and validated.

Rust improves memory-safety guarantees for safe code, especially around ownership, lifetime, use-after-free, double-free and data-race classes. It does not prevent logical bugs, deadlocks, leaks, allocation failures, incorrect DMA mappings or hardware-sequencing errors. Unsafe code and C FFI boundaries still require review.

## First Rust validation ladder

1. Full GKI 6.18 ARM64 build using the official Kleaf distribution target.
2. Confirm CONFIG_RUST=y and that the pinned Rust compiler is used by the kernel build.
3. Build a minimal Rust kernel module/sample against this exact source/toolchain.
4. Build a Rust I2C driver skeleton with an OF match entry for qcom,nq-nci. The first version only probes and reports device identity; it does not change NFC power or transfer data.
5. Verify module metadata, symbol imports, KMI requirements and module packaging.
6. Add one hardware operation at a time: I2C read/write, then GPIO/power, IRQ, state machine and userspace interface.
7. Only after static and compile tests pass, proceed to module load, probe and physical NFC tests.

## NQ-NCI / SN100 porting inventory

The current C reference is under experiments/nfc_nq/ on branch experiment/nq-nci-gki-6.18. It is a behavioral reference, not the intended final implementation.

| Area | Existing C behavior | Rust plan / current risk |
|---|---|---|
| I2C registration and transfer | I2C client at address 0x28; byte transport | Prefer the kernel Rust I2C driver abstraction if present in the exact pinned 6.18 source; verify transfer methods and adapter support |
| Device-tree matching | qcom,nq-nci | Use the Rust OF device-ID table if supported by the pinned tree |
| GPIO | VEN 12, IRQ 34, FIRM 35, CLKREQ 31 | Highest API gap to verify; if no suitable GPIO consumer abstraction exists, add a small audited C shim or implement/review a narrow Rust abstraction |
| IRQ and wake | Data-ready IRQ, wakeup handling, suspend/resume | Verify request/threaded IRQ and wake support; keep hard-IRQ work minimal |
| Regulator | Optional SN100 VDDIO handling | Check the exact 6.18 Rust regulator API and target DT properties; do not invent a rail |
| Character device | /dev/nq-nci | Preserve node, permissions and ABI; a small C registration shim may be appropriate if the Rust character-device abstraction is insufficient |
| ioctl ABI | NFC/eSE power and chip-info commands | Preserve magic, command numbers, direction bits, argument sizes and return semantics |
| Read/write | Blocking/nonblocking reads, I2C writes, retries | Rust-owned buffers and state; carefully preserve short-transfer and -EAGAIN behavior |
| Power/state machine | VEN/FIRM toggling, reset, firmware download, eSE | Rebuild as an explicit Rust state machine; keep timing and sequencing grounded in the original driver and board DTS |
| Cleanup | GPIO, IRQ, regulator, char device and notifier teardown | Prefer RAII/devres and pinned driver data; test every partial-probe failure path |

## Migration sizing

These are planning estimates, not measured commitments:

- Minimal Rust module and toolchain proof: small.
- I2C probe-only skeleton: small to medium.
- Simple I2C sensor driver with existing Rust abstractions: medium.
- NQ-NCI full port preserving GPIO/IRQ/power/char-device/ioctl behavior: medium to large because the hardware state machine and userspace ABI are substantial.
- Display, KGSL, Camera, audio and power-management stacks: large to very large; retain C where the subsystem is deeply coupled to vendor frameworks or lacks suitable Rust abstractions.

The first NQ-NCI implementation should not attempt to remove all C in one step. A safe, small compatibility boundary is preferable to reimplementing undocumented kernel internals.

## Acceptance criteria

- Exact GKI source and toolchain are pinned and recorded.
- Rust module compiles with the kernel's own Rust toolchain and build system.
- No unresolved or unapproved imported symbols.
- No ABI drift in device-tree matching or userspace interfaces.
- Probe failure and device removal release every acquired resource.
- Runtime tests cover power cycles, suspend/resume, IRQ storms, short I2C transfers, nonblocking reads and repeated bind/unbind.
- Physical-device validation occurs on a recoverable test setup before any daily-use device is exposed to the driver.
