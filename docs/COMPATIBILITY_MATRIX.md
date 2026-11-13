# Compatibility and Validation Matrix

Status values: **Unknown**, **Source-reviewed**, **Build-tested**, **Boot-tested**, **Hardware-tested**, **Blocked**.

Driver-specific source evidence and proposed migration dispositions are tracked in [DRIVER_MIGRATION_MATRIX.md](./DRIVER_MIGRATION_MATRIX.md); shared prerequisites and sequencing are in [DRIVER_DEPENDENCY_MAP.md](./DRIVER_DEPENDENCY_MAP.md). Most entries remain source-reviewed. NQ-NCI strict DDK and CRC validation passed in run 42226214281; module loading remains untested. The [development plan](../plan.md) defines target-system acceptance. The table also includes hardware results recorded on the bring-up branches.

## Platform layers

| Layer | Candidate | Status | Evidence required |
| --- | --- | --- | --- |
| Android framework | Android 17 | Open | Same-boot init, launcher, physical input and boot-completion evidence. |
| System image | Android 17 QPR1 ARM64 + GMS | Second-stage init observed under enforcing on a warm boot | RAM/USB-backed dm-verity lost its fallback reader. `/system/build.prop` and startup configuration reads failed. Android 17 ADB and disconnected UFS boot were `NOT RUN`. [Trial 05](https://github.com/xxbo/RMX2072-AOSP-Project/blob/19d77ebfd3b5c5eed24c49c4494043a9203a12b7/build/device/gsi17-enforcing-second-stage-2026-11-12.json) |
| Vendor image | Project-built 2 MiB RMX2072 ext4 | Mounted read-only from RAM | Genfs 202604 and strict compilation passed in the earlier control. On November 12 the kernel accepted 703,220 policy bytes and entered enforcing. Vendor AVB, full VINTF and UFS-backed mounting remain open. The fixture declares no HAL instances. [Policy load](https://github.com/xxbo/RMX2072-AOSP-Project/blob/19d77ebfd3b5c5eed24c49c4494043a9203a12b7/build/device/gsi17-policy-install-2026-11-12.json) |
| Stock vendor/ODM comparison | F.20 | Diagnostic comparison | Strict compile with the GSI reported 299 neverallow conflicts across 262 locations. Target vendor acceptance uses the project image. [Comparison](https://github.com/xxbo/RMX2072-AOSP-Project/blob/da4385b38212ea8f84307f672a741da77172ecc5/build/device/gsi17-init-policy-2026-11-11.json) |
| Legacy control | Realme F.20 4.19.157 | Stock boot-tested | Logging-reader Android restored and booted. [Recovery scope](DEVICE_BASELINE_2026-11-06.md) |
| Community kernel | SM8250-Common 4.19.325 | Build-tested | [Legacy build](https://github.com/xxbo/RMX2072-AOSP-Project/actions/runs/42228243866) |
| ACK/GKI | Android 17 6.18.32 generic ARM64 | Generic distribution build-tested | [Kleaf build](GKI_618_BUILD.md) |
| Platform kernel | 6.18.32 with factory-derived G3 DTB and original DTBO | Warm boot through Android PID 1 second-stage entry | Eight CPUs, paced USB and warm UFS reads were exercised in earlier trials. Repeat the headless boot on source-built trees for M2. [UFS](https://github.com/xxbo/RMX2072-AOSP-Project/blob/da4385b38212ea8f84307f672a741da77172ecc5/build/device/ufs-g3-2026-11-10.json) · [Trial 05](https://github.com/xxbo/RMX2072-AOSP-Project/blob/19d77ebfd3b5c5eed24c49c4494043a9203a12b7/build/device/gsi17-enforcing-second-stage-2026-11-12.json) |
| Board DTB/DTBO | Source-built RMX2072 trees | Open | Repeat cold boot, USB, UFS, recovery and headless Android tests. |
| Device-specific modules | Built for the project kernel | Per driver | Record module load and hardware results by subsystem. |

## Hardware test matrix

| Feature | Status | Test evidence / notes |
| --- | --- | --- |
| Boot / reboot | Android second-stage entry on RAM/USB fixture | Independent Android cold boot remains open. F.20 boot/DTBO readbacks and stock boot completion are recorded separately from the Android 17 trial. [Trial 05](https://github.com/xxbo/RMX2072-AOSP-Project/blob/19d77ebfd3b5c5eed24c49c4494043a9203a12b7/build/device/gsi17-enforcing-second-stage-2026-11-12.json) |
| Display / brightness / refresh rate | Unknown | |
| Touch / gestures | Unknown | |
| USB / ADB / MTP | SID0 ACM shell and 606-second paced test passed | 29 responses / 7.25 MiB verified, same boot, configured high-speed UDC. Uncapped bursts still return short data; ADB/MTP are not supplied by the diagnostic ramdisk. [Soak evidence](../build/device/usb-soak-2026-11-09.json). |
| UFS | Hardware-tested (warm, read-only) | Two-lane HS-G3, six LUNs and verified F.20 mounts. [G3 reads](https://github.com/xxbo/RMX2072-AOSP-Project/pull/6) · [Mounts](https://github.com/xxbo/RMX2072-AOSP-Project/pull/8) |
| Encrypted userdata | Unknown | Validate key services, data access and reboot persistence on the target system. |
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
| OTA / recovery / rollback | Unknown | |

## Test record template
For each test, record date/device build, kernel commit/config, system/vendor fingerprints, exact steps, expected and observed behavior, logs and result.
