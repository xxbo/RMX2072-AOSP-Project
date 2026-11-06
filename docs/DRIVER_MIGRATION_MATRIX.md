# RMX2072 Driver Migration Matrix — First Pass

> Snapshot: **2026-11-06 UTC**  
> Target: realme X50 Pro Player Edition (RMX2072 / bladerunner_48m), Snapdragon 865 / SM8250 (Kona)  
> Kernel target under investigation: Android 17 ACK / GKI 6.18, pinned at ecdaacc9a0ee87eaf9544e1836d86bd9d590312e  
> Status: **source-reviewed planning matrix only**. No driver in this matrix has been built against GKI 6.18, loaded, booted or hardware-tested on RMX2072.

## 1. How to read this matrix

Evidence is separated into three layers:

- **RMX2072 device evidence** — files in an RMX2072-specific device tree or its proprietary-file manifest. This can identify firmware/configuration candidates, but it is not a substitute for reading the actual handset's DTS, sysfs, boot logs or hardware revision.
- **Kernel-source evidence** — implementation paths and Kconfig/Makefile wiring in the pinned official 4.19.81 source and the community SM8250 4.19.325 reference.
- **ACK/GKI evidence** — what has been explicitly confirmed in the pinned 6.18 source. An upstream subsystem existing does not prove that the exact Kona device binding, vendor interface or firmware path is supported.

The 4.19.325 tree is a **reference implementation**, not a validated RMX2072 build. Its device-tree common repository currently carries a proprietary-file list sourced from RMX3371, and its Kona/Oplus config fragments do not exactly match the RMX2072 GT9886 touch firmware evidence. Do not transplant its blob set or treat its config as the RMX2072 final config.

### Migration dispositions

| Disposition | Meaning |
|---|---|
| Reuse upstream | Prefer the ACK/Linux driver; add device tree, firmware declaration and configuration as needed. |
| Port vendor delta | Keep the hardware-specific OPlus/Qualcomm extension that upstream does not provide; adapt it to 6.18 APIs/KMI. |
| ABI bridge / compatibility | Preserve an existing vendor userspace contract while replacing the old kernel implementation underneath. |
| Userspace / firmware integration | Kernel driver may already exist; work is primarily HAL, firmware, calibration, init, SELinux or VINTF integration. |
| Hardware identification required | Do not select or port a specific driver until the exact component/bus/revision is confirmed. |

## 2. Driver migration matrix

