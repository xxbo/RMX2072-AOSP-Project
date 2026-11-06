# RMX2072 NQ-NCI / SN100 experimental port

**Status: first AArch64 GKI 6.18 compile-smoke artifact produced. Not KMI-certified or hardware-ready.**

This directory carries a target-focused port of the Qualcomm NQ-NCI driver used by the RMX2072 NFC controller. The immediate goal is to compile the existing driver against the pinned Android 17 ACK/GKI 6.18 headers, identify API/KMI blockers, and then validate the module on a recoverable test device.

## Why this is the first pilot

The official RMX2072 kernel source at commit \`24a15224fbae8ab0e8ba29a9046c06ee7a9f53a4\` contains the target-specific device-tree node in \`arch/arm64/boot/dts/20607/lito-mtp.dtsi\`:

- I2C controller: QUPv3 SE0, configured for 1 MHz
- Device address: \`0x28\`
- Compatible: \`qcom,nq-nci\`
- IRQ GPIO: 34
- VEN GPIO: 12
- FIRM GPIO: 35
- CLKREQ GPIO: 31

The RMX2072 device-tree proprietary manifest at commit \`08afb1d784dd568fa04ca462684a350b37e2bf4a\` also lists \`libnfc-mtp-SN100.conf_20607\` and \`libsn100u_fw.so\`. Together, these are strong target-specific evidence for the SN100/NQ-NCI path. Physical chip revision and the running handset's DTB still need confirmation.

## Source provenance

The initial port is based on the NQ-NCI implementation in:

- Repository: [SM8250-Common/android_kernel_realme_sm8250](https://github.com/SM8250-Common/android_kernel_realme_sm8250)
- Commit: \`b76eb6c93add8152b1aa873da0d8d7f495cccab0\`
- Source: \`drivers/nfc/nq-nci.c\`, \`drivers/nfc/nq-nci.h\`
- License: SPDX \`GPL-2.0-only\`

That source is a newer SM8250 reference, not a proven RMX2072 build. It is selected because its NQ-NCI header explicitly supports SN100_A/SN100_B and its code contains SN100-oriented regulator handling. The target-specific 20607 DTS values are taken from the official RMX2072 4.19.81 tree, not from the shared RMX3371 common-device blob set.

The Qualcomm UAPI \`nfcinfo.h\` definition is retained locally with its original \`GPL-2.0-only WITH Linux-syscall-note\` SPDX identifier.

## First-pass 6.18 adaptations

Only compatibility changes required to reach a first GKI compile are made initially:

1. I2C probe callback changed to the one-argument API used by current kernels.
2. I2C remove callback changed to the current \`void\` return signature.
3. \`class_create()\` changed to the current one-argument API.
4. The vendor \`linux/nfcinfo.h\` header is supplied locally so the old userspace ioctl ABI can be preserved without adding a global kernel header.
5. Legacy GPIO calls are intentionally retained in this first pass to expose whether the pinned GKI build exports the required compatibility symbols. A follow-up should migrate to descriptor-based GPIO APIs if the GKI KMI does not expose the legacy calls.

The existing \`/dev/nq-nci\` character-device name and ioctl numbers are preserved. Do not change them without auditing the matching vendor NFC HAL/library.

## Porting log

See [PORTING_LOG.md](./PORTING_LOG.md) for each GKI compile attempt, environment issue, compiler finding and corrective patch.

## Userspace ABI

See [ABI.md](./ABI.md) for the current character-device, ioctl, power-state, buffer and 32-bit compatibility inventory. The native and compat ioctl paths are not identical in the source; this must be resolved against the target vendor userspace before declaring compatibility.

## Build

The external-module smoke build is driven by:

- \`Makefile\`
- \`../.github/workflows/nfc-nq-gki-618-smoke.yml\`

The workflow checks out the exact Android Common Kernel commit recorded in \`sources/SOURCE_LOCK.json\`, prepares the ARM64 GKI configuration, and compiles this module. The first stage is a source/API compile smoke test; it is **not** a complete GKI KMI/ABI certification because \`modules_prepare\` does not generate the final \`Module.symvers\` for a fully linked GKI image.

## Validation gates

| Gate | Required evidence | Current status |
|---|---|---|
| Source provenance | Immutable source commit and SPDX headers | Recorded |
| Target hardware mapping | 20607 DTS node, I2C address and GPIOs | Source-reviewed; physical capture pending |
| 6.18 compile | \`nq-nci.ko\` produced against pinned GKI headers | Pending CI |
| KMI/export audit | Every imported symbol present in the exact GKI KMI/export set | Not started |
| DT integration | Ported node uses correct I2C controller, GPIOs, pinctrl and IRQ | Not started |
| Module load | \`insmod\`/module loader accepts module with matching vermagic/signature | Not started |
| Probe | I2C device binds and driver reaches successful probe | Not started |
| Userspace ABI | \`/dev/nq-nci\`, power ioctls, read/write, eSE and firmware flow | Not started |
| Functional NFC | NFC discovery, card read, eSE, suspend/resume and cold boot | Not started |

## Safety

Do not enable this driver on a daily-use device until the exact board DT, regulator behavior and recovery route are verified. NFC VEN/FIRM and optional eSE GPIO handling affects power sequencing. Do not flash a kernel or DTBO from this experiment as a test of compile success.
