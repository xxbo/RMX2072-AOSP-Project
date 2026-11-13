# M1 UFS layout and recovery qualification

The RMX2072 F.20 handset exposes `super` at `sda10` on UFS LUN 0. Its sysfs start and length are 1544256 and 17317888 sectors of 512 bytes. The equivalent Firehose range starts at 193032 and spans 2164736 sectors of 4096 bytes. These units describe the same 8866758656-byte partition. The recovery read uses 17 contiguous requests and ends before userdata.

## Where both target images fit

| Slot 0 group calculation | Bytes |
| --- | ---: |
| F.20 group limit | 8862564352 |
| Current allocations | 6627184640 |
| Android 17 GSI including AVB footer and hashtree | 3953213440 |
| Project vendor 02, ext4 | 2097152 |
| Shortfall after replacing stock system and vendor while retaining all other names | 685142016 |
| Stock `my_stock` allocation in the candidate | 1601294336 released |
| Candidate group allocation | 7946412032 |
| Candidate group headroom | 916152320 |

The offline candidate trades one F.20 logical partition for space while retaining the existing `system_ext` and `odm` payloads. Slot 0 gets a new `system` in 16 linear extents and a new `vendor` in one extent. Every new extent starts on the alignment advertised by the F.20 LP block-device entry. All twelve other slot 0 payloads match their original SHA-256. This exercise uses the current unsigned project vendor at its measured size. Adding signing metadata requires repeating the fit calculation with the final image.

Slot 1 describes a different, overlapping layout on the same physical sectors. Its primary and backup metadata can stay byte-identical while its logical `system` payload changes. The other eight slot 1 payloads matched their stock hashes on the candidate. Recovery requires the full physical `super` image, including the bytes outside the active logical devices.

## Replay on a workstation

1. On the booted F.20 handset, verify the model, build, boot ID, resolved `super` device, UFS LUN, logical sector size, start and length. Stream the raw block device outside the checkout and compare its SHA-256 with an independent device-side `sha256sum`. Keep the complete raw image private.
2. Generate recovery-mode **read** requests with `python scripts/device_audit/check_super_chunks.py xml --output PRIVATE/read-super.xml`. On this handset, the existing boot/DTBO recovery kit supplies the tested Sahara loader and Firehose client. Verify its GPT range against the live Android values before acquisition. After the read, reset to F.20 and verify a new boot ID and `sys.boot_completed=1`.
3. Assemble a private stock recovery kit with `python scripts/device_audit/check_super_chunks.py stock-kit --android-backup PRIVATE/f20-super.raw --directory PRIVATE/edl --sha256 STOCK_SHA256 --output PRIVATE/stock-kit`. The helper hashes the Android backup and the complete Firehose stream, copies all 17 readbacks and verifies the copies. It produces a manifest and a restore XML with the metadata-containing chunk last. Generating this file leaves the phone untouched.
4. Run `python scripts/device_audit/rehearse_super_layout.py --stock PRIVATE/f20-super.raw --stock-sha256 STOCK_SHA256 --system SYSTEM_IMG --vendor PROJECT_VENDOR_IMG --private-out PRIVATE/rehearsal`. This writes a new regular file. It checks the stock geometry and both metadata slots, writes both target payloads, rereads every allocated partition through each slot's extents, then restores and rehashes the entire original image on the workstation. The two inputs remain recoverable separately from the working file.

The handset's standalone AOSP `lpdump` also parsed both candidate slots from a temporary sparse file. Only that file's metadata prefix contained candidate bytes. Full payload verification used the workstation copy. The format used for the table and checksums follows [AOSP liblp](https://android.googlesource.com/platform/system/core/+/refs/heads/main/fs_mgr/liblp/include/liblp/metadata_format.h).

The complete hashes, physical ranges and per-partition results are in the [qualification record](../build/device/m1-super-layout-2026-11-13.json).

The next hardware checkpoint is a full stock `super` write through 9008, a fresh readback of every byte, and an F.20 boot. The candidate layout additionally needs a trust path for the project vendor and first-stage discovery of the UFS-backed system and vendor. [M1 plan](../plan.md#next-work-on-m1)