| Priority | Subsystem and RMX2072-specific evidence | Legacy / 4.19 reference evidence | ACK/GKI 6.18 direction | First-pass disposition |
|---|---|---|---|---|
| P0 | **SoC platform foundation** — SM8250/Kona; exact board revision and PMIC configuration still require handset capture. | drivers/clk/qcom, drivers/soc/qcom, drivers/iommu, drivers/regulator, drivers/pinctrl/qcom, drivers/remoteproc. Community tree adds Kona LLCC, RPMh, GLINK/SMEM and OPlus integration. | ACK contains upstream Qualcomm clock, SoC, thermal and IOMMU driver families. Verify each Kona clock/reset, regulator, pinctrl, interconnect, LLCC and SMMU binding against the pinned 6.18 tree and the target DTS. | **Reuse upstream + DTS port.** Do not copy the entire downstream drivers/soc/qcom directory. |
| P0 | **UFS / storage / inline crypto** — UFS is enabled in the SM8250 reference config; physical UFS revision, partition map and crypto capabilities are not yet captured from RMX2072. | drivers/ufs/host, drivers/phy/qualcomm, drivers/crypto; 4.19.325 kona-perf_defconfig sets CONFIG_SCSI_UFSHCD, CONFIG_SCSI_UFS_QCOM, CONFIG_SCSI_UFS_CRYPTO and CONFIG_SCSI_UFS_CRYPTO_QTI. | Prefer ACK UFS/QCOM PHY and upstream block/inline-crypto support. Confirm exact controller compatible strings, ICE/crypto integration, regulators, clocks and fstab/encryption behavior. | **Reuse upstream + DTS/config adaptation.** No reason to port the whole legacy UFS stack before checking 6.18. |
| P0 | **USB / Type-C** — exact connector/PD controller and role-switch wiring still need physical/DTS confirmation. | drivers/usb/dwc3/dwc3-msm.c, Qualcomm USB PHY and Type-C support; 4.19.325 config sets CONFIG_USB_DWC3_MSM=y. | Prefer upstream DWC3 and Qualcomm PHY/glue where present. Audit Type-C, role switch, extcon/USB-PD, gadget functions and Qualcomm-specific DBM/IPA dependencies. | **Reuse upstream + DTS adaptation; port only missing glue.** USB/ADB is an early bring-up requirement. |
| P0 | **Display / panel / backlight** — RMX2072 manifest contains Samsung AMS678UW01 LTM/QDCM calibration filenames; this is strong panel-family evidence, not a physical panel-ID readout. | 4.19.325 techpack/display has Kona DPU/SDE, DSI, DP, PLL and rotator build wiring. konadisp.conf enables CONFIG_DRM_MSM, CONFIG_DRM_MSM_SDE, CONFIG_DRM_MSM_DSI, CONFIG_DRM_MSM_DP and CONFIG_DRM_OPLUS; techpack/display/oplus contains OPlus panel/AOD/ADFR extensions. | GKI 6.18 has DRM/MSM. Map Kona DPU catalog, DSI host/PHY, DSC, panel command tables, backlight and display power sequencing. Do not assume the upstream DRM driver already supports the exact panel mode/calibration. | **Reuse DRM/MSM; port panel and OPlus-specific delta.** Keep display calibration blobs outside Git. |
| P0 | **Touchscreen** — RMX2072-specific manifest names FW_GT9886_SAMSUNG.img and related GT9886 firmware files. | Official 4.19.81: drivers/input/touchscreen/oppo_touchscreen/Goodix/GT9886. Community 4.19.325: drivers/input/touchscreen/oplus_touchscreen/Goodix/GT9886. The latter Makefile builds goodix_drivers_gt9886.o under CONFIG_TOUCHPANEL_GOODIX_GT9886. | Generic upstream input/Goodix support is not automatically equivalent to this OPlus GT9886 implementation (gesture, edge limit, charger/game mode, firmware/config update). Check whether a 6.18-compatible driver exists; otherwise port this controller driver and its minimal OPlus touchpanel framework dependencies. | **Port vendor delta.** Add an RMX2072-specific config selection; do not inherit the unrelated current common-tree touch config blindly. |
| P0 | **Memory allocation / DMA / secure buffers** — shared common-tree ueventd reference exposes /dev/ion, /dev/membuf and KGSL nodes, but that file is not RMX2072-specific. Vendor camera/GPU/audio stacks are likely to have allocator contracts that must be enumerated. | 4.19.81 and 4.19.325 contain Android ION; 4.19.325 kona-perf_defconfig sets CONFIG_ION=y and CONFIG_ION_POOL_AUTO_REFILL=y. Qualcomm SMMU, DMA-BUF and secure-buffer code is spread across drivers/iommu, drivers/soc/qcom and GPU/media paths. | Treat ION as a compatibility migration, not a directory rename. Inventory every /dev/ion ioctl/client and heap type; map to DMA-BUF heaps, CMA/system heaps, secure heap and exporter/importer APIs. Confirm the target GKI 6.18 heap and vendor-hook/KMI surface. | **ABI bridge / compatibility + DMA-BUF migration.** This is a prerequisite for GPU, camera and some audio paths. |
| P0/P1 | **GPU / Adreno 650** — RMX2072 manifest lists a650_gmu.bin, a650_sqe.fw and A650 ZAP firmware. | Both 4.19.81 and 4.19.325 contain drivers/gpu/msm KGSL. 4.19.325 Kona config sets CONFIG_QCOM_KGSL=y; its KGSL Makefile builds core, Adreno, GMU/HFI, IOMMU, shared memory and power control. | Confirmed in pinned GKI: DRM/MSM has an Adreno 650 catalog entry, but legacy drivers/gpu/msm KGSL and include/uapi/linux/msm_kgsl.h are absent. Qualcomm's separately pinned modern KGSL is a Linux 7.2 external-module reference, **not** a proven GKI 6.18 module. | **Two-route decision required.** First prototype modern KGSL against 6.18 to preserve /dev/kgsl-3d0/KGSL userspace ABI; compare with a DRM/MSM userspace adaptation only if the vendor stack can be replaced. Audit KMI, GMU, QFPROM/SCM, IOMMU and DMA-BUF before porting. |
| P1 | **Modem / Qualcomm IPC / data path** — RMX2072-specific modem firmware and exact transport inventory remain open. | drivers/soc/qcom contains GLINK, SMEM, SMP2P, QMI helpers, subsystem restart, MDT loader, IPA/RMNET and modem support; drivers/remoteproc contains Qualcomm Q6/remoteproc paths. QRTR is a separate networking layer and must be audited alongside GLINK/QMI. | Reuse upstream GLINK/SMEM/QRTR/remoteproc/IPA pieces where their exact interfaces are present. Audit downstream QMI services, modem boot/SSR, MHI, IPA offload, RMNET and vendor device nodes against the existing radio/data HALs. | **Reuse upstream + port vendor IPC/IPA delta.** High integration risk; validate modem boot, calls, SMS and mobile data separately. |
| P1 | **Wi-Fi** — RMX2072-specific manifest includes odm/etc/wifi/bdwlan.elf; exact WLAN chipset and driver module are not identified by this file alone. | 4.19.81 and 4.19.325 contain drivers/net/wireless/cnss2 and Qualcomm ICNSS/QMI support. 4.19.325 Kona config sets CONFIG_CNSS2=y and CONFIG_CNSS2_QMI=y. | Identify the actual WLAN device/firmware interface before choosing ath11k, CNSS or an external Qualcomm driver. Confirm whether the required WLAN datapath is upstream or a proprietary/out-of-tree module, and audit its KMI/firmware/PCIe dependencies. | **Hardware identification + likely vendor-module port/adaptation.** Do not infer the RMX2072 chipset from qca_cld3_qca6390/qca6490 names in the different RMX3371 common-tree init file. |
| P1 | **Bluetooth** — device-specific manifest has Bluetooth calibration data; exact controller/transport and firmware mapping remain unknown. | Qualcomm IPC and Bluetooth transport support exists in the 4.19 source families; the shared common tree contains SMD/BT device-node conventions, but is not RMX2072 hardware proof. | Prefer upstream Bluetooth HCI/transport drivers where they match the actual controller. Check UART/SMD/GLINK transport, btpower, coexistence, suspend/wake and Bluetooth audio HAL compatibility. | **Hardware identification + userspace/firmware integration.** Avoid a speculative chipset-specific port. |
| P1 | **Charging / battery / VOOC** — RMX2072 manifest lists oplus_vooc_fw_rt5125.bin, another VOOC firmware and charging thermal configuration. Exact charger/gauge IC population still needs DTS or handset confirmation. | Official 4.19.81 uses drivers/power/oppo; 4.19.325 uses drivers/power/oplus. Its charger Makefile has a CONFIG_OPLUS_SM8250_CHARGER path including oplus_battery_msm8250, charge-pump, DA9313, MP2650, USB-temperature and short-circuit components. | Keep upstream regulator, power_supply, I2C/SPMI and USB-PD foundations. Port only the OPlus charger/gauge/VOOC pieces required by the identified chips and vendor charging HAL. | **Port vendor delta.** Treat fast charging and thermal protection as safety-critical; test current/voltage/temperature limits before enabling fast-charge modes. |
| P1 | **Thermal / performance / power management** — target-specific thermal zones and trip points are not yet captured. | 4.19.325 has Qualcomm TSENS, ADC-TM, BCL, LMH/DCVS, QMI cooling and Kona thermal support; kona-perf_defconfig enables QTI BCL/thermal-related options. | Reuse ACK thermal framework, cpufreq/devfreq, regulator and Qualcomm TSENS/BCL/LMH drivers where supported. Port missing QMI cooling or vendor policy integration only after tracing the exact sysfs/thermal HAL contract. | **Reuse upstream + policy/DTS adaptation.** Validate thermal throttling and sustained load, not just temperature readout. |
| P1/P2 | **Audio / DSP / codec / amplifier** — RMX2072 manifest lists audio.primary.kona.so, tfa98xx.cnt and audio configuration files. These identify vendor audio dependencies but do not by themselves prove every codec in the shared KONA config is fitted. | 4.19.325 techpack/audio has KONA ASoC, Q6 DSP and APR/GLINK build paths. konaauto.conf enables QDSP6/APR, ADSP loader, WCD/WSA and TFA98xx-related options. | Audit ACK ASoC/Q6DSP/remoteproc/GLINK support and codec drivers against the exact audio HAL and calibration files. Keep the existing vendor audio HAL only if its kernel-facing PCM/AFE/control interfaces remain compatible. | **Reuse upstream foundations + port required Q6/codec/vendor delta.** Audio is a kernel + DSP firmware + calibration + HAL integration task. |
| P2 | **Camera / ISP / sensors** — RMX2072 manifest lists camera config and sensor-module candidates: GC02M0B, HI846, IMX471, IMX586 and OV02A1B, plus tuning/configuration files. This list does not prove every module is installed in every handset. | Official Q source exposes only a techpack/stub placeholder. 4.19.325 has KONA techpack/camera with Spectra modules (cam_cpas, cam_isp, cam_sensor_module, cam_smmu, cam_req_mgr, cam_sync, cam_jpeg, etc.); konacamera.conf sets CONFIG_SPECTRA_CAMERA. | Upstream V4L2/CAMSS presence, if available, is not a drop-in replacement for the Qualcomm Spectra/Camera HAL pipeline. Map CPAS, CSIPHY/CSID, ISP/VFE, CCI, SMMU, EEPROM/actuator and camera memory interfaces. | **Port a coherent camera pipeline, not isolated sensor files.** Very high risk; preserve RMX2072 calibration/tuning blobs outside Git. |
| P2 | **Fingerprint / secure touch** — manifest lists goodixfp.* and opluseid.* firmware files, indicating Goodix/OPlus secure integration. | 4.19.81 has Goodix fingerprint driver families; 4.19.325 drivers/input/oplus_fp_drivers/goodix_optical_fp is wired by CONFIG_OPLUS_FINGERPRINT_GOODIX_OPTICAL, which is enabled in its Oplus fragment. | Confirm the exact sensor interface (SPI/GPIO/IRQ), TEE/QSEE communication and secure-world firmware. Port the Goodix optical driver and the minimum OPlus secure framework required; keep the vendor biometric HAL and TEE contract separate. | **Port vendor driver + secure-service integration.** Do not treat firmware presence as proof of a working TEE path. |
| P2 | **Sensors / sensor hub** — RMX2072 manifest has Kona sensor configuration candidates for BMI26x, ICM4x6xx, LSM6DSO, SX933x and CCT-related data. Exact populated sensor set is not confirmed. | Qualcomm SSC/SLPI, QMI/GLINK and sensor-service paths exist in the downstream source family; direct I2C/IIO drivers may be used for selected sensors. | Determine whether each sensor is owned by SLPI/SSC firmware or directly by AP-side I2C/SPI. Reuse upstream IIO drivers only for directly attached devices; preserve sensor-hub firmware and HAL protocols where used. | **Hardware identification + firmware/HAL integration.** Avoid porting all sensor drivers in bulk. |
| P2 | **NFC** — RMX2072 manifest names libnfc-mtp-SN100.conf_20607, suggesting an NXP SN100 family configuration. | drivers/nfc/nq-nci.c and drivers/nfc/nxp-nci are present; 4.19.325 kona-perf_defconfig sets CONFIG_NFC_NQ=y. | Confirm exact controller, bus, GPIO/IRQ, eSE and firmware-download behavior. Check whether the required NQ-NCI driver exists in ACK 6.18; use upstream NXP NCI only if the protocol and device binding match. | **Likely NQ-NCI vendor adaptation or upstream NCI reuse after bus/protocol verification.** |
| P2 | **Haptics** — one RMX2072 device-tree manifest includes AW8697 RTP firmware names. This is firmware-level evidence, not yet a confirmed driver binding. | Exact AW8697 driver source path and selected Kconfig were not established in this pass. | Search the pinned kernel trees and device DTS for compatible string, bus and driver before selecting a port. | **Hardware/source identification required.** No driver migration decision yet. |
| P2 | **Security / TEE / Keymaster / DRM** — RMX2072-specific manifest includes Keymaster and Widevine firmware; device manifest declares a Keymaster HAL. | Qualcomm SCM, QSEE/QTEE shared-memory and secure-buffer support exists in the downstream source families. | Reuse ACK SCM/firmware foundations; separately audit QSEECom/QTEE/secure buffer, keymaster/gatekeeper, RPMB, Widevine and protected camera/GPU memory contracts. | **Vendor-dependent integration.** Secure-world firmware and userspace HAL compatibility are separate from ordinary driver compilation. |
| P2 | **GNSS** — no exact RMX2072 GNSS controller or dedicated firmware mapping has been established from the current source set. | Likely coupled to modem/Qualcomm location services; no device-specific kernel driver decision yet. | Trace the actual GNSS HAL, modem QMI services, device nodes and firmware. | **Hardware/userspace identification required.** Do not invent a standalone GNSS driver port. |

