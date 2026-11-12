# Compatibility and Validation Matrix

Status values: **Unknown**, **Source-reviewed**, **Build-tested**, **Boot-tested**, **Hardware-tested**, **Blocked**.

Driver-specific source evidence and proposed migration dispositions are tracked in [DRIVER_MIGRATION_MATRIX.md](./DRIVER_MIGRATION_MATRIX.md); shared prerequisites and sequencing are in [DRIVER_DEPENDENCY_MAP.md](./DRIVER_DEPENDENCY_MAP.md). Most entries remain source-reviewed. NQ-NCI strict DDK and CRC validation passed in run 42226214281; module loading remains untested. The [development plan](../plan.md) defines target-system acceptance. The table also includes hardware results recorded on the bring-up branches.

## Platform layers

| Layer | Candidate | Status | Evidence required |
| --- | --- | --- | --- |
| Android framework | Android 17 | Open | Same-boot init, launcher, physical input and boot-completion evidence. |
| System image | Android 17 QPR1 ARM64 + GMS | Hardware-tested on USB-backed dm-verity | Android PID 1 switched root and executed GSI `selinux_setup`. Second-stage init, Android ADB and a disconnected UFS cold boot remain open. [Physical trials](https://github.com/xxbo/RMX2072-AOSP-Project/blob/da4385b38212ea8f84307f672a741da77172ecc5/build/device/gsi17-project-vendor-2026-11-11.json) |
| Vendor image | Source-built 2 MiB RMX2072 ext4 | Mounted read-only from RAM | Trial 02 selected genfs `202604` and passed a separate strict compile. Kernel policy installation, enforcing mode, VINTF and vendor AVB remain open. The fixture declares no HAL instances. [Trial](https://github.com/xxbo/RMX2072-AOSP-Project/blob/da4385b38212ea8f84307f672a741da77172ecc5/docs/ANDROID17_USB_MOUNT.md#project-vendor-and-pid-1-policy-setup) |
| Stock vendor/ODM comparison | F.20 | Diagnostic comparison | Strict compile with the GSI reported 299 neverallow conflicts across 262 locations. Target vendor acceptance uses the project image. [Comparison](https://github.com/xxbo/RMX2072-AOSP-Project/blob/da4385b38212ea8f84307f672a741da77172ecc5/build/device/gsi17-init-policy-2026-11-11.json) |
| Legacy control | Realme F.20 4.19.157 | Stock boot-tested | Logging-reader Android restored and booted. [Recovery scope](DEVICE_BASELINE_2026-11-06.md) |
| Community kernel | SM8250-Common 4.19.325 | Build-tested | [Legacy build](https://github.com/xxbo/RMX2072-AOSP-Project/actions/runs/42228243866) |
| ACK/GKI | Android 17 6.18.32 generic ARM64 | Generic distribution build-tested | [Kleaf build](GKI_618_BUILD.md) |
| Platform kernel | 6.18.32 with factory-derived G3 DTB and original DTBO | Boot-tested through Android PID 1 policy setup | Eight CPUs, paced USB, warm UFS reads and first-stage mounts exercised. [UFS](https://github.com/xxbo/RMX2072-AOSP-Project/blob/da4385b38212ea8f84307f672a741da77172ecc5/build/device/ufs-g3-2026-11-10.json) · [Handoff](https://github.com/xxbo/RMX2072-AOSP-Project/blob/da4385b38212ea8f84307f672a741da77172ecc5/build/device/gsi17-project-vendor-2026-11-11.json) |
| Board DTB/DTBO | Source-built RMX2072 trees | Open | Repeat cold boot, USB, UFS, recovery and headless Android tests. |
| Device-specific modules | Built for the project kernel | Per driver | Record module load and hardware results by subsystem. |

## Hardware test matrix

| Feature | Status | Test evidence / notes |
| --- | --- | --- |
| Boot / reboot | Diagnostic boot-tested | Software return to EDL and restoration of F.20 boot/DTBO verified. Independent Android cold boot is open. [Trial](https://github.com/xxbo/RMX2072-AOSP-Project/pull/3) |
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
