# Android 17 GSI bring-up guide

The selected system image is Google Android 17 QPR1 ARM64 + GMS, CP3A.260905.010. The project supplies the ACK 6.18 kernel and RMX2072 vendor implementation. Record the external image's build ID and SHA-256 from [the GSI lock](../build/gsi.json) alongside the hashes of the board artifacts used for each boot.

## Headless boot sequence

1. Use load-05 as the warm regression control. On 6.18.32, PID 1 installed the policy and entered second-stage init under enforcing with the original dm-verity root. The GSI used RAM and USB. The project vendor was a RAM-backed, read-only mount. [Trial and replay](https://github.com/xxbo/RMX2072-AOSP-Project/blob/19d77ebfd3b5c5eed24c49c4494043a9203a12b7/docs/ANDROID17_USB_MOUNT.md#pid-1-sigbus-and-second-stage-execution)
2. Select an internal UFS layout for the measured GSI and project vendor. Keeping every other F.20 partition leaves a 1,095,585,792-byte GSI deficit. Verify recovery of the partitions the chosen layout changes. [Partition preflight](GSI_PREFLIGHT_2026-11-06.md)
3. Replace fixed fixture paths with partition discovery, record the verification inputs for both images and validate the target GSI/vendor VINTF pair. With both mounts backed by UFS, capture successful reads of `/system/build.prop`, `/system/etc/init/hw/init.rc` and `/etc/cgroups.json` under enforcing. Record the next service or mount result.
4. Cold-boot with the USB image server disconnected, then connect ADB and collect the same-boot identity, mount sources and Android init logs specified in the [M1 acceptance criteria](../plan.md#milestones-and-acceptance).

The F.20 vendor comparison remains available for isolating compatibility issues. A project-built generic system image is an optional comparison with the pinned prebuilt GSI. Board drivers and Android hardware services belong in the kernel and device vendor implementation.
