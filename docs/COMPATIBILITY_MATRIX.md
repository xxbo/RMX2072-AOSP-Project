# Compatibility and Validation Matrix

Status values: **Unknown**, **Source-reviewed**, **Build-tested**, **Boot-tested**, **Hardware-tested**, **Blocked**.

Driver-specific source evidence and proposed migration dispositions are tracked in [DRIVER_MIGRATION_MATRIX.md](./DRIVER_MIGRATION_MATRIX.md); shared prerequisites and sequencing are in [DRIVER_DEPENDENCY_MAP.md](./DRIVER_DEPENDENCY_MAP.md). Most entries remain source-reviewed. NQ-NCI has a compile-smoke artifact; strict DDK validation is running. No project-built 6.18 kernel or driver has been booted/loaded on RMX2072. The stock phone boots normally after unlock; that result is separate from target-system validation.

## Platform layers

| Layer | Candidate | Status | Evidence required |
| --- | --- | --- | --- |
| Android framework | AOSP Android 17 | Unknown | Successful build and physical boot |
| System image | Google Android 17 QPR1 ARM64 + GMS | Image inspected, not boot-tested | ZIP hash verified; actual FCM/VNDK and capacity gaps in GSI_PREFLIGHT_2026-11-06.md |
| Vendor image | RMX2072 F.20 stock vendor | Stock boot-tested; Android 17 compatibility unresolved | FCM 5, VNDK 30; target HAL tests pending |
| Legacy kernel | Realme 4.19.x | Source-reviewed (provisional) | Reproducible build and device boot |
| Community kernel | SM8250 4.19.x | Source-reviewed (provisional) | Exact branch support and reproducible boot |
| ACK/GKI | Android 17 6.18.32 generic ARM64 | Generic distribution build-tested | Run 42194678844 passed; board/module/boot tests remain |
| Device tree | bladerunner_48m | Source-reviewed (provisional) | Exact device match and build product |
| Vendor modules | Device-specific | Unknown | Module load logs and subsystem tests |

## Hardware test matrix

| Feature | Status | Test evidence / notes |
| --- | --- | --- |
| Boot / reboot | Unknown | |
| Display / brightness / refresh rate | Unknown | |
| Touch / gestures | Unknown | |
| USB / ADB / MTP | Unknown | |
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