## 3. What the current 4.19.325 reference config actually tells us

The current SM8250-Common kernel's declared base config is vendor/kona-perf_defconfig plus vendor/oplus.config. Its KONA techpack build systems also inject subsystem-specific fragments:

- techpack/display/config/konadisp.conf — DRM/MSM, SDE, DSI, DP, PLL, rotator and OPlus DRM.
- techpack/camera/config/konacamera.conf — Spectra camera.
- techpack/audio/config/konaauto.conf — QDSP6, APR, ADSP loader, WCD/WSA, SoundWire and codec options.

The base/fragment files explicitly show, among others:

- CONFIG_QCOM_KGSL=y
- CONFIG_SCSI_UFS_QCOM=y
- CONFIG_USB_DWC3_MSM=y
- CONFIG_CNSS2=y, CONFIG_CNSS2_QMI=y
- CONFIG_NFC_NQ=y
- CONFIG_ION=y
- CONFIG_OPLUS_SM8250_CHARGER=y
- CONFIG_OPLUS_FINGERPRINT_GOODIX_OPTICAL=y

Important mismatch: the same vendor/oplus.config enables Focal FT3658U, Samsung S6SY792 and Synaptics TCM touch variants, but does not select CONFIG_TOUCHPANEL_GOODIX_GT9886. The GT9886 driver and Kconfig symbol exist in the tree, and the RMX2072 firmware manifest names GT9886 firmware. This is a concrete reason to create a **device-specific config fragment** rather than treating the common-tree config as ready for RMX2072.

