# Official Android 17 QPR1 ARM64 + GMS preflight

The user selected the GMS variant and accepted the official download license. The package was downloaded locally from the [Google release page](https://developer.android.com/topic/generic-system-image/releases); neither the package nor extracted Google files are committed or uploaded to CI.

## Verified image

- Build: CP3A.260905.010 / 16176746, Android 17, API 37, security patch 2026-09-05.
- ZIP SHA-256 matches the official value in `build/gsi.json`.
- Raw ext4 `system.img`: 3,953,213,440 bytes, SHA-256 `8b525e2bff18a54b277c4b9a950a0ee667e50ad2e91bcc4c1daa6f081402407e`.
- `vbmeta.img`: 4,096 bytes, SHA-256 `b3281c527ecf2a6a743b37f5b9e118f492d2038e0a82e6777d292d1c5b42601a`.
- The ext4 parser reports 62,459,904 bytes after the filesystem. An AVBf 1.0 footer declares the original filesystem length 3,890,753,536 and a 2,432-byte vbmeta at offset 3,952,402,432; the extra data is consistent with an AVB-protected image layout. No signature verification has been claimed.

## Actual compatibility gaps

The image contains framework compatibility matrices 7, 8, 202404, 202504 and 202604, plus the device matrix. No level-5 matrix is present. The stock vendor manifest declares target-level 5. This confirms the previously source-derived gap against the downloaded image itself. It is not a completed libvintf compatibility verdict: `checkvintf` is unavailable on the running stock system and a matching host checker has not yet been run.

The image bundles VNDK APEX versions 31, 32, 33 and 34; version 30 is absent. Stock vendor declares `ro.vndk.version=30`, and its separate stock `/system_ext/apex` contains `com.android.vndk.v30.apex`. The stock fstab mounts a separate logical `system_ext`, while GSI includes its own system_ext content inside system. Investigate first-stage mounting, APEX selection and linker namespaces before deciding whether the existing VNDK 30 package is usable. Keeping an old system_ext can also introduce incompatible services; its presence does not solve the compatibility gap by itself.

Matrix kernel requirements must be evaluated at the correct vendor/kernel FCM level; selecting a newer matrix or editing the declared vendor target level does not establish compatibility.

## Partition capacity

Read-only `lpdump` on the connected handset reports qti_dynamic_partitions maximum size 8,862,564,352 bytes, with 6,627,184,640 currently allocated. Existing system is 622,247,936 bytes; replacing it with this GSI requires growth of 3,330,965,504 bytes, exceeding free group capacity by 1,095,585,792 bytes, before alignment allowances. It cannot fit through an ordinary system resize while retaining every current logical partition. See `build/device/stock-logical-partitions.json`.

Do not remove OEM logical partitions until their boot dependencies and a complete super recovery method are understood. The existing full super backup is local and hashed, but a complete super restore has not been exercised.

The November 13 rehearsal includes the project vendor at its actual 2 MiB size. Replacing both stock images reduces the group deficit to 685,142,016 bytes. The host candidate, retained partitions, overlapping slot 1 payload and recovery checks are recorded in the [M1 UFS layout](M1_UFS_LAYOUT.md).

## November 6 stock-vendor experiment design

These steps document the F.20 compatibility investigation. The [current roadmap](../plan.md) targets a source-built vendor on ACK 6.18. The partition measurements above remain relevant to any layout that preserves the same logical partitions.

1. Obtain a host libvintf checker matching this Android release and run it with explicit GSI system plus captured stock vendor/odm mappings and recorded boot properties.
2. Resolve VNDK 30 availability and system_ext mounting behavior using the actual boot path.
3. Design and review a capacity/recovery plan for the logical partition layout, or validate a compatible DSU path that avoids resizing super.
4. Only then create device-specific flashing commands and collect first-boot logs. The proposed November 6 comparison used the stock kernel. The subsequent target-system trials used the project 6.18 kernel.

No system partition, logical partition size, AVB setting or boot image was changed during this preflight.

On November 10 the GSI ran its own toybox from USB-backed dm-verity. On November 11 Android PID 1 mounted the GSI and project vendor. The measured deficit above still applies to the specified F.20 layout. [Handset journal](https://github.com/xxbo/RMX2072-AOSP-Project/blob/da4385b38212ea8f84307f672a741da77172ecc5/docs/ANDROID17_USB_MOUNT.md) · [Current M1 work](../plan.md#next-work-on-m1)
