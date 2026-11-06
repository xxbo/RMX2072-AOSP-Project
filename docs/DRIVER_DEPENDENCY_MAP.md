# RMX2072 Driver Dependency Map — First Pass

> Snapshot: **2026-11-06 UTC**  
> Basis: pinned RMX2072 4.19.81 source, SM8250 4.19.325 reference, RMX2072-specific device-tree/vendor manifests and the pinned Android 17 GKI 6.18 reference.  
> Status: architecture map for planning; exact DTS bindings, module symbols and physical component revisions remain to be verified.

## 1. Why dependency order matters

A phone kernel is not a bag of independent drivers. GPU, display, camera and audio all depend on lower-level services such as clocks, regulators, DMA, IOMMU and firmware/remote-processor communication. If those foundations are incomplete, porting an upper-level driver first creates misleading build success followed by probe failures, memory faults or runtime instability.

The highest-value preparation work is therefore to identify shared foundations and make their interfaces explicit before porting the feature drivers.

## 2. High-level dependency graph

~~~mermaid
flowchart TD
    BOOT["Boot chain / boot image / DTB / DTBO"] --> SOC["SM8250 SoC foundation"]
    SOC --> PM["PMIC / regulators / clocks / resets / pinctrl / interconnect / LLCC"]
    SOC --> MEM["DMA / DMA-BUF / SMMU-IOMMU / secure memory"]
    SOC --> IPC["Qualcomm IPC: SMEM / GLINK / SMP2P / QRTR / QMI"]
    SOC --> UFS["UFS / PHY / inline crypto"]
    SOC --> USB["DWC3 / USB PHY / Type-C / role switch"]

    PM --> DISP["DRM/MSM DPU / DSI / panel / backlight"]
    PM --> TOUCH["GT9886 touch / IRQ / I2C / firmware"]
    PM --> CHG["Charger / fuel gauge / VOOC"]
    PM --> THERM["TSENS / BCL / LMH / thermal policy"]

    MEM --> GPU["Adreno 650 / KGSL or DRM-MSM"]
    MEM --> DISP
    MEM --> CAM["Spectra camera / ISP / camera buffers"]
    MEM --> AUDIO["Audio DSP / PCM buffers"]

    IPC --> MODEM["Modem / SSR / MHI / IPA / RMNET"]
    IPC --> WLAN["CNSS / WLAN firmware and datapath"]
    IPC --> AUDIO
    IPC --> SENSOR["SSC / SLPI / sensor hub"]
    IPC --> CAM

    USB --> MODEM
    PM --> WLAN
    PM --> AUDIO
    PM --> SENSOR
    PM --> NFC["NQ-NCI / NFC controller"]
    PM --> FP["Goodix optical fingerprint"]
    PM --> HAPTIC["Haptic controller"]

    FP --> TEE["SCM / QSEE / QTEE / secure service"]
    GPU --> TEE
    CAM --> TEE
    TEE --> DRM["Keymaster / Gatekeeper / Widevine / protected content"]
~~~

The graph is conceptual, not a generated probe graph. It shows the major shared dependencies to audit; individual devices may use different buses or firmware transports.

## 3. Dependency groups

### A. Boot and SoC foundation

**Must precede almost everything else.**

- Boot image format, bootloader hand-off, DTB/DTBO and reserved-memory layout.
- Kona clocks, resets, regulators, PMIC/SPMI, pinctrl and interconnect.
- LLCC, SMMU/IOMMU, DMA mapping and memory carve-outs.
- UFS and USB/ADB for reliable development and recovery.
- Qualcomm firmware loader and remoteproc infrastructure where required.

**Gate:** the kernel boots reliably, mounts the intended partitions, exposes a stable ADB path, and does not report unresolved critical clocks, regulators, IOMMU or firmware-probe failures.

### B. Memory and DMA contract

**Must be resolved before GPU, camera and full multimedia.**

Legacy Android Qualcomm stacks may use ION heap IDs, private allocation ioctls, secure heaps and vendor-specific DMA-BUF behavior. The target GKI architecture uses modern DMA-BUF/heap and memory-management interfaces. A migration must inventory clients and contracts, not just replace one allocator name with another.

Audit at least:

