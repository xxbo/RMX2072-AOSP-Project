# Android 17 GSI bring-up guide

The selected system image is Google Android 17 QPR1 ARM64 + GMS, CP3A.260905.010. The project supplies the ACK 6.18 kernel and RMX2072 vendor implementation. Record the external image's build ID and SHA-256 from [the GSI lock](../build/gsi.json) alongside the hashes of the board artifacts used for each boot.

## Headless boot sequence

1. Replay the warm USB-backed control. Android first-stage init mounted the verified GSI, switched root and mounted the project vendor from RAM. PID 1 entered `selinux_setup`. Trial 02 selected genfs `202604` and passed a separate strict compile. [Handset trial and replay](https://github.com/xxbo/RMX2072-AOSP-Project/blob/da4385b38212ea8f84307f672a741da77172ecc5/docs/ANDROID17_USB_MOUNT.md#project-vendor-and-pid-1-policy-setup)
2. Extend observation past the kernel policy write. Record its result, enforcing state, second-stage exec or the first error. Replace fixture-only device paths and the temporary emulator first-stage binary for the source-built boot path. Validate the target vendor/GSI VINTF pair and record signing and verity inputs for both images.
3. Select an internal UFS layout from measured image sizes and document recovery for the partitions it changes. Preserving every current F.20 logical partition leaves a 1,095,585,792-byte deficit for the selected GSI. See the [partition preflight](GSI_PREFLIGHT_2026-11-06.md).
4. Cold-boot with the USB image server disconnected, then connect ADB and collect the same-boot identity, mount sources and Android init logs specified in the [M1 acceptance criteria](../plan.md#milestones-and-acceptance).

The F.20 vendor comparison remains available for isolating compatibility issues. A project-built generic system image is an optional comparison with the pinned prebuilt GSI. Board drivers and Android hardware services belong in the kernel and device vendor implementation.
