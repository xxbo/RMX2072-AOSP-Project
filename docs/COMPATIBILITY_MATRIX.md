# Compatibility and Validation Matrix

Status values: **Unknown**, **Source-reviewed**, **Build-tested**, **Boot-tested**, **Hardware-tested**, **Blocked**.

Driver-specific source evidence and proposed migration dispositions are tracked in [DRIVER_MIGRATION_MATRIX.md](./DRIVER_MIGRATION_MATRIX.md); shared prerequisites and sequencing are in [DRIVER_DEPENDENCY_MAP.md](./DRIVER_DEPENDENCY_MAP.md). Most entries remain source-reviewed. NQ-NCI strict DDK and CRC validation passed in run 42226214281; module loading remains untested. The [development plan](../plan.md) defines target-system acceptance. The table also includes hardware results recorded on the bring-up branches.

## Platform layers

| Layer | Candidate | Status | Evidence required |
| --- | --- | --- | --- |
| Android framework | Android 17 | Open | Same-boot init, launcher, physical input and boot-completion evidence. |
| System image | Android 17 QPR1 ARM64 + GMS, CP3A.260905.010 | Boot-tested through second-stage init from internal UFS with USB attached | Android PID 1 verified and mounted system, entered enforcing and read the complete `/system/build.prop` and main `init.rc`. A disconnected cold boot with an API 37 ADB shell remains open. [UFS evidence](M1_UFS_FIRST_STAGE.md) |
| Vendor image | Signed project-built RMX2072 ext4 | Boot-tested on internal UFS | First-stage init verified and mounted vendor. Under enforcing, PID 1 imported the configured zygote scripts and vold read the complete vendor fstab. Full VINTF compatibility remains open. [Vendor service trial](../build/device/m1-ufs-first-stage-vendor-services-2026-11-13.json) |
| TEE / Keymaster | Source-built device HAL and 6.18 transport | Blocked at the hardware service | 6.18 found the resident `keymaster64`. In a private comparison, the F.20 HAL opened hwbinder and read an empty listener readiness property. A successful GSI hardware call and maintenance registration remain open. [Reference trials](M1_UFS_FIRST_STAGE.md#four-writable-volume-handset-runs) |
| Stock vendor/ODM comparison | F.20 | Diagnostic comparison | Strict compile with the GSI reported 299 neverallow conflicts across 262 locations. Target vendor acceptance uses the project image. [Comparison](https://github.com/xxbo/RMX2072-AOSP-Project/blob/da4385b38212ea8f84307f672a741da77172ecc5/build/device/gsi17-init-policy-2026-11-11.json) |
| Legacy control | Realme F.20 4.19.157 | Stock boot-tested | Logging-reader Android restored and booted. [Recovery scope](DEVICE_BASELINE_2026-11-06.md) |
| Community kernel | SM8250-Common 4.19.325 | Build-tested | [Legacy build](https://github.com/xxbo/RMX2072-AOSP-Project/actions/runs/42228243866) |
| ACK/GKI | Android 17 6.18.32 generic ARM64 | Generic distribution build-tested | [Kleaf build](GKI_618_BUILD.md) |
| Platform kernel | 6.18.32 with factory-derived G3 DTB and original DTBO | Warm boot through Android PID 1 second-stage entry from UFS | Eight CPUs, paced USB and warm UFS reads were exercised in earlier trials. M2 requires reproducing M1 with source-built trees and ramdisk. [UFS](../build/device/ufs-g3-2026-11-10.json) · [Android handoff](M1_UFS_FIRST_STAGE.md) |
| Board DTB/DTBO | Source-built RMX2072 trees | Open | Repeat cold boot, USB, UFS, recovery and headless Android tests. |
| Device-specific modules | Built for the project kernel | Per driver | Record module load and hardware results by subsystem. |

## Hardware test matrix

| Feature | Status | Test evidence / notes |
| --- | --- | --- |
| Boot / reboot | Android 17 second-stage entry from internal UFS on a USB-attached warm boot | The GSI reached post-fs-data. Disconnected Android cold boot and target boot completion remain open. [UFS trial records](M1_UFS_FIRST_STAGE.md) |
| Display / brightness / refresh rate | Unknown | |
| Touch / gestures | Unknown | |
| USB / ADB / MTP | Diagnostic ACM hardware-tested, Android 17 ADB unavailable in trial 09 | The 606-second paced ACM test passed. Uncapped bursts produced short reads. Trial 09 recorded 93 empty ADB polls and 47 USB samples with diagnostic ACM. MTP remains untested. [Soak evidence](../build/device/usb-soak-2026-11-09.json) · [Android 17 USB observations](../build/device/m1-ufs-keymaster-2026-11-13.json) |
| UFS | Hardware-tested (warm, read-only on 6.18) | Two-lane HS-G3 and six LUNs. First-stage init verified and mounted both the GSI and project vendor from internal super. [G3 reads](../build/device/ufs-g3-2026-11-10.json) · [Verified mounts](M1_UFS_FIRST_STAGE.md) |
| Encrypted userdata | Open | Writable RAM-backed ext4 data and metadata passed write and fsync checks. Persistent encrypted UFS userdata across reboot remains untested. [Scratch volumes](M1_UFS_FIRST_STAGE.md#writable-data-and-metadata-trial) |
| SIM / calls / SMS / mobile data | Unknown | |
| Wi-Fi | Unknown | |
| Bluetooth | Unknown | |
| NFC | Unknown | |
| GPS / location | Unknown | |
| Speakers / microphones / earpiece | Unknown | |
| Camera (front/rear/video) | Unknown | |
| Fingerprint | Unknown | |
| Sensors | Unknown | |
| Charging / fast charging | Unknown | |
| Thermal / sustained performance | Unknown | |
| Widevine / DRM | Unknown | |
| OTA / recovery / rollback | F.20 recovery hardware-tested, Android GSI update open | After trial 09, the full F.20 super, both LP slots, log-reader boot and original DTBO matched the baseline. F.20 completed boot. [Recovery records](../build/device/m1-ufs-keymaster-2026-11-13.json) |

## Test record template
For each test, record date/device build, kernel commit/config, system/vendor fingerprints, exact steps, expected and observed behavior, logs and result.
