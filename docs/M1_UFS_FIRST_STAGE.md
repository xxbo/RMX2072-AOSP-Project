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
