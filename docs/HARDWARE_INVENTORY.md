# Hardware and Source Inventory

## Target identity

| Field | Working value | Evidence |
| --- | --- | --- |
| Commercial model | realme X50 Pro Player Edition | Project target |
| Model | RMX2072 | Community device tree |
| Device codename | bladerunner_48m | Community device tree |
| SoC | Snapdragon 865 | Product/platform identification |
| Platform | SM8250 / Kona | Qualcomm platform lineage |
| Architecture | ARM64 | Platform |
| Legacy kernel | Linux 4.19.x | Official source trees |

Exact regional SKU, RAM/storage variant, panel/touch vendor, camera module revisions, firmware build and partition layout remain to be captured from the handset.

## Source repositories

| Source | Purpose | Notes |
| --- | --- | --- |
| [Realme Android Q kernel](https://github.com/realme-kernel-opensource/realmeX50Pro-5GPlay_AndroidQ-kernel-source) | Device-specific legacy kernel baseline | Official player-edition source |
| [Realme Android S shared kernel](https://github.com/realme-kernel-opensource/realme_GTneo2-X50pro-GTMasterExploratory-AndroidS-kernel-source) | Later downstream reference | Shared source; verify exact device applicability |
| [RMX2072 device tree](https://github.com/IGaganpreetSingh/android_device_realme_bladerunner_48m) | Android product/device configuration | Community source; verify branch and ROM target |
| [Project Elixir SM8250 kernel](https://github.com/ProjectElixir-Devices/android_kernel_realme_sm8250) | Community kernel reference | Verify branch and exact device support |
| [Android Common Kernel](https://android.googlesource.com/kernel/common/) | Modern kernel base | Select branch after checking Android release and GKI requirements |

## Hardware inventory checklist

| Subsystem | What to identify | Current status |
| --- | --- | --- |
| Display | panel, DSI, DRM/MDSS path, refresh modes | Research needed |
| Touch | controller, firmware, input driver | Research needed |
| GPU | Adreno 650, KGSL/DRM path, userspace driver and firmware | Research needed |
| Camera | sensors, EEPROM, actuator, CSIPHY/CSID, ISP, HAL | Research needed |
| Audio | codec, DSP, routing, amplifier, HAL | Research needed |
| Modem | baseband firmware, QRTR/QMI interfaces | Research needed |
| Wi-Fi/Bluetooth | chipset, CNSS/WLAN stack, firmware | Research needed |
| NFC | controller and firmware | Research needed |
| Sensors | accelerometer, gyro, proximity, light and other sensors | Research needed |
| Charging/power | fuel gauge, charger, thermal, fast-charging stack | Research needed |
| Storage | UFS controller, fstab and encryption | Research needed |
| Biometrics | fingerprint hardware, HAL and secure service | Research needed |
| Security | Keymaster/Gatekeeper, TEE, AVB, Widevine | Research needed |

## Required handset capture
- Settings → About device: model, build number, Android version and baseband.
- Build properties, especially ro.product.*, ro.build.fingerprint and ro.vendor.*.
- Partition names and sizes.
- Fastboot variables with serial numbers and sensitive identifiers redacted.
- Boot image header/version and kernel release.
- Bootloader unlock state and AVB state.
- Stock firmware package version and SHA-256 hashes.

Never commit IMEI, serial number, MAC addresses, personal data, signing keys or proprietary firmware blobs.
