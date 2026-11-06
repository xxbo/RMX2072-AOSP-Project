# Compatibility and Validation Matrix

Status values: **Unknown**, **Source-reviewed**, **Build-tested**, **Boot-tested**, **Hardware-tested**, **Blocked**.

## Platform layers

| Layer | Candidate | Status | Evidence required |
| --- | --- | --- | --- |
| Android framework | AOSP Android 17 | Unknown | Successful build and physical boot |
| System image | Android 17 GSI | Unknown | Treble/VINTF checks and boot logs |
| Vendor image | RMX2072 stock vendor | Unknown | Build fingerprint, VINTF and HAL tests |
| Legacy kernel | Realme 4.19.x | Source-reviewed (provisional) | Reproducible build and device boot |
| Community kernel | SM8250 4.19.x | Source-reviewed (provisional) | Exact branch support and reproducible boot |
| ACK/GKI | Candidate 6.18 branch | Unknown | KMI/module build, boot and hardware tests |
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
