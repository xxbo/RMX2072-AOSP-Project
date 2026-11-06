# Hardware and Source Inventory

> Snapshot: 2026-11-06 UTC  
> Evidence status: source-reviewed; no current physical-device capture has been recorded.

## Target identity

| Field | Working value | Evidence |
|---|---|---|
| Commercial model | realme X50 Pro Player Edition | Project target |
| Model | RMX2072 | Community device tree |
| Device codename | bladerunner_48m | Community device tree |
| SoC | Snapdragon 865 | Product/platform identification |
| Platform | SM8250 / Kona | Qualcomm platform lineage |
| Architecture | ARM64 | Platform |
| Legacy kernel | Linux 4.19.x | Official source trees |
| Research target | Android 17 ACK / GKI 6.18 | Pinned official reference; not device-ready |

Exact regional SKU, RAM/storage variant, panel/touch vendor, camera module revisions, firmware build and partition layout remain to be captured from the handset.

## Source repositories

| Source | Purpose | Notes |
|---|---|---|
| [Realme Android Q kernel](https://github.com/realme-kernel-opensource/realmeX50Pro-5GPlay_AndroidQ-kernel-source/tree/24a15224fbae8ab0e8ba29a9046c06ee7a9f53a4) | Device-specific legacy kernel baseline | Official player-edition source, 4.19.81 |
| [Realme Android S shared kernel](https://github.com/realme-kernel-opensource/realme_GTneo2-X50pro-GTMasterExploratory-AndroidS-kernel-source/tree/4e5ec4aeeb781851b0fe6c268d9ba69953166fda) | Later downstream reference | Shared source; verify exact device applicability, 4.19.157 |
| [RMX2072 device tree](https://github.com/IGaganpreetSingh/android_device_realme_bladerunner_48m/tree/08afb1d784dd568fa04ca462684a350b37e2bf4a) | Android product/device configuration | Community source; proprietary list identifies RMX2072_11.F.15 |
| [RMX2072 vendor reference](https://github.com/sreelekshman/android_vendor_realme_bladerunner_48m/tree/6f8c1c21395f3356b7182f576afe3b8e44b7b6c4) | Vendor blob provenance reference | Commit message says RMX2072_11.F.17; mismatch with F.15 device-tree list remains unresolved |
| [SM8250-Common kernel](https://github.com/SM8250-Common/android_kernel_realme_sm8250/tree/b76eb6c93add8152b1aa873da0d8d7f495cccab0) | Newer downstream implementation reference | 4.19.325; source/config reference only, not a validated RMX2072 build |
| [Current shared SM8250 common device tree](https://github.com/SM8250-Common/android_device_realme_sm8250-common/tree/681bfa28e36003fddc004bfebef491234505adbc) | Shared platform configuration reference | Its proprietary-files list identifies RMX3371 blobs; do not use it as an RMX2072 vendor source |
| [Android Common Kernel / GKI](https://android.googlesource.com/kernel/common/+/ecdaacc9a0ee87eaf9544e1836d86bd9d590312e/) | Modern kernel base | Pinned Android 17 6.18 reference; not a device-ready RMX2072 kernel |

## RMX2072-specific source evidence

The following entries were found in the RMX2072-specific device-tree proprietary-file manifest at commit 08afb1d784dd568fa04ca462684a350b37e2bf4a. They identify source/configuration candidates; they do not prove that every listed component is physically populated in every RMX2072 unit.

| Subsystem | Source evidence found | What it establishes | What remains unverified |
|---|---|---|---|
| Display | Samsung AMS678UW01 LTM/QDCM calibration filenames, including DSC command-mode and QHD variants | Samsung panel-family calibration is present in the device-tree extraction list | Exact panel ID, revision, supported refresh modes, DSC parameters and panel DTS binding |
| Touch | FW_GT9886_SAMSUNG.img, FW_GT9886_SAMSUNG_FAE.img and LIMIT_GT9886_SAMSUNG.img | GT9886 Samsung touch firmware is listed | Actual controller ID, I2C address, panel pairing, firmware version and gesture behavior |
| GPU | a650_gmu.bin, a650_sqe.fw and A650 ZAP firmware files | Adreno 650 firmware family is listed | Exact firmware hashes, boot-time loading path and runtime KGSL/DRM behavior |
| Camera | Sensor module/configuration names GC02M0B, HI846, IMX471, IMX586 and OV02A1B, plus OPlus camera config/tuning files | These camera module variants are represented in the extraction list | Which modules are physically present in this handset, EEPROM/actuator variants, sensor IDs and calibration pairing |
| Audio | audio.primary.kona.so, tfa98xx.cnt, mixer and sound-trigger configuration files | Kona vendor audio stack and TFA98xx-related firmware/configuration are referenced | Exact codec/amplifier population, DSP firmware version, speaker routing and calibration |
| Wi-Fi | odm/etc/wifi/bdwlan.elf | A WLAN board/calibration firmware artifact is listed | WLAN chipset, bus, driver module, firmware interface and MAC/board data behavior |
| Bluetooth | Bluetooth_cal.acdb | Bluetooth calibration data is listed | Controller, transport, firmware, coexistence and power-control path |
| NFC | Manifest lists libnfc-mtp-SN100.conf_20607, libnfc-nci.conf_20607 and libsn100u_fw.so. Official RMX2072 20607 DTS defines qcom,nq-nci at I2C 0x28 on QUPv3 SE0 (1 MHz), IRQ GPIO 34, VEN 12, FIRM 35 and CLKREQ 31. | Strong source-level match for the NQ-NCI / NXP SN100 family; both official 4.19.81 and community 4.19.325 kernels contain the NQ-NCI driver. | Exact SN100 silicon revision, live handset DTB match, optional eSE power GPIO, regulator wiring and current vendor HAL/library build |
| Sensors | Kona configuration names BMI26x, ICM4x6xx, LSM6DSO, SX933x and CCT-related entries | These sensor families/configuration profiles are referenced | Actual fitted sensors, which are AP-side versus SSC/SLPI-owned, and bus/address mapping |
| Charging | oplus_vooc_fw_rt5125.bin, oplus_vooc_fw.bin and charging_thermal_config_default.txt | OPlus VOOC/fast-charge firmware and thermal policy files are referenced | Exact charger, charge-pump, fuel-gauge and battery-protection IC population |
| Fingerprint | goodixfp firmware segments and opluseid firmware segments | Goodix/OPlus secure fingerprint firmware is referenced | Exact sensor revision, SPI wiring, TEE service version and secure enrollment/authentication path |
| Haptics | AW8697 RTP firmware names in the alternate RMX2072 device-tree manifest | An AW8697 haptic firmware family is referenced | Exact controller, bus, driver source path and selected Kconfig |
| Security / DRM | Keymaster and Widevine firmware mappings | Secure services and DRM firmware are part of the vendor stack | Exact TEE firmware, Keymaster/Gatekeeper versions, AVB/RPMB and protected-memory integration |

### Important provenance warning

- The RMX2072-specific device-tree proprietary list says its source firmware is RMX2072_11.F.15.
- The pinned RMX2072 vendor repository commit message says its proprietary blobs were updated to RMX2072_11.F.17.
- This mismatch may reflect a stale extraction list or an unmatched vendor update. It is unresolved; do not combine the two as a known-good set.
- The current SM8250 common device tree's proprietary-file list explicitly identifies Realme GT Neo 3T RMX3371 firmware. It is not a substitute for RMX2072 blobs.
- Shared SM8250 init/ueventd files are useful examples of Qualcomm device-node and module integration, but are not proof of RMX2072 hardware configuration.

## Kernel configuration clues from the 4.19.325 reference

The current SM8250-Common kernel declares a base config pair of vendor/kona-perf_defconfig plus vendor/oplus.config. Its KONA techpack build files also inject display, camera and audio fragments.

Selected source-level findings:

- kona-perf_defconfig sets CONFIG_QCOM_KGSL, CONFIG_SCSI_UFS_QCOM, CONFIG_USB_DWC3_MSM, CONFIG_CNSS2, CONFIG_CNSS2_QMI, CONFIG_NFC_NQ, CONFIG_ION and QTI thermal/BCL options.
- vendor/oplus.config sets CONFIG_OPLUS_SM8250_CHARGER and CONFIG_OPLUS_FINGERPRINT_GOODIX_OPTICAL.
- techpack/display/config/konadisp.conf enables DRM/MSM, SDE, DSI, DP, PLL, rotator and OPlus DRM options.
- techpack/camera/config/konacamera.conf enables the KONA Spectra camera stack.
- techpack/audio/config/konaauto.conf enables QDSP6/APR, ADSP loader, WCD/WSA, SoundWire and several codec paths.
- The same vendor/oplus.config selects Focal FT3658U, Samsung S6SY792 and Synaptics TCM touch variants, but does not select CONFIG_TOUCHPANEL_GOODIX_GT9886. The GT9886 driver and Kconfig symbol exist in the tree, while the RMX2072-specific firmware list names GT9886. A device-specific touch config is therefore required.

These are source configuration clues, not a generated final .config and not a validated RMX2072 build. The current shared config must not be copied wholesale.

## Hardware inventory checklist

| Subsystem | Current status | Next evidence required |
|---|---|---|
| Display | Source evidence found; handset confirmation pending | Panel ID, DTS node, DSI mode, DSC and refresh-rate data |
| Touch | GT9886 firmware evidence found; handset confirmation pending | Controller ID, bus/address, IRQ/reset GPIO and firmware version |
| GPU | Adreno 650 firmware evidence found | Firmware hashes, KGSL userspace ABI and GKI KMI audit |
| Camera | Sensor-module candidates found | Runtime sensor enumeration, module IDs, EEPROM and actuator details |
| Audio | Kona HAL/TFA98xx files found | Codec/amp IDs, DSP firmware, machine driver and calibration |
| Modem | Not device-confirmed | Baseband version, modem firmware provenance, QMI/QRTR/IPA nodes |
| Wi-Fi/Bluetooth | WLAN calibration and BT calibration files found | WLAN chipset/driver, BT controller/transport and firmware |
| NFC | SN100 configuration evidence found | Controller ID, bus, IRQ, eSE and NQ-NCI binding |
| Sensors | Sensor config candidates found | Actual component IDs and SSC/SLPI ownership |
| Charging/power | VOOC firmware evidence found | Charger/gauge/charge-pump IDs, battery profile and thermal trips |
| Storage | UFS support enabled in a shared SM8250 config reference | Physical UFS model, controller binding, partition map and encryption |
| Biometrics | Goodix/OPlus firmware evidence found | Sensor revision, SPI/GPIO and TEE service |
| Security | Keymaster/Widevine references found | Actual TEE/AVB/RPMB state and secure-memory contracts |
| Haptics | AW8697 firmware evidence in alternate device-tree list | Controller ID, bus and driver binding |
| GNSS | No device-specific source mapping yet | GNSS HAL, modem service and runtime location test |

## Required handset capture

- Settings → About device: model, build number, Android version and baseband.
- Build properties, especially ro.product.*, ro.build.fingerprint and ro.vendor.*.
- Partition names and sizes.
- Fastboot variables with serial numbers and sensitive identifiers redacted.
- Boot image header/version and kernel release.
- Bootloader unlock state and AVB state.
- Stock firmware package version and SHA-256 hashes.
- Read-only DTS/DTBO and runtime component information where available.

Never commit IMEI, serial number, MAC addresses, personal data, signing keys or proprietary firmware blobs.

## Related planning documents

- [Driver migration matrix](./DRIVER_MIGRATION_MATRIX.md)
- [Driver dependency map](./DRIVER_DEPENDENCY_MAP.md)
- [Kernel porting strategy](./KERNEL_PORTING.md)


### NFC target DTS cross-check

The official RMX2072 kernel's \`arch/arm64/boot/dts/20607/lito-mtp.dtsi\` defines the NFC controller under \`&qupv3_se0_i2c\`:

~~~dts
nq@28 {
    compatible = "qcom,nq-nci";
    reg = <0x28>;
    qcom,nq-irq = <&tlmm 34 0x00>;
    qcom,nq-ven = <&tlmm 12 0x00>;
    qcom,nq-firm = <&tlmm 35 0x00>;
    qcom,nq-clkreq = <&tlmm 31 0x00>;
    interrupt-parent = <&tlmm>;
    interrupts = <34 0>;
};
~~~

The parent I2C controller is configured for 1 MHz. This is source evidence for the 20607 board configuration; confirm the actual handset's DTB/DTBO before applying it to a new kernel.