- ION ioctl callers in KGSL, camera, audio, video and vendor userspace.
- Heap types, alignment, cache policy, secure/protected allocation and buffer ownership.
- DMA-BUF exporter/importer behavior and attachment lifetime.
- SMMU domains, stream IDs, IOVA mapping, page-table formats and secure contexts.
- GKI vendor hooks, KMI exports and any struct-layout dependency.

**Gate:** representative non-secure and secure buffer allocation/import/export works with the exact consumers that will be retained.

### C. Graphics and display

**Two related but distinct paths.**

- Display path: DRM/MSM → DPU/SDE → DSI host/PHY → panel → backlight/brightness.
- GPU path: KGSL or DRM/MSM Adreno → GMU/HFI and A650 firmware → IOMMU/DMA-BUF → userspace graphics driver.

The existing RMX2072 vendor stack has a KGSL-oriented userspace contract. GKI 6.18 contains DRM/MSM and an Adreno 650 catalog entry but not the legacy KGSL device/UAPI path. Therefore, the GPU decision must be made separately from display bring-up.

**Gate:** stable boot animation/UI, correct panel mode and brightness, GPU submission, suspend/resume, and no IOMMU faults. A DRM/MSM source tree existing is not proof that the old KGSL userspace can use it.

### D. Qualcomm IPC, modem and wireless

The following components form a dependency chain rather than isolated features:

- SMEM / SMP2P and shared-memory channels.
- GLINK and QRTR transports.
- QMI services and subsystem restart/SSR.
- Remoteproc and modem/ADSP/SLPI firmware loading.
- IPA, GSI, RMNET and MHI where the device actually uses them.
- CNSS/ICNSS and the WLAN firmware/datapath.
- Bluetooth HCI transport, power and coexistence.

**Gate:** modem boots and recovers from subsystem restart; SIM, calls, SMS and mobile data work; Wi-Fi and Bluetooth work through suspend/resume. Do not infer the RMX2072 WLAN chipset from a different model's common-tree module list.

### E. Audio

Audio is a kernel + remote DSP + codec + calibration + HAL system:

1. Android audio HAL and policy.
2. ALSA/ASoC machine and codec drivers.
3. Q6 DSP/AFE/ASM and APR transport.
4. ADSP firmware loading, PDR/notifier and GLINK/RPMsg dependencies.
5. SoundWire/SLIMbus or other actual codec bus.
6. Speaker amplifier, calibration and device-specific mixer paths.

The RMX2072 manifest names a Kona audio HAL and TFA98xx firmware/configuration. The shared KONA audio fragment is a source reference; the exact codec population still needs handset/DTS confirmation.

**Gate:** earpiece, receiver, speakers, microphones, wired/USB audio, Bluetooth audio, sound-trigger and suspend/resume are tested separately.

### F. Camera and video

The camera path has a wide dependency surface:

- Camera provider/HAL and vendor camera libraries.
- Camera request manager, CPAS, CAM SMMU, sync and memory manager.
- CSIPHY/CSID, CCI/I2C, sensor, EEPROM, actuator and flash.
- ISP/VFE/IFE, JPEG and any DSP/CV processing path.
- Sensor module binaries, tuning data and per-module configuration.
- Secure/protected camera buffers where required.

The RMX2072 proprietary manifest lists multiple sensor-module candidates. That does not mean every listed sensor is present in a single handset. The community KONA Spectra tree is the relevant downstream reference; generic upstream CAMSS should not be assumed to replace the full vendor Spectra pipeline.

**Gate:** each physically present camera is enumerated and tested for preview, capture, video, focus/exposure, flash and camera switching. Preserve exact tuning provenance.

### G. Power, thermal and charging

These components interact continuously:

- PMIC, regulators, battery gauge and charger.
- USB Type-C/PD and VOOC fast-charge controller/firmware.
- Power-supply class and vendor charging policy.
- TSENS, ADC-TM, BCL, LMH/DCVS and thermal zones.
- CPUFreq, Devfreq, GPU bandwidth and cooling devices.

**Gate:** charging state/current/voltage/temperature are sane, thermal trips throttle correctly, suspend current is measured, and fast-charge protection is validated before enabling high-power modes.

### H. Sensors, NFC, biometrics and haptics

These are lower in the first boot sequence but still depend on common foundations:

