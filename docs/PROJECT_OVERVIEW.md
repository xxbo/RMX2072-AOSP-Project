# Project Overview

## Mission
Maintain an independent AOSP platform for the realme X50 Pro Player Edition (RMX2072 / bladerunner_48m), powered by Snapdragon 865 / SM8250. The active milestone is a stable 6.18 RAM-only diagnostic environment. Android 17 vendor/system integration follows its own preflight and compatibility gates.

## Scope
- Device identification and stock-firmware preservation
- AOSP/GSI build and boot validation
- Device-tree and vendor compatibility
- Kernel source inventory and migration research
- Hardware validation and recovery procedures

## Milestones
The [development plan](../plan.md) tracks M0–M8. The team has captured the F.20 baseline (M0), built the community 4.19 kernel (M1/M6), and inspected the official GSI (M2). The active M7 prototype now supports a verified 6.18 host ACM shell with primary USB SID0. Sustained transfer testing is in progress; display, UFS and Android userspace remain separate gates. See the [bring-up journal](INDEPENDENT_KERNEL_BRINGUP.md).

## Evidence labels
- Source-confirmed: visible in a named source repository or official documentation.
- Device-confirmed: captured from the actual handset.
- Build-tested: compiled successfully with recorded toolchain/configuration.
- Boot-tested: booted on physical hardware.
- Hardware-tested: a specific function was exercised and logs retained.

Do not promote claims to a stronger evidence level without reproducible evidence.
