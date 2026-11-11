# Project overview

RMX2072 targets a project-built ACK 6.18 kernel, an Android 17 ARM64 GSI and a source-built device layer for the Snapdragon 865 board. The release goal is to boot from UFS and operate the hardware independently of realme Android images, closed Android HALs and factory device trees. The [development plan](../plan.md) defines the milestones and how to record dependencies below Android.

The handset has already run the GSI's toybox on 6.18 using a read-only USB-backed image. The next milestone is a headless cold boot from UFS with Android init as PID 1 and a usable ADB shell. Project-built device trees can be validated in parallel. Interactive graphics and touch follow, then daily-use hardware and update/recovery qualification. [Physical GSI record](https://github.com/xxbo/RMX2072-AOSP-Project/blob/f2f6385af354d1c157b319030d5d458134a66acf/build/device/gsi17-usb-mount-2026-11-10.json)

## Evidence labels

- Source-confirmed: visible in a named source repository or official documentation.
- Device-confirmed: captured from the actual handset.
- Build-tested: compiled successfully with recorded toolchain/configuration.
- Boot-tested: booted on physical hardware.
- Hardware-tested: a specific function was exercised and logs retained.

Do not promote claims to a stronger evidence level without reproducible evidence.
