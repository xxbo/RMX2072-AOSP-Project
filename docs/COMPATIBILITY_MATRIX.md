# Compatibility and Validation Matrix

Status values: **Unknown**, **Source-reviewed**, **Build-tested**, **Boot-tested**, **Hardware-tested**, **Blocked**.

Driver-specific source evidence and proposed migration dispositions are tracked in [DRIVER_MIGRATION_MATRIX.md](./DRIVER_MIGRATION_MATRIX.md); shared prerequisites and sequencing are in [DRIVER_DEPENDENCY_MAP.md](./DRIVER_DEPENDENCY_MAP.md). Most entries remain source-reviewed. NQ-NCI strict DDK and CRC validation passed in run 42226214281; module loading remains untested. The project-built 6.18 kernel has now reached RAM-only diagnostic userspace using the stock DTB bundle/original DTBO. This partial boot does not establish upstream board support or Android compatibility. See [the runtime record](../build/device/handoff-runtime-2026-11-08.json).

## Platform layers

| Layer | Candidate | Status | Evidence required |
| --- | --- | --- | --- |
| Android framework | AOSP Android 17 | Unknown | Successful build and physical boot |
| System image | Google Android 17 QPR1 ARM64 + GMS | Image inspected, not boot-tested | ZIP hash verified; actual FCM/VNDK and capacity gaps in GSI_PREFLIGHT_2026-11-06.md |
| Vendor image | RMX2072 F.20 stock vendor | Stock boot-tested; Android 17 compatibility unresolved | FCM 5, VNDK 30; target HAL tests pending |
| Legacy kernel | Realme F.20 4.19.157 | Stock boot-tested | Logging-reader Android restored and booted; backup limits in DEVICE_BASELINE_2026-11-06.md |
| Community kernel | SM8250-Common 4.19.325 | Build-tested | [Legacy build](https://github.com/xxbo/RMX2072-AOSP-Project/actions/runs/42228243866); boot of the rebuilt community image pending |
| ACK/GKI | Android 17 6.18.32 generic ARM64 | Generic distribution build-tested | Run 42194678844 passed; board/module/boot tests remain |
| Platform kernel handoff | 6.18.32 + stock DTB bundle/original DTBO | Boot-tested (diagnostic userspace only) | Eight CPUs activated; init and timed EDL restart at 90.74s; no UDC; ten-minute stability pending |
| Device tree | bladerunner_48m | Source-reviewed (provisional) | Exact device match and build product |
| Vendor modules | Device-specific | Unknown | Module load logs and subsystem tests |

## Hardware test matrix

| Feature | Status | Test evidence / notes |
| --- | --- | --- |
| Boot / reboot | Boot-tested (partial diagnostic path) | 6.18 RAM-only supervisor reached; explicit EDL restart captured. Upstream board DTS still loops; sustained runtime untested. |
| Display / brightness / refresh rate | Unknown | |
| Touch / gestures | Unknown | |
| USB / ADB / MTP | SID0 ACM shell and 606-second paced test passed | 29 responses / 7.25 MiB verified, same boot, configured high-speed UDC. Uncapped bursts still return short data; ADB/MTP are not supplied by the diagnostic ramdisk. [Soak evidence](../build/device/usb-soak-2026-11-09.json). |
| UFS / encryption | Unknown | |
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