- Sensors may be direct I2C/SPI/IIO devices or owned by the Qualcomm SSC/SLPI sensor hub.
- NFC has controller bus, IRQ, power, NCI/NQ-NCI and eSE/firmware dependencies.
- Goodix optical fingerprint uses SPI/GPIO/IRQ plus secure-world communication.
- Haptics require the correct controller bus, power and firmware.

**Gate:** identify each physical component and bus first; then test wake behavior, suspend/resume, firmware loading and HAL communication.

## 4. Recommended migration order derived from the graph

| Wave | Scope | Why this order | Exit gate |
|---|---|---|---|
| 0 — Device facts | Exact firmware, DTS/DTBO, partition/boot metadata, component IDs, recovery baseline | Prevents building against a mismatched board/vendor set | Device identity and recovery facts recorded |
| 1 — Platform base | Kona DTS, clocks, resets, PMIC, regulators, pinctrl, interconnect, LLCC, SMMU, UFS, USB/ADB | Every later subsystem depends on this layer | Stable boot, storage, ADB and clean critical probe logs |
| 2 — Memory + display + touch | DMA-BUF/secure heaps, DRM/MSM, panel, GT9886 | Provides a visible and interactive system and establishes buffer contracts | UI, brightness, touch, suspend/resume |
| 3 — GPU | KGSL-vs-DRM decision, A650 firmware/GMU, KMI and memory path | GPU shares memory/IOMMU with display and camera | GPU workload and graphics HAL pass |
| 4 — IPC + modem + wireless | SMEM/GLINK/QRTR/QMI/remoteproc/IPA, WLAN and Bluetooth | Establishes Qualcomm remote subsystem communication | Calls/data/Wi-Fi/BT and subsystem recovery |
| 5 — Power + thermal + audio | Charger/VOOC, fuel gauge, TSENS/BCL/LMH, Q6/ASoC | Power safety and DSP dependencies need platform/IPC foundations | Safe charging, thermal control and full audio route tests |
| 6 — Camera + remaining peripherals | Spectra, sensors, fingerprint, NFC, haptics, secure services | These depend on stable memory, IPC, power and secure-world foundations | Per-component hardware tests and logs |

This order is for the GKI research track. It does not replace the safer project-level rule: first reproduce a known-compatible legacy kernel/vendor baseline, and do not combine the first Android 17 GSI experiment with an unvalidated 6.x kernel.

## 5. Evidence still required

The following items block a device-exact dependency graph:

- Actual RMX2072 firmware build and a matched F.15/F.17 vendor extraction set.
- Actual DTB/DTBO and kernel command line from the handset.
- Panel ID, touch controller ID and touch bus/address.
- Camera sensor enumeration and module/EEPROM IDs.
- WLAN chipset and driver/firmware binding; Bluetooth controller and transport.
- Charger, fuel-gauge, VOOC and haptic controller IDs.
- Sensor-hub ownership versus direct AP-side sensor buses.
- Boot image header, partition map, AVB state and verified recovery route.
- Vendor HAL and firmware versions for the exact handset build.

Do not fill these fields from a different SM8250 handset or from a shared common-tree example.

## 6. Related project documents

- [Driver migration matrix](./DRIVER_MIGRATION_MATRIX.md)
- [Kernel porting strategy](./KERNEL_PORTING.md)
- [GKI migration research](./GKI_MIGRATION.md)
- [Hardware and source inventory](./HARDWARE_INVENTORY.md)
- [KGSL / Adreno 650 research](./KGSL_ADRENO_RESEARCH.md)
- [Source inventory and provenance](./SOURCE_INVENTORY.md)


## 7. Experimental pilot selection

NQ-NCI / SN100 is selected as the first port experiment because the official RMX2072 20607 DTS supplies an unusually concrete hardware contract (I2C address, controller, IRQ and GPIO assignments), the proprietary manifest contains matching SN100 configuration/firmware references, and a downstream implementation already exists. This is a **porting-method pilot**, not a claim that NFC is more important to boot than the P0 platform, display or memory foundations.

The pilot is intentionally isolated as an external module. Its first compile is designed to reveal 6.18 source/API compatibility; the next phase must check the imported-symbol list against the exact GKI KMI, then convert legacy GPIO calls if required. It must preserve the vendor /dev/nq-nci and ioctl ABI until the corresponding userspace contract has been verified.

See [the NQ-NCI experimental port](../experiments/nfc_nq/README.md) and its [userspace ABI inventory](../experiments/nfc_nq/ABI.md).
