# F.20 AVB and verified read-only mounts

Two RMX2072 warm boots used the 6.18 G3 kernel and the same DTB bundle as the super-mapping trial. Each boot hashed the entire data area of three dm-verity devices, mounted their filesystems in the RAM diagnostic and checked six files against the running F.20 system. See the [signed metadata reference](../build/device/f20-verity-reference.json) and [physical trial results](../build/device/avb-verity-mount-2026-11-10.json).

| F.20 partition | AVB parent | Tree hash | Mounted filesystem | Verified bytes |
| --- | --- | --- | --- | ---: |
| system | vbmeta_system | SHA-256 | EROFS | 610,508,800 |
| vendor | vbmeta_vendor | SHA-1 | EROFS | 404,725,760 |
| product | vbmeta_system | SHA-256 | ext4 | 13,504,512 |

## Metadata and runtime checks

On the workstation, the F.20 capture verifies the RSA PKCS#1 v1.5 signature and authentication hash of each vbmeta structure. It pins the observed top-level F.20 key fingerprint and checks that each child key matches its parent descriptor. Concatenating the normal boot structures in order (`vbmeta`, `boot`, `dtbo`, `vbmeta_system`, `vbmeta_vendor`) reproduces the bootloader-reported SHA-256 over 17,536 bytes. Recovery metadata is checked separately. The capture compares the signed tree parameters, FEC geometry, salts and root hashes with the F.20 kernel's live verity tables.

Before creating mappings, the 6.18 diagnostic reads the three complete GPT vbmeta partitions and verifies that they match the workstation's authenticated reference. It uses slot 0 only after its LP extent tables match F.20. Each positive verity device uses two FEC roots. The diagnostic returns I/O errors on corruption and checks zero blocks as well. The kernel reported valid status with zero corrected blocks on all three targets. Each mount was read-only, nodev, nosuid and noexec. The ext4 mount used `noload` to suppress journal replay.

The mounted-file samples were `/system/bin/init`, `/system/build.prop`, `/vendor/build.prop`, `/vendor/etc/fstab.qcom`, `/product/etc/build.prop` and `/product/etc/apns-conf.xml`. The first boot also rejected a wrong product root hash, but the BusyBox log filter missed the error text before recording the negative target's status. The second boot captured both the failed direct read and status `C` on a fresh read-only target with one root-hash digit changed and FEC omitted. It detached all targets and unmounted all test filesystems. The control only changed the in-memory device-mapper table.

The handset was unlocked for both boots. These checks cover signed F.20 metadata and stock filesystem contents. Bootloader enforcement for a locked handset, hardware rollback counters and the modified diagnostic boot payload are outside this test. Android first-stage init has yet to perform these mounts.

## Replay

1. With root ADB on the restored F.20 handset, run `python scripts/device_audit/check_verity.py capture --serial SERIAL --output reference.json`. The workstation requires Python and `cryptography`. Compare the resulting JSON with `build/device/f20-verity-reference.json`. Also capture the F.20 logical partition reference using `check_super.py capture`.
2. Follow the [super diagnostic build and recovery instructions](SUPER_READONLY.md#replay) with `--f20-verity` and trial ID `ufs-host-g3-super-verity-02`. Use the same verified G3 kernel, DT and Alpine runtime.
3. From ACM, stage the host, enumerate the six LUNs and run `/bin/ufs-host-test disks`. Run `/bin/super-readonly metadata` and compare it with the captured LP reference before continuing.
4. Run `/bin/verity-readonly metadata` followed by `/bin/super-readonly verity`. Save the two outputs as `avb.txt` and `verity.txt`. Run `python scripts/device_audit/check_verity.py verify --reference reference.json --metadata avb.txt --transcript verity.txt` on the workstation.
5. Request EDL over ACM, restore the F.20 logging-reader boot and recheck the complete boot and DTBO hashes. Recapture the AVB and LP references after Android completes boot.
