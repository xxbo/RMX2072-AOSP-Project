# Android 17 GSI bring-up guide

The selected system image is Google Android 17 QPR1 ARM64 + GMS, CP3A.260905.010. The project supplies the ACK 6.18 kernel and RMX2072 vendor implementation. Record the external image's build ID and SHA-256 from [the GSI lock](../build/gsi.json) alongside the hashes of the board artifacts used for each boot.

## Headless boot sequence

1. Use the known-working 6.18 kernel, USB diagnostic path and UFS profile as the control. The [USB-backed Android 17 test](https://github.com/xxbo/RMX2072-AOSP-Project/blob/f2f6385af354d1c157b319030d5d458134a66acf/build/device/gsi17-usb-mount-2026-11-10.json) supplies a reproducible userspace comparison.
2. Prepare the boot-v2 ramdisk and project vendor with first-stage fstab, init rules, VINTF declarations and SELinux policy. Identify the signing key and verification path for each target image. Capture the handoff to Android init and its first mount result.
3. Select an internal UFS layout from measured image sizes and document recovery for the partitions it changes. Preserving every current F.20 logical partition leaves a 1,095,585,792-byte deficit for the selected GSI. See the [partition preflight](GSI_PREFLIGHT_2026-11-06.md).
4. Cold-boot with the USB image server disconnected, then connect ADB and collect the same-boot identity, mount sources and Android init logs specified in the [M1 acceptance criteria](../plan.md#milestones-and-acceptance).

The F.20 vendor comparison remains available for isolating compatibility issues. A project-built generic system image is an optional comparison with the pinned prebuilt GSI. Board drivers and Android hardware services belong in the kernel and device vendor implementation.