These config observations are source evidence only. The final merged .config must be generated and inspected from the exact build system; Makefile-injected KONA fragments are part of the configuration story.

## 4. First implementation order

1. **Freeze the hardware and vendor baseline:** resolve RMX2072 firmware F.15/F.17 provenance, capture actual DTS/DTBO and component IDs, and establish a recoverable stock baseline.
2. **Create the 6.18 platform base:** Kona DTS, clocks/resets, PMIC/regulators, pinctrl, SMMU/IOMMU, LLCC/interconnect, UFS and USB/ADB.
3. **Bring up display and touch:** DRM/MSM + exact Samsung panel sequence + GT9886 driver/config.
4. **Resolve memory and GPU together:** ION client inventory → DMA-BUF/secure heap plan → KGSL-vs-DRM decision → A650 GMU/KMI prototype.
5. **Bring up modem and wireless:** GLINK/SMEM/QRTR/QMI/remoteproc/IPA first, then WLAN and Bluetooth transports.
6. **Port audio and power/thermal:** Q6/ASoC and OPlus charger/VOOC with safety checks.
7. **Port camera and remaining peripherals:** Spectra pipeline, sensors, fingerprint, NFC, haptics and secure-world services.

Do not start with the full camera or audio stack before the memory, IOMMU and Qualcomm IPC foundations are understood.

