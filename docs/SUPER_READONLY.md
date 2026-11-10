# F.20 dynamic partitions under Linux 6.18

The RMX2072 diagnostic boot used the kernel and device-tree bundle from the verified HS-G3 profile. Alpine's ARM64 build of AOSP `lpdump` parsed the 8,866,758,656-byte `super` block device (`sda10`). Linux device-mapper assembled temporary read-only targets in RAM-only userspace. See the [physical evidence, image identity and full partition hashes](../build/device/super-readonly-2026-11-10.json).

| Metadata slot | Logical partitions | Linear extents | Comparison |
| --- | ---: | ---: | --- |
| 0 | 15 | 79 | Every extent matched F.20. Its three tested tables matched the live Android kernel tables. |
| 1 | 9 | 9 | Every extent matched F.20's separate slot 1 dump. |

The geometry has two 4 KiB copies and reserves 64 KiB for each metadata copy. The 268 KiB prefix read through 6.18 had the same SHA-256 as the prefix read on F.20. Each slot's primary and backup matched byte-for-byte. The geometry checksum and both slots' header and tables checksums passed independently. See the [AOSP metadata structures](https://android.googlesource.com/platform/system/core/+/refs/heads/main/fs_mgr/liblp/include/liblp/metadata_format.h).

| Read-only target | Extents | Full mapped bytes |
| --- | ---: | ---: |
| system | 1 | 622,247,936 |
| vendor | 2 | 412,540,928 |
| product | 3 | 13,807,616 |

The last vendor extent and the last two product extents are physically below their respective first extents. The diagnostic preserved logical order, queried the loaded kernel tables, checked the kernel's read-only flag and hashed all 1,048,596,480 bytes. Each digest matched the corresponding F.20 `/dev/block/mapper` device. All three temporary mappings were removed. The phone returned to 9008 by ACM command in 6.985 seconds. After F.20 booted, Android-side verification reproduced the original boot and DTBO hashes, LP metadata and all three logical hashes.

## Replay

1. On the booted F.20 handset with root ADB, run `python scripts/device_audit/check_super.py capture --serial SERIAL --output reference.json`. This reads the two liblp layouts and selects slot 0 by comparing the F.20 kernel's actual tables. Keep the reference and raw transcripts outside the checkout.
2. Run `python scripts/build/super_tools.py --cache PRIVATE_APK_CACHE`. The lock pins the SHA-256 of every Alpine v3.23 aarch64 package. The ramdisk builder selects the two commands, musl loader and their ELF dependencies. Keep the verified cache for offline rebuilds.
3. Build the diagnostic ramdisk with the G3 profile's BusyBox and helpers, `--ufs-host-g3-test --super-tools-apks PRIVATE_APK_CACHE --trial-id ufs-host-g3-super-01 --gadget-bind-delay 20 --return-to-edl-after 260`. Package it using the tested G3 kernel and overlay. Follow the [G3 bring-up procedure](UFS_HOST_BRINGUP.md#g3-read-and-wake-validation) through host start, disk enumeration and `/bin/ufs-host-test disks`.
4. Run `/bin/super-readonly metadata` on ACM and save stdout to `metadata.txt`. On the workstation run `python scripts/device_audit/check_super.py verify --reference reference.json --metadata metadata.txt`. This must succeed before creating maps.
5. Run `/bin/super-readonly map` on ACM and save stdout to `maps.txt`. Repeat the workstation verification with `--maps maps.txt`. Confirm the three full hashes and cleanup status. Use the normal ACM-to-EDL procedure, restore the reader boot and repeat the capture on F.20.

This test used plain read-only dm-linear targets over the stock F.20 image. Verifying the AVB chain, attaching dm-verity and mounting filesystems in Android first-stage init are separate boot milestones.
