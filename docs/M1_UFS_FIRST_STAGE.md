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