## 5. Acceptance criteria for any migrated driver

A driver is not complete when it merely compiles. Record all of the following:

1. Exact source repository, immutable commit, file-level license and patch provenance.
2. Required Kconfig symbols, device-tree bindings, firmware names and module dependencies.
3. Undefined symbols versus the exact GKI exported-symbol/KMI lists; module ABI and signing status.
4. Reproducible module build against the pinned 6.18 toolchain/config.
5. Successful module load and probe on the target device, with clean kernel logs.
6. Correct device nodes/sysfs interfaces and compatibility with the intended vendor HAL/userspace.
7. Functional test, suspend/resume test, thermal/power behavior and failure/recovery test.
8. Test date, system/vendor fingerprints, kernel SHA, config SHA and retained logs.

## 6. Known blockers and explicit non-goals

- No physical-device capture has yet confirmed the exact panel, sensor population, WLAN chip, Bluetooth transport, charger ICs, fingerprint revision or partition/boot layout.
- The RMX2072 device-tree proprietary list says firmware source RMX2072_11.F.15; the pinned vendor-tree update says RMX2072_11.F.17. Resolve before combining them.
- The current shared SM8250 common device-tree proprietary list is from RMX3371. It is not an RMX2072 vendor blob source.
- The current SM8250 common tree is useful for source/configuration research, but its device config and module list are not automatically RMX2072-specific.
- Qualcomm Linux 7.2 KGSL is a reference implementation only; it is not evidence of GKI 6.18 KMI compatibility.
- No proprietary firmware, vendor binaries, factory images, keys or personal device dumps belong in this repository.

