# RMX2072 6.18 adaptation review after the second trial

This review describes the November 7 trial. Later boots established kernel execution, USB, warm UFS and the Android first-stage handoff. See the [current physical results](../plan.md#verified-starting-point) and [M1 work list](../plan.md#next-work-on-m1).

This review uses the actual configuration from platform build 42233938138, the checked-in USB diagnostic DTS, the selected stock DTB/DTBO and root captures from the F.20 handset. It describes remaining work beyond logging. It does not diagnose the restart loop: physical execution of the 6.18 kernel is still unproven. Stock-kernel debug Android has been recovered and verified.

The configuration snapshot is [machine-readable](../build/device/bootstrap-adaptation-audit-2026-11-07.json). Its SHA-256 is `fa09c1232f575baa68cd507f7e2707bd3dee1143b1f12dccc00e24792900f2d2`. The audit script records actual built values; requested fragment assignments alone are insufficient.

## Confirmed configuration and board gaps

| Area | Current evidence | Required adaptation / validation |
|---|---|---|
| SMEM hardware mutex | `QCOM_SMEM=y`, generic `HWSPINLOCK=y`, but `HWSPINLOCK_QCOM=n`. Inherited SM8250 SMEM references `tcsr_mutex` lock 3; the SMEM probe obtains a hardware lock before exposing shared memory. | Enable the Qualcomm hardware-lock provider built-in, rebuild and verify its actual assignment. Confirm SMEM probes at runtime. This is a concrete dependency gap, not a proven cause of reboot. |
| Firmware handoff / CPU / power | PSCI, CPU power domains, firmware reservations, RPMh and SM8250 clocks come from upstream bindings plus captured board ranges. They have not been runtime-validated with OEM firmware. | Validate DTB/DTBO selection, load handoff, reserved ranges, interrupts/timer, CPU bring-up and idle/reset behavior. Distinguish bootloader failure, early panic and watchdog reset before selecting a fix. |
| PMIC and board wiring | The project DTS includes `sm8250.dtsi`, three RPMh USB regulator definitions and a UART/USB diagnostic setup. It does not instantiate complete PM8150-family board peripheral trees. | Translate the actual board's PMIC/SPMI, pins, key/reset, regulator consumers and power sequencing. Match upstream bindings instead of copying downstream nodes verbatim. Not every PMIC peripheral is necessary for a RAM-only USB milestone. |
| USB | DWC3/QCOM, HS PHY and ACM gadget are built-in. DTS forces peripheral/high-speed operation with captured rails; no diagnostic USB device has enumerated yet. | Validate PHY power/reset/clock dependencies and UDC registration. Keep this minimal path before adding Type-C role switching, charger/PD/extcon and Android FunctionFS/ADB. An ACM shell is a different userspace service from ADB. |
| Storage and encryption | UFS/QCOM, UFS PHY, inline-crypto engine, dm-default-key, fscrypt and dm-verity are built, but the diagnostic DTS leaves storage disabled. | Add exact UFS supplies/reset/PHY/clock/interconnect bindings and firmware crypto/SCM integration. First prove read-only enumeration and partition access, then validate dynamic partitions, metadata/FBE and key services. Existing configuration options do not establish vendor keymaster compatibility. |
| Android first-stage boot | The current initramfs intentionally mounts no handset filesystem. There is no vendor_boot/init_boot/vendor_dlkm physical partition. Binder IPC/binderfs are built. `DEVTMPFS=n`; the diagnostic init creates its few device nodes manually. | Design boot-v2 ramdisk first-stage init, device-node creation/ueventd, fstab, logical partitions, firmware and early module placement. DEVTMPFS being off is not automatically an Android blocker: Android init can create devices. Do not load the stock 4.19 modules into 6.18. |
| Display and panel | `DRM_MSM=n`. Diagnostic DTS has no enabled display pipeline or panel. Live stock evidence identifies the RM19795 Samsung panel path, with actual 1080x2400 60/90-Hz DSC modes. | Enable/build the appropriate DPU/DSI/PHY/clock chain, implement the exact panel commands/reset/supplies and initially one conservative mode. Translate actual DSC/timing values; do not infer them from a panel filename. Then validate brightness and suspend/resume. |
| GPU, allocator and HWC | Generic ACK lacks legacy KGSL. `DMABUF_HEAPS=y`, but system/CMA heap providers are off; `QCOM_LLCC=n`. Stock uses KGSL/ION-oriented vendor graphics. | Select a coherent kernel/userspace route: port a compatible KGSL stack or replace/adapt graphics userspace for DRM/MSM. Audit allocator heaps, IOMMU, secure buffers, firmware, LLCC dependencies, gralloc and HWC display ioctls together. Enabling DRM/MSM does not make the stock graphics HAL work. |
| Touch | Actual GT9886 implementation/firmware and I2C 8 address 0x5d were captured earlier. It is not present in the USB diagnostic board integration. | Port the controller plus required Oplus touch framework, IRQ/reset/pinctrl, regulators and firmware path. Generic Goodix driver presence is insufficient proof of support for this controller. |
| DSP / modem / audio / wireless | Q6V5 ADSP/MSS/PAS options are off in the platform artifact; remote processors remain disabled in the diagnostic DTS. | Stage SMEM/SMP2P/GLINK/QRTR/remoteproc, exact firmware and secure loading, then audit vendor HAL contracts and actual wireless transports. These are deliberately deferred for USB-only boot, not completed subsystems. |
| Battery / thermal / power management | No complete board battery/charger/thermal implementation has been integrated into the diagnostic target. | Establish temperature/battery reporting, basic charging, thermal limits and reliable poweroff before sustained Android/GPU load. Port VOOC and performance policy later against the identified chips and HALs. |

The hardware mutex dependency is directly visible in the pinned sources: [SM8250 SMEM/hwlocks DTS](https://github.com/xxbo/RMX2072-AOSP-Project/blob/cfa72fb3d7f89372c7e449a4de2477551ea4c29c/arch/arm64/boot/dts/qcom/sm8250.dtsi), [SMEM probe](https://github.com/xxbo/RMX2072-AOSP-Project/blob/cfa72fb3d7f89372c7e449a4de2477551ea4c29c/drivers/soc/qcom/smem.c), and [Qualcomm hardware-lock option](https://github.com/xxbo/RMX2072-AOSP-Project/blob/cfa72fb3d7f89372c7e449a4de2477551ea4c29c/drivers/hwspinlock/Kconfig). Neither a disabled later-stage driver nor a missing Android HAL should be labeled the cause of the present early restart without runtime evidence.

## What most directly blocks an Android desktop

1. Stable kernel/firmware handoff and a working USB diagnostic path.
2. UFS plus Android first-stage mounts and encryption/key-service compatibility.
3. Panel/display output and a coherent allocator/GPU/gralloc/HWC route.
4. Touch input; use an explicitly verified alternative input path only for early testing.
5. Basic battery/thermal supervision, followed by modem, Wi-Fi, audio, sensors and other features.

The biggest desktop work item is the graphics contract, not NFC. The strict NFC build and CRC audit do not validate the much larger GPU/display userspace ABI. Camera, fingerprint and NFC hardware tests can follow the first stable desktop. Keep the minimal USB-only DTS separate from a later Android-capable board target so added devices do not obscure the early-boot problem.

## Independent GSI integration blockers

The selected Google Android 17 ARM64+GMS image is not a replacement for the vendor stack. Inspection already found FCM 5 missing from its framework matrices, no bundled VNDK 30 APEX, and a roughly 1.02-GiB dynamic-partition capacity deficit if all current logical partitions are retained. See [GSI preflight](GSI_PREFLIGHT_2026-11-06.md). A successful 6.18 USB boot does not resolve these issues; do not raise the vendor's declared FCM number as a substitute for implementing its contracts.

## Next implementation scope

First prepare a platform revision with the Qualcomm hardware mutex built-in and check its actual compiled result. Audit board PMIC/clock/USB dependencies alongside the independent log-path work. Do not enable all multimedia and remote processors in that revision. After establishing kernel execution and USB, introduce UFS as a separate read-only milestone. In parallel, inventory the stock graphics HAL's exact KGSL/ION/display UAPI dependencies before committing to a GPU route. No configuration, kernel build or phone partition was changed by this review.
