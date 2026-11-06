# Build and device-test execution

The execution path is GitHub Actions for kernel/driver builds, a selected official Google Android 17 ARM64 GSI for the system layer, and the locally connected RMX2072 for flashing and hardware tests. A local full AOSP build host is not required for this phase.

## Legacy build gate

`Legacy Kernel Build` is manually triggered. Run `stage=config` first; use `stage=kernel` after configuration validation.

Configuration validation passed in [run 42224170969](https://github.com/xxbo/RMX2072-AOSP-Project/actions/runs/42224170969). The first full build ([run 42224859055](https://github.com/xxbo/RMX2072-AOSP-Project/actions/runs/42224859055)) failed on one Clang `-Werror,-Wmisleading-indentation` diagnostic in `goodix_common.c:277`. A minimal whitespace-only patch aligns the unconditional statement; warnings remain enabled. The build applies the checked-in patch with `git apply --check` and records its SHA-256. A corrected full run is required before claiming success.

Inputs are fixed by `sources/SOURCE_LOCK.json` and `build/legacy-kernel.json`. The selected community 4.19.325 source has the complete Techpack reference, while the official Q/S trees contain Techpack stubs. This is a candidate build, not a proven F.20 source match. The actual handset runs 4.19.157-perf+.

The build uses `vendor/kona-perf_defconfig`, `vendor/oplus.config` and a small project-owned GT9886 fragment supported by the running F.20 configuration. It verifies required assignments in the generated `.config`. Makefile-injected Techpack flags still need comparison with that generated config; this does not solve all source-pairing gaps.

Clang r416183b is pinned to an immutable official prebuilt commit and selected because the kernel's build.config.common names it. Host package versions, commands, archive hashes, final config hash, build logs and output hashes are retained as evidence. Build identity/time are fixed. This has not yet established byte-for-byte reproducibility across independent builds.

The full build requests Image.gz, DTBs and modules. Outputs include Module.symvers and System.map when produced. Modules in this job target the selected 4.19 kernel, not 6.18. No boot.img, automatic flashing or device-ready ZIP is produced. Source revisions and file-level licenses remain authoritative when redistributing any resulting artifact.

## ACK 6.18 gate

The existing `experiment/gki-6.18-repo-mirror` branch has already passed a complete Kleaf build in [run 42194678844](https://github.com/xxbo/RMX2072-AOSP-Project/actions/runs/42194678844), producing a 687,670,307-byte uploaded artifact. Its workflow, source pins and NFC experiment are now being integrated into the mainline execution path. Preserve this evidence instead of repeating an initial generic-kernel feasibility experiment.

The kernel/common pin already resolves to 6.18.32. The main workflow now locks all 58 manifest projects using the resolved snapshot from that successful run, verifies every checkout and adds a strict NQ-NCI DDK compilation gate. A kernel/common SHA alone is insufficient. The default manifest includes extra device/test projects; evaluate its groups and workspace footprint on the Actions runner rather than downloading everything blindly.

The generic ACK baseline is built. Next add a separate KGSL compile/KMI probe and introduce the RMX2072 boot/DTS/UFS/USB changes. A generic GKI Image is not an RMX2072 boot image. The existing boot header is v2 with an embedded DTB bundle; vendor_boot/init_boot are absent from the physical GPT.

## GSI gate

The user selected and authorized downloading the official Android 17 QPR1 ARM64 + GMS package CP3A.260905.010 after accepting its license. `build/gsi.json` records the official URL and SHA-256. Inspect its actual VINTF matrices, VNDK/linker support, sparse/raw size and system partition fit. Stock F.20 declares vendor FCM 5, while the inspected Android 17 source's default matrix list begins at FCM 7. Resolve this gap with image evidence and a compatibility test, not by arbitrarily changing the declared vendor target level.

First test the system layer against the compatible stock kernel/vendor. Test a new 6.18 kernel separately so failures can be isolated. Keep the existing local backups; full-system recovery from them is not yet exercised.

## Evidence and synchronization

Commit project-authored code/configuration, source pins and redacted findings promptly. Keep full images, proprietary vendor files, calibration/secure data, device identifiers and raw captures local. Public CI artifacts contain build products/provenance only; private handset backups must never be added to Actions artifacts.

Record build-tested, boot-tested and hardware-tested independently. Update this document and the compatibility matrix after each actual run.

## Selected device trees

A read-only local parse of the original F.20 boot/DTBO backups found 25 concatenated boot DTBs and 18 DTBO entries. The live phone reports `ro.boot.dtb_idx=12` and `ro.boot.dtbo_idx=17`; selected root selectors and blob hashes are in `build/device/stock-dt-selection.json`. Boot entry 12 identifies Kona v2.1 (SoC 356, revision 0x20001); overlay 17 identifies Kona MTP with board ID 0x10008. These indices identify the stock selection; they do not establish 6.18 bindings or driver compatibility. Direct live DT filesystem reads remain denied.

The corrected legacy run [42226376116](https://github.com/xxbo/RMX2072-AOSP-Project/actions/runs/42226376116) passed the Goodix compile point, then failed in qcacld with `/bin/sh: Argument list too long`. The codeload root embeds the 40-character commit in every repeated include path. The build now renames that extracted root to a short workspace path before configuring; it keeps Wi-Fi enabled and retains the source/patch hashes. This change needs a new full run.

The shortened-path full legacy retry is [run 42228243866](https://github.com/xxbo/RMX2072-AOSP-Project/actions/runs/42228243866), currently pending a final build result. The main locked GKI + strict DDK run is [42226214281](https://github.com/xxbo/RMX2072-AOSP-Project/actions/runs/42226214281).

## Completed locked GKI + strict NFC milestone

[Run 42226214281](https://github.com/xxbo/RMX2072-AOSP-Project/actions/runs/42226214281) passed: all 58 exact revisions verified, full GKI distribution produced, and NQ-NCI built through strict DDK. The downloaded NFC artifact passed local import/CRC checking against the same run's kernel symvers (75 imports, 76 version entries, no missing/mismatching CRCs). See `experiments/nfc_nq/results/strict-ddk-9.json`. The newer automatic CRC gate was committed after this run started; that same audit was applied locally to its artifacts. Board boot, module loading and physical NFC are still untested.

## SM8250 platform bootstrap

The shortened-path legacy full build [42228243866](https://github.com/xxbo/RMX2072-AOSP-Project/actions/runs/42228243866) passed and produced a 27,314,415-byte artifact. This is build evidence, not a stock-source match or physical boot result.

`SM8250 6.18 Platform Bootstrap` is the next compile gate. It uses the same 58-project dependency lock, a standalone Kleaf kernel target and a checked-in SM8250 pre-defconfig fragment. Pinctrl, clock/RPMh, SPMI/regulators, interconnect, SMMU, UFS/PHY and USB/I2C/UART support are requested built-in to match the boot-v2 early-driver requirement. Kconfig must preserve every requested assignment. This is a custom platform configuration and is not represented as an unchanged GKI-certified kernel. It produces Image/modules/config/symvers, not an RMX2072 boot image; board DTS and display/vendor ABI work remain necessary.

## Runtime diagnostics and first board DT

The stock Bootloader did not expose fastboot after adb reboot bootloader; the handset returned to the Android MIDI USB configuration. A temporary fastboot boot was therefore unavailable. After the user explicitly approved a debug boot write, boot alone was written through the previously tested 9008 path. Before writing, a full boot readback matched the stock backup SHA-256. The prepared Magisk v31.1 image retained the exact stock kernel, DTB, boot command line, v2 header and 4096 page size. After writing, readback matched the prepared image. Stock Android booted; the root shell returned UID 0 after completing Magisk setup and granting Shell access in the new v31 UI.

The active debug boot hash is `9593e11ba8cd2fabe162fe821b951035efd328b2b2cbf5b9c57c1a7b5c0969ad`; stock boot hash is `28bb76fe226a3cf859873e870f3bee89093cc0248f841c1ad793701f35a34a7c`. Exact backup images and one-partition recovery XML remain local. No system, super, userdata, recovery or bootloader image was changed by this debug step. This is still the original 4.19.157 kernel, not 6.18 device-boot evidence.

The root capture now confirms the selected panel boot argument `msm_drm.dsi_display0=qcom,mdss_dsi_rm19795samsung_ams641rw01_1080_2340_cmd:`. Despite the node suffix, its actual modes are 1080x2400 at 60/90 Hz with DSC, slice width 540 and slice height 48. Driver firmware logs bind Goodix at I2C 8 address 0x5d, with firmware path `tp/19795/FW_GT9886_SAMSUNG.img`; its reported firmware PID is GT9885. Preserve the distinction between the driver/DT name and firmware PID.

A first `sm8250-realme-rmx2072-usb-diag.dts` now translates the captured RAM banks, firmware reservations, ramoops and USB-HS rails onto the pinned upstream 6.18 SM8250 bindings. It deliberately leaves storage, display and Android integration disabled for a read-only USB diagnostic initramfs milestone. It must compile and boot before claiming board support. The accompanying no-op DTBO is needed to prevent applying the original downstream overlay to this upstream-binding DTB. Its replacement/restoration must be handled together with the diagnostic boot image.

## First 6.18 on-device diagnostic candidate

The standalone platform build [42233938138](https://github.com/xxbo/RMX2072-AOSP-Project/actions/runs/42233938138) passed and produced raw ARM64 Image (44,976,640 bytes), config, symvers and modules. All requested platform assignments survived Kconfig. The separate RMX2072 device-tree [run 42237662943](https://github.com/xxbo/RMX2072-AOSP-Project/actions/runs/42237662943) passed both dtc compilation and libfdt overlay application.

A locally built static-BusyBox initramfs configures a CDC ACM USB serial shell and mounts only proc/sysfs/devtmpfs-or-tmpfs/configfs. It never mounts a block filesystem. Its newc format was checked by BusyBox on the handset. The diagnostic boot-v2 package preserves the stock load offsets and OS/patch header fields, uses the verified platform Image plus the compiled USB diagnostic DTB, and fits the original 96 MiB boot partition. A matching no-op DTBO is padded to the original 24 MiB partition size. Both boot and DTBO have paired readback and restore recipes prepared locally. Device boot has not yet been attempted at this checkpoint.

This step proves the kernel/USB/logging foundation before Android integration. Display/HWC/KGSL compatibility and the official Google GSI's FCM/VNDK/capacity gaps remain on the desktop critical path. No USB diagnostic shell result should be labeled an Android desktop result.

## First physical 6.18 attempt: bootloader rejection and recovery pending

The first packaged USB diagnostic boot (`5fb916f85ae8dbc7bbbdb6815cd0f59b735e3110eb7e3367e0794f547a09f7d7`) and no-op DTBO (`605b7b942425ca50d3462316a354d52266e9bfe755480fe7c98dd40cfce905e5`) were written and byte-verified through 9008. On reboot, the user reported the system-files-destroyed / install-correct-software screen. No diagnostic USB interface enumerated. Do not record this as a kernel boot or kernel crash; execution of the 6.18 Image has not been established.

Inspection found a concrete packaging defect: the freshly generated images lacked AVB footers, while both stock images and the physically booted Magisk debug image retain them. The packaging script now retains the stock embedded AVB metadata and relocates its footer around the changed payload, for the already-unlocked test device only. This does not sign or authenticate the modified payload: the stock signed hash no longer matches it. Verification of the corrected package on the handset is still pending.

The retention procedure reconstructs the previously booted Magisk image byte-for-byte from stock metadata and its patched payload. Four synthetic format/bounds regression tests pass; the two failed no-footer packages are rejected by the new validator. Corrected images were prepared locally but have NOT been written to the phone.

Recovery is the immediate priority. The original and tested debug boot images plus original DTBO, exact UFS XML ranges and hashes are collected locally under outputs/phone-recovery-kit. Only boot and DTBO were changed by the diagnostic attempt. The previous 9008 route depended on ADB reboot edl; repeated physical-key attempts from the error screen have not enumerated 9008 or a stable fastboot USB interface. Windows records no phone USB arrival after the diagnostic reset. The user reports key-held screen flickering, but a static error screen with all keys released and USB unplugged. The phone is NOT currently verified restored or operational.
