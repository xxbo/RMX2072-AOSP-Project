# Project overview

RMX2072 targets a project-built ACK 6.18 kernel, an Android 17 ARM64 GSI and a source-built device layer for the Snapdragon 865 board. The release goal is to boot from UFS and operate the hardware independently of realme Android images, closed Android HALs and factory device trees. The [development plan](../plan.md) defines the milestones and how to record dependencies below Android.

On 6.18.32, first-stage init ran as PID 1 and mounted the USB-backed Android 17 GSI and RAM-backed project vendor. The observer reached `selinux_setup`. Trial 02 passed a separate strict compile and stopped before kernel policy installation. The [November 12 replay](../build/device/gsi17-policy-install-2026-11-12.json) observed the policy write, enforcing transition and a PID 1 SIGBUS. M1 still requires second-stage init and a disconnected UFS cold boot with same-boot ADB. M2 board-tree and ramdisk work can proceed in parallel. [Handset record](https://github.com/xxbo/RMX2072-AOSP-Project/blob/da4385b38212ea8f84307f672a741da77172ecc5/build/device/gsi17-project-vendor-2026-11-11.json) · [Milestone acceptance](../plan.md#milestones-and-acceptance)

## Evidence labels

- Source-confirmed: visible in a named source repository or official documentation.
- Device-confirmed: captured from the actual handset.
- Build-tested: compiled successfully with recorded toolchain/configuration.
- Boot-tested: booted on physical hardware.
- Hardware-tested: a specific function was exercised and logs retained.

Do not promote claims to a stronger evidence level without reproducible evidence.
