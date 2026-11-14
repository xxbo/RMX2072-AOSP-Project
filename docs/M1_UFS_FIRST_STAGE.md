# Android 17 first-stage init on internal UFS

This test pairs ACK 6.18.32 and the pinned API 37 first-stage binary with the CP3A.260905.010 system image and the project vendor 02 filesystem. Both filesystems reside in logical partitions of the RMX2072 internal UFS super. Slot 0 releases `my_stock` to make space. The candidate uses a 3,145,728-byte signed vendor and leaves 915,103,744 bytes of group capacity. The overlapping inactive slot 1 system payload changes. [Layout and original recovery procedure](M1_UFS_LAYOUT.md)

## Build inputs

Use the original GSI and the 2 MiB vendor 02 ext4 image. Wrap a copy of vendor 02 in an AVB hashtree using a private engineering RSA-4096 key. The salt for this trial was the SHA-256 of the original vendor ext4 image. Keep the original vendor and signing key outside the checkout. The tested AVB tool is from AOSP tag android-16.0.0_r1. [AVB tool](https://android.googlesource.com/platform/external/avb/+/refs/tags/android-16.0.0_r1/avbtool.py)

```sh
python avbtool.py add_hashtree_footer --image PRIVATE/vendor.img --partition_name vendor \
    --partition_size 3145728 --algorithm SHA256_RSA4096 --key PRIVATE/vendor.pem \
    --hash_algorithm sha256 --salt 8222950372b5c1327e7cf9b4de1fa852ba7a833847af76b767afac6838364f90 \
    --do_not_generate_fec
python avbtool.py extract_public_key --key PRIVATE/vendor.pem --output PRIVATE/vendor.avbpubkey
python scripts/build/prepare_ufs_verification.py --system PRIVATE/system.img --vendor PRIVATE/vendor.img \
    --vendor-key PRIVATE/vendor.avbpubkey --output PRIVATE/profile
```

The profile builder verifies both embedded RSA signatures, pins the system image and key, checks the expected vendor key and verifies the hash of the original vendor filesystem inside the signed image. Pass the resulting directory to `build_diag_ramdisk.py --ufs-first-stage` with the pinned Android init, static observer, liblp runtime, UFS host diagnostic and return timer. Use `prepare_ramdisk_control.py --ufs-boot-device` with the proven 6.18 boot template. Only the public keys enter the first-stage root. The project uses an unlocked engineering handset and a factory-derived board tree for this trial.

## Evidence

The ramdisk fstab selects logical partitions by their names. Android regenerates block devices and reads LP metadata, then uses its first-stage AVB setup to mount system and vendor. The observer checks each successful mount against the actual dm-verity table, its pinned root digest and the dm-linear extents on the UFS super. Device-mapper minor numbers are recorded at runtime. The vendor 02 filesystem still contains the historical USB fixture fstab; the first-stage root embeds the separate UFS fstab. [UFS fstab](https://github.com/xxbo/RMX2072-AOSP-Project/blob/209bfe94ed4bebf48e524181efac17e3ea572a9b/device/realme/bladerunner_48m/fstab.m1-ufs) · [AOSP first-stage mount](https://android.googlesource.com/platform/system/core/+/refs/heads/main/init/first_stage_mount.cpp)

Collect the ACM stream with `observe_ufs_first_stage.py` and save ramoops during recovery. For this kernel and GSI, the probe on `vfs_read` records PID 1, the filesystem device and inode, request size and actual return value. Inodes 659 and 757 identify `/system/build.prop` and `/system/etc/init/hw/init.rc`. Compare their read results with the enforcing transition and second-stage entry from the same boot. The handset trial and stock recovery results are in the [machine-readable record](../build/device/m1-ufs-first-stage-2026-11-13.json).

## November 13 handset result

Trial 03 ran on boot ID `d7add4b7-7174-40a4-a9be-121a9fdc1ecf`. fs_mgr returned AVB success separately for both partitions. PID 1 mounted system on `dm-14` and vendor on `dm-15` as read-only ext4. Each mount returned zero. All 16 system extents and the single vendor extent matched the candidate LP layout on `sda10`. Each verity table matched its signed root and reported status `V`.

| Seconds since boot | Observation |
| ---: | --- |
| 39.589690 | SELinux audit recorded enforcing switching from 0 to 1. |
| 39.615790 | PID 1 logged second-stage entry. |
| 39.662750 | PID 1 read all 5,675 requested bytes of `/system/build.prop` on device 254:14. |
| 39.686730 | PID 1 read all 56,913 requested bytes of `/system/etc/init/hw/init.rc` on the same device. |
| 39.687703 | The import at init.rc line 12 could not expand `ro.zygote`. |
| 40.397633 | PID 1 started servicemanager. |
| 40.490701 | SELinux denied vold read access to `/vendor/etc/fstab.qcom`, labeled `vendor_rmx2072_board_config`. |

The first host observer launch lacked pyserial. Restarting the observer with the existing serial dependency captured both mounts on this boot. Enforcing then limited the diagnostic observer's access to proc and kmsg. The persistent kernel console retained the read results. It was retrieved from the following diagnostic boot before the return to 9008. Host trial 02 had stopped at a Firehose XML parser error before a test boot. After trial 03, all 17 original super chunks, boot and DTBO matched their recovery digests. F.20 reported a new boot ID, `eb461622-8f63-4ad8-8f72-1bcd715b4d3d`, and `sys.boot_completed=1`. Both LP slots and the full device-side super digest matched the originals. Android 17 ADB and disconnected cold boot still need measurement.

To regenerate the mount and read results, place the private `acm.log`, `identity.json` and `console-ramoops-0` together and run the recorder. It verifies their boot identity, live extents, verity roots, enforcing order and the filesystem device for both reads.

```sh
python scripts/device_audit/record_ufs_first_stage.py --capture PRIVATE/live \
    --layout build/device/m1-ufs-first-stage-2026-11-13.json
```


## Trial 04 · Zygote imports and vold on UFS

The project vendor supplies `ro.zygote=zygote64_32` in `/vendor/build.prop`. Both the first-stage ramdisk and the vendor partition use the two logical UFS entries from `m1-vendor/etc/fstab.qcom`. The vendor filesystem stores the fstab with the platform's `vendor_configs_file` context. CI checked every ext4 file and SELinux xattr, built the vendor twice and compared the images byte for byte. The signed 3 MiB vendor used the existing engineering key. [Vendor build](https://github.com/xxbo/RMX2072-AOSP-Project/actions/runs/43436009380)

After signing, pass the matching CI manifest to the profile builder. The manifest binds the original ext4 digest to the tracked source inventory. Use its `sha256` as the AVB salt when reproducing this build.

```sh
python scripts/build/prepare_ufs_verification.py --system PRIVATE/system.img \
    --vendor PRIVATE/vendor-signed.img --vendor-key PRIVATE/vendor.avbpubkey \
    --vendor-report PRIVATE/vendor.json --output PRIVATE/profile
```

On boot `0682a103-f53f-43b6-af8c-13eb63883546`, init verified and mounted system and vendor from UFS and entered second stage at 27.449207 seconds. SELinux had entered enforcing at 27.422965 seconds. The mounted file's inode and size, the kernel read result and the caller identify each observation. The import events and binder caller identity are in the [handset record](../build/device/m1-ufs-first-stage-vendor-services-2026-11-13.json).

| Time since boot | Reader | File | Bytes read |
| ---: | --- | --- | ---: |
| 27.528196 s | init, PID 1 | `/system/etc/init/hw/init.zygote64_32.rc` | 620 / 620 |
| 27.529043 s | init, PID 1 | `init.zygote64.rc`, imported by the preceding file | 901 / 901 |
| 27.529758 s | init, PID 1 | `init.boringssl.zygote64_32.rc` | 392 / 392 |
| 28.463988 s | vold, PID 1778, `u:r:vold:s0` | `/vendor/etc/fstab.qcom`, inode 14, device 254:15 | 220 / 220 |

The host took 73 successful ADB samples over 76.344 seconds from the handoff request through identification of the recovery boot. The longest sample gap was 1.156 seconds. Diagnostic ACM enumerated. Every ADB device list in that interval was empty. Boot logs show the bootstrap APEX scan finding `com.google.android.adbd.capex`. They contain no service start for adbd or zygote. The watchdog bounded this USB-attached test.

At `post-fs-data`, init encountered read-only `/data` and a missing `/data/misc/keystore`. It waited for `vdc keymaster earlyBootEnded` at 28.655711 seconds. Vold requested `android.security.maintenance`, and init reported eight `keystore2` exits on SIGABRT through the captured window. This records the wait and the process failures. Identifying the abort cause requires the keystore log for that crash and a writable diagnostic data setup.

Capture with `observe_ufs_first_stage.py --observe-adb`. Replay the mounts, reads, service identity and host ADB window from the private capture using the checked-in layout.

```sh
python scripts/device_audit/record_ufs_first_stage.py --capture PRIVATE/live \
    --layout build/device/m1-ufs-first-stage-vendor-services-2026-11-13.json --vendor-services
```

The handset returned to 9008 by software. Recovery restored all 17 original super chunks and the F.20 log-reader boot baseline. Independent readback matched super, boot and the original DTBO. F.20 then reported `sys.boot_completed=1` on boot `4ac714d3-ae03-45b9-8a43-eb3775901ab4`. Both LP metadata dumps and the SHA-256 computed over super from Android matched the pre-trial values.

## Writable /data and /metadata trial

Build the scratch filesystems using `python scripts/build/build_m1_scratch.py --output PRIVATE/volumes` on a host with e2fsprogs. Pass that directory to `build_diag_ramdisk.py --scratch-volumes PRIVATE/volumes` alongside the trial 04 signed UFS profile. The data image is 512 MiB and includes the GSI file labels and Android ownership for its root, `misc` and `misc/keystore`. Metadata begins with a labeled root on a separate 32 MiB image.

After the UFS vendor mount, the diagnostic decompresses both images into a bounded tmpfs and checks their raw digests. The observer mounts the two loop-backed ext4 filesystems in Android init's namespace and verifies a create, write, fsync and unlink on each volume. UFS block devices remain read-only during Android execution.

The observer verifies the GSI library hashes and records keystore2's Android log messages and Binder registration calls and returns. Match the first keystore PID against its log messages and init's exit record. Check the exit status of the specific vdc invocation, APEX activation, USB interface descriptors and host ADB state separately. [Linux 6.18 uprobe interface](https://docs.kernel.org/6.18/trace/uprobetracer.html) · [AOSP keystore2 registration](https://android.googlesource.com/platform/system/security/+/refs/heads/main/keystore2/src/keystore2_main.rs)

On Windows, start `watch_trial_usb.ps1` in 9008 before the test reset. Pass a JSONL output path and the observer's `live/host-events.jsonl` as `-HandoffEvents`. The collector follows the physical USB port through re-enumeration and records interface compatible IDs. The ACM observer separately samples the ADB server.

### Trial 05 handset result

The handset ran ACK 6.18.32 and switched to SELinux enforcing at 47.442569 seconds. Both scratch mounts passed the write check. The console ring wrapped during service retries. The matching pmsg handoff marker identifies boot `cc122bec-c8ca-4ae0-993f-f231d5869fad`, and the live ACM stream retains both AVB successes. The persistent console contains the first keystore process's complete panic. [Handset record](../build/device/m1-ufs-first-stage-writable-2026-11-13.json)

| Time since boot | Observation |
| ---: | --- |
| 48.607708 s | Init started keystore2 as PID 2035. |
| 48.653957 s | Init waited for PID 2041 running `vdc keymaster earlyBootEnded`. |
| 48.787662 s | The same keystore2 thread returned 0 from registering `android.security.compat`. |
| 48.788188 s | Creating the mandatory TEE security level failed. The direct KeyMint lookup and the legacy wrapper ended in `HARDWARE_TYPE_UNAVAILABLE`. |
| 48.789185 s | Keystore2 logged the panic constructing `android.system.keystore2.IKeystoreService/default`. |
| 48.822156 s | Init recorded the first SIGABRT for PID 2035. Eight keystore2 invocations aborted during the capture. |
| 85.725695 s | Init still could not resolve `aidl/android.security.maintenance`. The trace contains no maintenance registration or matching vdc exit. |

The bootstrap APEX scan found `com.google.android.adbd.capex`. It activated the four bootstrap packages (virt, tzdata, i18n and runtime). The capture contains no adbd activation or service start. Across 96.313 seconds, 88 ADB queries returned an empty list and one timed out. All 40 USB samples showed either a disconnected port or the diagnostic gadget. The only observed interface was CDC ACM (02/02/01).

```sh
python scripts/device_audit/record_ufs_scratch.py --capture PRIVATE/live --usb PRIVATE/usb-port.jsonl \
    --layout build/device/m1-ufs-first-stage-writable-2026-11-13.json
```

Trial 05 returned to 9008 by software. Recovery verified each of the 17 original super chunks, the F.20 log-reader boot and the original DTBO. F.20 booted with ID `714bc753-3d76-4bfc-b01c-8319ebb9cf9b` and `sys.boot_completed=1`. Both LP metadata slots and the device-side full super digest matched the pre-trial baseline. On that boot, `lshal -i` listed `android.hardware.keymaster@4.0::IKeymasterDevice/default` and the vendor manifest specified hwbinder. This identifies the stock interface for the next project vendor comparison.

## F.20 Keymaster reference and Android 17 compatibility

F.20 exposed `android.hardware.keymaster@4.0::IKeymasterDevice/default` over hwbinder. The running service held descriptors for hwbinder, QSEECom, ION and a DMA buffer. Its QSEECom device was bound to `82400000.qseecom`. Generating a temporary TEE key through Android Keystore produced five paired SCM trace events in the HAL process after an idle second with zero events. The key was deleted successfully. A separate loaded-app query found `keymaster64` resident and `keymaster` absent. F.20 registered `android.security.maintenance` and init recorded a successful exit for `vdc keymaster earlyBootEnded` after 17 ms. [Stock observations](../build/device/m1-f20-keymaster-path-2026-11-13.json)

In CP3A.260905.010, the system_ext manifest caps the HIDL manager at FCM 8. Matrix 7 lists Keymaster 4.0/default. The M1 comparison selects device FCM 7, retains the GSI's 202604 split SELinux policy and uses the QTI service with six pinned libraries from the handset. Build the private comparison with `build_m1_vendor.py --keymaster-reference DIR --output OUT`. The default image still builds from the project's M1 vendor sources. The comparison and release have different dependencies. [Private HAL inventory](../device/realme/bladerunner_48m/m1-keymaster-reference/f20-files.json)

### Four writable-volume handset runs

Each boot mounted the same 512 MiB data and 32 MiB metadata ext4 seeds on RAM-backed loop devices. Both signed UFS partitions passed Android first-stage verification. The new SCM lookup returned ENOENT for `keymaster` and success for `keymaster64` in all four boots.

| Trial | First observation on the hardware-service path |
| --- | --- |
| 06 | The GSI manager requested the declared Keymaster 4.0/default instance. The first service process exited with status 1 after 14 ms. Vendor init rejected a separate property-based start rule. |
| 07 | HIDL lazy startup alone launched the service. The first process wrote a loader error naming `libcutils.so` as a missing direct dependency. Early second-stage and APEX lines rolled out of the console ring on this run. |
| 08 | Adding the twelve VNDK 30 libraries mapped by the stock HAL allowed the executable to reach its hwbinder open. The same process remained alive through another request 37 seconds later. |
| 09 | The same signed vendor and kernel ran with an additional instrumented ramdisk. At 49.140609 s the HAL read an empty listener readiness value in the Keymaster constructor. On F.20, `vendor.sys.listeners.registered` was `true` and `vendor.qseecomd` was running with ten QSEECom descriptors. The constructor checks this value before calling QSEECom to start the app. The retry probe produced no visible record. The start-app callsite also produced none during the saved interval. |

On trial 09, PID 1 entered enforcing at 47.670138 s and started second stage at 47.697350 s. Keystore2 registered `android.security.compat` with return code 0. Vold still requested maintenance at 84.980840 s. Init continued to wait for vdc PID 2018. The recorder counted zero keystore2 SIGABRTs. Bootstrap apexd found the adbd package and activated four other packages. The host recorded 93 ADB polls and 47 physical USB samples, with diagnostic ACM on the phone's port. M1 remains open.

A callable hardware instance requires the 6.18 listener transport and a verified readiness producer. Qualify actual listener registration, the subsequent Keymaster app startup and HIDL service registration before using a maintenance result as an Android boot milestone. The reference ELF files and the engineering AVB private key remain local. [Per-boot records and rollback digests](../build/device/m1-ufs-keymaster-2026-11-13.json)

### F.20 listener dependencies measured on November 14

On one F.20 boot the stock daemon logged ten started listeners. A pair of repeat captures filtered SCM trace events to the Keymaster HAL threads. Both temporary TEE key generations requested time listener 11. In the second capture the continuation also requested GP cancellation listener 4352. The time worker handled command 770 (`GET_UTC_SEC`), obtained ATS_MODEM time and returned success. Both sign/verify operations completed with two SCM calls each. Neither sign/verify produced a listener request in the saved interval. The inventory and the callbacks observed for these particular operations have different scopes. [Per-operation records](../build/device/m1-f20-keymaster-listeners-2026-11-14.json)

The [capture script](../scripts/device_audit/f20_listener_trace.sh) uses a uniquely named temporary key. It records SCM status and listener IDs without saving keys or payloads. For an independent client control, the project-built HIDL client on F.20 received security level 1, name `Keymaster HAL: 4` and author `QTI` from the stock service.

The [info-only engineering service and client](../device/realme/bladerunner_48m/m1-keymaster-info) use the Android 11 platform HIDL ABI. The service requires a successful version reply from the resident `keymaster64` before registering. Key operations return `UNIMPLEMENTED`. Its vendor profile uses eight public AOSP VNDK libraries. The hardware version query follows Qualcomm's fixed [PFK version request and response](https://android.googlesource.com/kernel/msm/+/b5b536e7623678da36aa53853217e8d7d68cc268/security/pfe/pfk_ice.c). A version query measures the app transaction. Listener delivery and a GSI Binder return each require their own trace.

For the engineering build, use [VNDK 30 arm64](https://android.googlesource.com/platform/prebuilts/vndk/v30/+/5f9884aa352825291757dfd6694b874ad8c1805e/arm64/) headers and shared libraries, [Bionic libc headers](https://android.googlesource.com/platform/bionic/+/673bb02eec857ef6b004e562ab41d6b3a0e21b8a/libc/include/) and NDK 28.2.13676358. Build both executables with `scripts/build/build_m1_keymaster_info.py`. Stage both and the eight pinned shared libraries in a directory passed to `build_m1_vendor.py --keymaster-info DIR`. Verify the resulting signed vendor using `prepare_ufs_verification.py --keymaster-info --vendor-report REPORT`. The default vendor profile and the earlier private F.20 comparison have separate inputs. [Input digests](../device/realme/bladerunner_48m/m1-keymaster-info/inputs.json)

### Android 17 calls the source-built Keymaster service

Trial 11 booted the Android 17 GSI and the signed project vendor from internal UFS on 6.18.32. The same disposable ext4 data and metadata volumes passed the write/fsync check. The fixed version query to the resident `keymaster64` returned transport 0, app status 0, API 4.0 and TA 4.546. With SELinux enforcing, init started GSI `keystore2` as PID 2027 and the project service as PID 2044. At 72.023776 s, the service logged its completed HIDL reply to PID 2027 with level `TEE` and name `RMX2072 keymaster64 API 4.0 TA 4.546`. At 72.024407 s the GSI logged `-100` during shared-secret parameter retrieval. Its only observed keystore Binder registration was `android.security.compat`. No exit from `vdc keymaster earlyBootEnded` or ADB transport was observed during the capture.

The first host observer missed the initial USB connection. The replacement observer recovered the trial's console from persistent RAM and matched its boot ID to the live ACM capture. All 17 original super chunks, both LP metadata slots, the F.20 log-reader boot and stock DTBO matched after rollback. F.20 reported boot completion over ADB. [Handset observations and image digests](../build/device/m1-ufs-keymaster-info-2026-11-14.json)

Trial 12 measured the listener lifetime on the same handset and signed vendor. Both the SCM transport and secure-world results were zero for registration and teardown of time service 11 and GP request cancellation 4352. Each listener was removed before the version query. On this boot the TA again returned API 4.0 and TA 4.546. GSI keystore2 PID 2019 received the project HAL's hardware information at 48.790201 s. The GSI reported shared-secret parameter error `-100` at 48.790915 s. During the 96-second host observation there was no ADB transport.

The outstanding listener test is a Keymaster request that returns `INCOMPLETE`, dispatches the named listener, and resumes to a final TA status. The version command in these runs completed directly. The pinned ACK SCM path currently warns on incomplete and blocked calls. F.20's time worker reported `ATS_MODEM` for the observed key generation. Trial 12's kernel has neither QRTR nor the PM8xxx RTC driver enabled. Qualcomm also publishes a UTC listener implementation using the OS real-time clock. A callback test needs a verified source of UTC on this boot and a record of the actual dispatch and continuation. [ACK SCM](https://android.googlesource.com/kernel/common/+/ecdaacc9a0ee87eaf9544e1836d86bd9d590312e/drivers/firmware/qcom/qcom_scm.c) · [Qualcomm UTC listener](https://github.com/qualcomm/minkipc/blob/ff9eaf92d357ec35a54a7bf5d2465a5f818d73ea/listeners/libtimeservice/atime.c)

After trial 12 the full F.20 recovery checks passed again. On that restored boot the separate source-built HIDL client called the stock `getHmacSharingParameters` at uptimes 102.16 s and 104.08 s. Both calls returned OK. Each capture shows one direct SCM completion and zero listener callbacks in the stock HAL thread. The client discards the returned parameters. This gives the next GSI method its own positive stock control, independent of the key generation callback trace. [F.20 control captures](../build/device/m1-f20-keymaster-listeners-2026-11-14.json)

### Keymaster HMAC parameters and a disposable signing key

The F.20 stock HIDL client selected the legacy HMAC parameter method twice. The project HAL passes the board driver's typed TEE reply to the GSI. The read-only interface accepts a single fixed-size read and is labeled for the Keymaster process. The signed vendor comes from the same source ABI and public AOSP VNDK inputs used for trial 12. Logs record the Binder caller and status. Neither seed nor nonce is recorded.

The stock temporary-key control calls HIDL to generate a 256-bit HMAC/SHA-256 signing key, then deletes the returned blob. Repeating the control produced a time callback on each generation and a direct completion on each deletion. Its six key authorizations, request lengths, return codes and output sizes are reproducible without saving the blob. [Stock observations](../build/device/m1-f20-hmac-method-2026-11-14.json)

The 6.18 engineering probe repeats those fixed authorizations once per boot. The realme Q driver dispatches an incomplete call to the listener named by secure world and resumes that call after its response. The F.20 trace selected the response variant with a scatter/gather table. This time listener supplies an empty table because its buffer contains no external addresses. In the USB-attached test, the host explicitly initializes and checks the diagnostic OS UTC clock before first-stage handoff. That clock source follows Qualcomm’s normal OS-clock time listener implementation. The modem time source used by F.20 remains a separate porting task. [Official realme Q driver](https://github.com/realme-kernel-opensource/realmeX50Pro-5GPlay_AndroidQ-kernel-source/blob/24a15224fbae8ab0e8ba29a9046c06ee7a9f53a4/drivers/misc/qseecom.c) · [Qualcomm time service](https://github.com/qualcomm/minkipc/blob/ff9eaf92d357ec35a54a7bf5d2465a5f818d73ea/listeners/libtimeservice/atime.c)

Trial 13 booted that signed vendor and the fixed HMAC method on 6.18.32. At 50.621543 s the project HAL returned HMAC parameters with status 0 to GSI keystore2 PID 2021. The next GSI trace recorded a shared-secret computation error of -100, followed by its negotiation worker's completion log. The trace contains only the compat Binder registration, and the observed earlyBootEnded process did not exit. The kernel/HAL parameter path passed, while keystore service initialization remains incomplete. The full F.20 partition and Android recovery checks passed after collection. [Trial 13 evidence](../build/device/m1-ufs-hmac-2026-11-14.json)

Trial 14 mounted both UFS partitions and the same writable scratch volumes, then stopped inside the temporary-key control before the SELinux handoff. Listener 11 and 4352 each passed the preceding registration/teardown control. The capture has no return from the key probe and cannot locate its internal stopping point. Three observer UTC-formatting failures were corrected on the same boot before this attempt. The console has no ECC errors. The pmsg record reports 32 unrecoverable blocks and is excluded from Android identity and execution claims. All original partition digests, both LP slots and F.20 boot completion passed after recovery. [Trial 14 evidence](../build/device/m1-ufs-hmac-2026-11-14.json)

The follow-up kernel records the lookup, allocation, registration, app submission and listener-continuation stages. Its ramdisk requests blocked-task and CPU stacks if the temporary-key read lasts five seconds. The official board's QSEECom node sets `qcom,no-clock-support`, which must be considered before attributing this stop to driver clock enables. [Official 20607 board configuration](https://github.com/realme-kernel-opensource/realmeX50Pro-5GPlay_AndroidQ-kernel-source/blob/24a15224fbae8ab0e8ba29a9046c06ee7a9f53a4/arch/arm64/boot/dts/20607/kona.dtsi)

Trial 15 returned from the temporary-key app call at 47.852913 s. The transport completed successfully and the TA returned `KEYMASTER_NOT_CONFIGURED` (-64). No listener callback occurred. Listener teardown returned 0. The last serial command was the wait for the background stack monitor, so this run provides no subsequent GSI service result. The ramdisk now lets that monitor exit after checking a completion marker. F.20 restoration, both LP slots and full partition readback passed. [Trial 15 evidence](../build/device/m1-ufs-hmac-2026-11-14.json)

The next kernel adds the legacy CONFIGURE command before the disposable-key operation. Its fixed engineering parameters come from the verified CP3A.260905.010 system properties, with Android 17 encoded as 170000 and the September 2026 patch level encoded as 202609. The ramdisk checks these properties before invoking the control. The configuration and its status are part of the temporary-key experiment. General HAL configuration remains future work. App submissions also use the scatter/gather variant observed in F.20 (`0x70000006`). These changes require their own handset result.

Trial 16 reused trial 15's kernel with the monitor-wait change. Generation again returned -64, with zero callbacks and successful listener teardown. At 44.526760 s the next QSEE call returned transport error -22. The serial stream stopped before the version reply and SELinux handoff. Removing the monitor wait therefore left the interruption unresolved. F.20 boot completion and all recovery digests passed. A separate GSI control uses the earlier HMAC-only kernel to observe keystore initialization while the configured-key kernel builds. [Trial 16 evidence](../build/device/m1-ufs-hmac-2026-11-14.json)

Trial 18 ran that GSI control using the trial 13 kernel and the same signed UFS images and scratch seeds. Under enforcing, the project HAL returned HMAC parameters with status 0 to GSI keystore2 PID 2020 at 49.364646 s. The trace again recorded shared-secret computation error -100 and compat registration 0, with no maintenance registration or matching earlyBootEnded exit. The entropy probes installed successfully and recorded no event matching the `keystore2` task name. Binder worker names were outside this filter, so this capture cannot resolve the entropy-wait hypothesis. The next ramdisk includes worker names and the recorder associates them with the same keystore process. F.20 restoration and both LP metadata checks passed. [Trial 18 evidence](../build/device/m1-ufs-hmac-2026-11-14.json)


Trial 17 stopped after submitting the 36-byte CONFIGURE request at 45.318217 s through the whitelist SCM command. TIME listener registration returned success beforehand. The capture has no CONFIGURE return, generation result or listener callback. Both UFS mounts and scratch write checks passed before this call. Android handoff was not reached. Console ECC was clean, while pmsg reported 32 unrecoverable blocks. F.20 restoration verified every partition digest and both LP slots. A fresh source-built stock HIDL control then generated and deleted its temporary 455-byte blob successfully, and maintenance was registered. [Trial 17 evidence](../build/device/m1-ufs-hmac-2026-11-14.json)

The official Q driver allocates its scatter/gather tables through QTEE shared memory. Its bridge initializer enables the mechanism and registers the default pool. The tested 6.18 kernel selected generic TZ memory allocation. The next engineering build selects ACK's SHMBRIDGE allocator and logs successful initialization. This is a shared-memory hypothesis awaiting a handset result. F.20 exposes the bridge symbols, but its kernel has no kprobe_events interface, so the attempted runtime flag probe collected no enabled value. [Official Q shared-memory bridge](https://github.com/realme-kernel-opensource/realmeX50Pro-5GPlay_AndroidQ-kernel-source/blob/24a15224fbae8ab0e8ba29a9046c06ee7a9f53a4/drivers/soc/qcom/qtee_shmbridge.c)


The GSI KeyMint compatibility constructor calls `GetVendorPatchlevel()`. The pinned GSI library imports `WaitForPropertyCreation`, and the AOSP implementation waits for `ro.vendor.build.security_patch`. The project vendor previously supplied only `ro.zygote` in build.prop. The M1 engineering image now supplies the epoch date `1970-01-01` to represent an undeclared vendor patch level. Its date is a development placeholder and carries no security-patch validation claim. The handset comparison must establish whether the compatibility constructor returns and maintenance registers after this property is present. [AOSP property wait](https://android.googlesource.com/platform/system/keymaster/+/55cf90f07311695353ac110c7428e1a6cca42644/android_keymaster/keymaster_configuration.cpp)


Trial 20 repeated the HMAC-only kernel with syscall-boundary random-read probes. Six keystore getrandom entries had matching returns for their requested byte counts. At 137.033289 s, the project HAL returned HMAC parameters with status 0 to keystore2 PID 2277. Compat registration succeeded, while maintenance registration and the matching earlyBootEnded exit remained absent. The first host observer launch lacked its local pyserial dependency. It was restarted on the same diagnostic boot, delaying Android handoff. The console retained the subsequent service evidence without ECC errors. Full F.20 restoration, both LP slots and the Android-side super digest passed. The private flashing harness now imports the serial dependency during preflight. [Trial 20 evidence](../build/device/m1-ufs-hmac-2026-11-14.json)


Trial 21 used the signed vendor containing that property and the HMAC-only 6.18 kernel. APEX activation advanced to 43 packages at 57.202467 s, and init imported `/apex/com.android.adbd/etc/init.rc` at 57.270773 s. The host observed no ADB transport. The console had wrapped and began at 50.253333 s, after the initial keystore and vdc results. Those earliest results remain unverified in this capture. The pmsg record reported ECC errors. Recovery verified F.20 boot completion, all partition digests and both LP slots. The observer now stops its proc-access retries when enforcing denies access, to preserve service evidence in the persistent console. [Trial 21 evidence](../build/device/m1-ufs-hmac-2026-11-14.json)

Trial 19 selected `CONFIG_QCOM_TZMEM_MODE_SHMBRIDGE=y` and used the earlier vendor without the patch-level property. The initial bridge-status log had rolled out of the console, leaving runtime activation unverified. CONFIGURE returned transport -22 at 47.765535 s. Generation and listener continuation did not run. Android subsequently entered enforcing and second stage, but HMAC retrieval returned -49 to keystore2. The compatibility-constructor probes reached `GetVendorPatchlevel()` without recording its return. All recovery hashes, both LP slots and F.20 boot completion passed. The host observer now saves the early bridge-status log before Android handoff. [Trial 19 evidence](../build/device/m1-ufs-hmac-2026-11-14.json)

On the restored F.20 boot, a fresh temporary-key control returned generation 0, a 455-byte wrapped blob and deletion 0. The QSEECom entry probe measured a response pointer exactly 84 bytes after the generation request and 467 bytes after the deletion request. In both cases request and response capacities totaled 40 KiB. The revised 6.18 control uses this contiguous layout, moves the returned blob with overlap-safe copying and clears the shared allocation after terminal completion. Its hardware result is pending. [Stock buffer-layout control](../build/device/m1-f20-hmac-method-2026-11-14.json)

### Trial 22 · Maintenance registration and earlyBootEnded return

Boot `b5fcb72c-c9a8-4cc2-b56a-4704622ce223` used the HMAC-only 6.18 kernel, the vendor with the patch-level property and the same writable data/metadata seeds. The quieter observer preserved the complete service sequence in the console, which reports no ECC errors. The pmsg record has unrecoverable blocks and is excluded from these service observations. [Trial 22 evidence](../build/device/m1-ufs-hmac-2026-11-14.json)

| Time since boot | Observed result |
| ---: | --- |
| 51.131446 s | Keystore2's `GetVendorPatchlevel()` returned, followed by the compatibility constructors. |
| 51.132934 s | Project HAL returned HMAC parameters with status 0 to GSI keystore2 PID 2020. |
| 51.139268 s | The same process returned 0 from registering `android.security.maintenance`. |
| 51.140915 s | Keystore2 logged successful service registration and joined its thread pool. |
| 51.159918 s | Boot-level key creation failed with UNIMPLEMENTED from the project HAL. |
| 51.163362 s | The observed vdc PID 2027 exited with status 0 after a 0.185-second wait. |
| 58.927777 s | Apexd activated 43 packages. |
| 58.985348 s | Init imported `/apex/com.android.adbd/etc/init.rc`. |

The trace still reports UNIMPLEMENTED in shared-secret computation. The successful vdc exit coexists with the failed boot-level key creation. The host observed diagnostic ACM and no ADB interface or transport. Init launched zygote processes that subsequently restarted. This trial's kernel contains the HMAC parameter path and omits the temporary-key callback control. The next kernel tests the contiguous request/response buffer on the same vendor and writable seeds.

Recovery returned F.20 to boot `a35919f0-d87d-4b63-8dac-989854105004` with `sys.boot_completed=1`. Full readback matched all 17 original super chunks, the F.20 log-reader boot and original DTBO. Both LP slots and the Android-side super hash also matched the recovery baseline.