## 7. Pinned references

- [Official RMX2072 Android Q kernel — 4.19.81](https://github.com/realme-kernel-opensource/realmeX50Pro-5GPlay_AndroidQ-kernel-source/tree/24a15224fbae8ab0e8ba29a9046c06ee7a9f53a4)
- [SM8250-Common kernel — 4.19.325](https://github.com/SM8250-Common/android_kernel_realme_sm8250/tree/b76eb6c93add8152b1aa873da0d8d7f495cccab0)
- [RMX2072 device tree proprietary manifest](https://github.com/IGaganpreetSingh/android_device_realme_bladerunner_48m/blob/08afb1d784dd568fa04ca462684a350b37e2bf4a/proprietary-files.txt)
- [Current shared SM8250 common device tree](https://github.com/SM8250-Common/android_device_realme_sm8250-common/tree/681bfa28e36003fddc004bfebef491234505adbc) — source reference only; its blob list is RMX3371.
- [Android 17 GKI 6.18 pinned source](https://android.googlesource.com/kernel/common/+/ecdaacc9a0ee87eaf9544e1836d86bd9d590312e/)
- [KGSL / Adreno 650 research](./KGSL_ADRENO_RESEARCH.md)
- [Kernel tree structural findings](./KERNEL_TREE_DIFF_FINDINGS.md)
- [Hardware and source inventory](./HARDWARE_INVENTORY.md)
- [Driver dependency map](./DRIVER_DEPENDENCY_MAP.md)
