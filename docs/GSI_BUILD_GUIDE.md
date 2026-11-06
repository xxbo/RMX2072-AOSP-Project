# Android 17 GSI Build and Bring-up Guide

## Strategy
Treat GSI bring-up and kernel modernization as separate tracks. First test a suitable Android 17 GSI with a known-compatible device kernel/vendor stack. This isolates framework and Treble compatibility from kernel migration.

The proposed execution environment is GitHub Actions for kernel/module builds and an official ARM64 Android 17 GSI for the system layer; local USB remains the hardware-test interface. See the [captured F.20 baseline](DEVICE_BASELINE_2026-11-06.md) for boot header v2, single boot/recovery layout, vendor FCM 5 and unresolved Android 17 compatibility gates. The GSI is a candidate until its exact image contents and device boot are checked.

## Preflight
- Confirm exact RMX2072 model and region.
- Confirm bootloader unlock capability and understand the data wipe.
- Capture partition layout, boot image metadata, AVB state and stock firmware build.
- Verify Treble/VINTF status and dynamic partition arrangement.
- Obtain a complete stock restore package and verify its hashes.
- Confirm GSI architecture, binder mode, partition size and Android release requirements.

## Build options
1. Use an official or reputable Android 17 GSI for an initial compatibility experiment.
2. Build AOSP system images from the corresponding Android source branch after fixing the build host, manifest and target configuration.
3. Keep device-specific configuration, vendor blobs and kernel work outside the generic system image where possible.

## Validation sequence
1. Validate image metadata and image size before flashing.
2. Confirm target partition and fastboot/fastbootd mode.
3. Follow device-specific instructions and preserve stock images.
4. Boot without changing the kernel initially.
5. Capture first-boot logs, VINTF results and dmesg.
6. Test display, touch, telephony, Wi-Fi, Bluetooth, audio, camera, sensors, charging and encryption separately.

This is a planning checklist, not a verified RMX2072 flashing recipe. Exact commands require the handset partition map, bootloader state and firmware revision.
