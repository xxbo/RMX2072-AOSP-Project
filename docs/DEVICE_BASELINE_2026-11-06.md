# RMX2072 post-unlock device baseline

Captured on 2026-11-06 from the physical handset. These are stock-firmware observations, not Android 17 or 6.18 boot-test results. Raw evidence, images, calibration data and identifiers remain outside this repository.

## Confirmed device facts

| Item | Observation |
|---|---|
| Model / device / platform | RMX2072 / RMX2072CN / SM8250 Kona |
| Project / hardware version properties | 20607 / 50 |
| Firmware | RMX2072_11.F.20_3200_202401191645 |
| System | Android 12, API 31, security patch 2024-02-05 |
| Vendor SDK / VNDK | 30 / 30 |
| Product first API / board first API | 29 / 30; record both rather than conflating them |
| Treble / vendor manifest target level | true / FCM 5 |
| Running kernel | 4.19.157-perf+ |
| Final boot state | flash.locked=0, vbmeta.device_state=unlocked, verifiedbootstate=orange |
| Android boot completion | sys.boot_completed=1 after stock recovery format-data and setup |
| UFS inquiry | SAMSUNG KLUDG4UHDB-B2D1, firmware 0900 |
| Physical partitions | Single boot, recovery, abl, ocdt; super and dtbo present |
| Modern boot partitions | No vendor_boot, init_boot or physical vendor_dlkm entry in captured GPT |
| Dynamic partitions / slot suffix | true / empty; no A/B layout inferred from a generic GSI naming convention |
| Boot image | Header v2; 4096-byte pages; kernel 46,608,400 bytes; ramdisk 1,011,839 bytes; DTB bundle 12,616,040 bytes |

The boot image was inspected using AOSP `system/tools/mkbootimg` at commit `d2bb0af5ba6d3198a3e99529c97eda1be0b5a093`. A bundled DTB may contain multiple hardware variants; it does not identify the selected runtime board by itself.

## Stock configuration evidence

`/proc/config.gz` was readable through ordinary ADB and decompressed locally. Confirmed assignments include:

```text
CONFIG_ARM64_4K_PAGES=y
CONFIG_MODULES=y
CONFIG_MODVERSIONS=y
CONFIG_TOUCHPANEL_GOODIX_GT9886=y
CONFIG_OPLUS_SM8250_CHARGER=y
CONFIG_DRM_MSM=y
CONFIG_DRM_MSM_DSI=y
CONFIG_QCOM_KGSL=y
CONFIG_ION=y
```

These are actual running-kernel configuration inputs for baseline comparison. They do not demonstrate that a driver loads or that every physical component has been identified. In particular, the GT9886 setting confirms the configuration mismatch already identified in the current shared Oplus source fragment.

## Recovery evidence and limits

- Bootloader unlock completed and was verified both through fastboot and post-boot Android properties.
- EDL/Sahara/Firehose connectivity worked with the 865 programmer; six primary GPTs were read and their header/entry CRC32 values validated.
- A local stock system/firmware/calibration backup totals approximately 10.537 GiB. The manifest covers 89 files with lengths and SHA-256 hashes. Userdata, cache and log/dump partitions are excluded; this is not a complete storage clone or a user-data backup.
- Original ABL/OCDT were restored through EDL and independently reread byte-for-byte. Stock Android then booted normally while retaining the unlocked state.
- Full-system restoration from the backup has not been exercised. A separate exact factory OFP/OTA package has not yet been archived. Do not claim these gates are complete.

## Android 17 GSI gates

Using an official ARM64 AOSP GSI avoids building the Android framework in project CI. It does not replace the RMX2072 vendor stack, device tree or kernel adaptation.

The captured stock vendor manifest declares `target-level="5"`. At Android 17 hardware/interfaces commit `0162af698935100a590b7359581ac8b1b80693e5`, `compatibility_matrices/Android.bp` lists `SYSTEM_MATRIX_DEPS_A17` starting with FCM 7 and 8, followed by dated newer matrices. FCM 5 is absent from that default list.

This is a concrete compatibility gap to investigate, not a completed test or proof that every Android 17 GSI fails. Inspect the chosen image's actual matrices, linker/VNDK handling, HAL requirements and first-boot logs before selecting a remediation. Do not simply raise the vendor manifest target level: that does not implement newer HAL contracts.

## Next execution gates

1. Use this handset's F.20 vendor files/configuration as the captured baseline. Historical F.15/F.17 sources remain references, not a proven matched extraction set.
2. Add a manually triggered legacy-kernel build with pinned source, toolchain and the device-exact configuration; keep output marked build-tested until booted.
3. Add a separate manually triggered ACK 6.18 build and KGSL/module compile probe. Pin the complete build manifest/toolchain, not only kernel/common.
4. Measure runner disk, RAM and runtime before promising that a complete Kleaf workspace fits the standard Actions runner.
5. Test a selected Android 17 ARM64 GSI against a known-compatible kernel/vendor combination, independently of the first 6.18 boot attempt.
6. Bring up 6.18 boot/UFS/USB/DTS first, then memory/display/touch and GPU, following the existing dependency map.

## Repeat the read-only audit

```text
python scripts/device_audit/collect_device.py --output /path/outside/repository/device-audit
```

Use `--serial` only to select a target when necessary; it is not recorded in the audit JSON. The collector deliberately keeps raw evidence outside the public repository, captures an allowlist of properties, pulls VINTF/fstab/kernel configuration, and reports permission-denied/missing paths rather than hiding them. Live DT, `/proc/devinfo`, `/proc/touchpanel` and linkerconfig access were denied on this stock user build; component selection remains incomplete.

## References

- [AOSP mkbootimg revision](https://android.googlesource.com/platform/system/tools/mkbootimg/+/d2bb0af5ba6d3198a3e99529c97eda1be0b5a093/)
- [Android 17 framework matrix inputs](https://android.googlesource.com/platform/hardware/interfaces/+/0162af698935100a590b7359581ac8b1b80693e5/compatibility_matrices/Android.bp)
- [Official GSI releases](https://developer.android.com/topic/generic-system-image/releases)
- [Existing driver migration matrix](DRIVER_MIGRATION_MATRIX.md)
- [Existing KGSL research](KGSL_ADRENO_RESEARCH.md)
