# Project overview

RMX2072 targets a project-built ACK 6.18 kernel, an Android 17 ARM64 GSI and a source-built device layer for the Snapdragon 865 board. Reuse suitable upstream drivers and port the RMX2072-specific parts to 6.18. The release must operate independently of realme Android partitions, extracted HALs and factory device trees. Build the board trees, ramdisk, vendor and HALs from source and record each remaining boot-chain or peripheral firmware dependency. [Development plan](../plan.md#target-system)

On November 12 the phone ran Android 17 second-stage init as PID 1 under enforcing on 6.18.32. The GSI used original data from RAM with USB fallback, and the project vendor ran from RAM. When the fallback reader exited, init reported I/O errors reading properties and startup configuration. M1 requires verified UFS-backed system and vendor mounts, a disconnected cold boot and Android ADB on that boot. [Trial 05](https://github.com/xxbo/RMX2072-AOSP-Project/blob/19d77ebfd3b5c5eed24c49c4494043a9203a12b7/build/device/gsi17-enforcing-second-stage-2026-11-12.json) · [M1 acceptance](../plan.md#milestones-and-acceptance)

## Evidence labels

- Source-confirmed: visible in a named source repository or official documentation.
- Device-confirmed: captured from the actual handset.
- Build-tested: compiled successfully with recorded toolchain/configuration.
- Boot-tested: booted on physical hardware.
- Hardware-tested: a specific function was exercised and logs retained.

Do not promote claims to a stronger evidence level without reproducible evidence.
