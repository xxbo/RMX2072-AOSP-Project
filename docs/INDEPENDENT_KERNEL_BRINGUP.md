# Independent 6.18 kernel bring-up

The current goal is a stable, RAM-only 6.18 diagnostic environment on RMX2072. GSI, Android framework/vendor integration, super resizing and user-data mounts are deferred.

## Platform revision

[Run 42326221558](https://github.com/xxbo/RMX2072-AOSP-Project/actions/runs/42326221558) builds revision `126778e`, requiring Qualcomm hardware mutex and APSS watchdog support built-in. SCM, USB gadget/ACM and pstore dependencies are explicitly pinned alongside the existing platform requirements. CI checks every fragment assignment and publishes its actual config audit. A build result alone does not prove a driver probed or a kernel ran.

Stock live FDT confirms SMEM at 0x80900000 (0x200000 bytes), TCSR hardware lock number 3, and APSS watchdog registers at 0x17c10000 (0x1000 bytes). The pinned SM8250 DTS references the same lock and watchdog address. Its watchdog driver can adopt hardware left running by firmware. Neither missing driver has been proven to explain the previous loop. The USB-only board DTS remains unchanged for this platform comparison; storage, display and remote processors stay disabled.

## Runtime gates

1. Verify the candidate's source/config/image hashes, built-in dependencies, boot-v2 geometry, AVB envelope and paired DTBO. Verify the exact current boot/DTBO by full pre-write reads and preserve known-good recovery images.
2. Require an actual diagnostic banner and `uname` reporting the expected 6.18 build, plus kernel/UDC logs. A logo, black display, reset loop or USB connection sound is insufficient evidence.
3. Save `/proc/cmdline`, `/proc/mounts`, uptime, CPU online state, driver probe/deferred-probe information, regulator/clock failures and watchdog status. Confirm no handset block filesystem is mounted.
4. Observe at least ten minutes without spontaneous reset, then exercise moderate RAM-only CPU/memory work and check logs. This is an initial stability gate, not full hardware qualification.
5. Validate controlled restart/recovery before introducing UFS. The later UFS milestone is read-only enumeration and partition identification, with a separate board revision; Android/user-data mounting is outside this stage.

## Recovery and log controls

The original/debug stock boot and original DTBO have both been recovered with full post-write verification. Stock Android has subsequently reached Launcher. Software ADB-to-EDL works while Android is running. During the second diagnostic loop, holding both volume buttons across a restart entered 9008 without shorting. That observation is specific to the tested state; it is not a universal hardware-entry recipe.

`scripts/device_audit/pstore_continuity.py` writes unique markers only to RAM-backed kmsg/pmsg, never reboots or erases logs, and archives post-reboot evidence outside the public checkout. Stock console_loglevel was 4, so the control uses an explicit level-0 marker. Its report distinguishes a full exact marker from an exact match of the unique 64-bit identifier.

On the original debug layout, a normal reboot preserved the level-0 marker's identifier, but its prefix and other console text contained damaged bytes. A software EDL/Sahara/UFS-read/reset cycle also produced console text with a visibly similar marker at the expected pre-reboot time; neither its full token nor full identifier matched exactly. This is evidence of partial text retention, not a successful byte-integrity control. Do not equate an exact-match failure with all RAM being cleared. Raw archives remain local.

## Candidate aligned stock-kernel reader

The available OEM pstore code subtracts a 0x1000-byte device-info region before allocating dump zones; pinned ACK does not. With the captured 4-MiB sizes, setting OEM `devinfo-size` to zero makes its source-derived console address 0xb0180000, matching the ACK console position. The ftrace/pmsg ordering still differs: this reader is not claimed to align those buffers. The available OEM source is not proven identical to the running F.20 binary, so runtime verification remains required.

`scripts/build/prepare_pstore_reader.py` only accepts the exact previously booted debug image. It changes `devinfo-size` from 0x1000 to zero in all 21 applicable trees in the 25-DTB boot bundle, including selected tree 12, and updates the AOSP boot-v2 ID. It verifies that all differences are confined to those properties and the ID; kernel, ramdisk, load metadata, partition length and AVB envelope remain byte-identical. The original DTBO contains no ramoops node and is not changed. The device-info log will be unavailable in this candidate. Its stock signed payload hash is still mismatched, as with the already booted Magisk image; this remains an unlocked-device experiment.

Candidate SHA-256: `99884c2cc65b704e5d5a1f5b2461ca38e6065008ea2db2ef748ced4597c05bbd`, 41 changed bytes. The independent FDT parser confirmed all 21 new zero values; two tests cover unaligned concatenated DTB placement and rejection of an unexpected original value. Candidate preparation is not device-boot or cross-kernel logging evidence. Validate this stock-kernel reader before relying on it after another 6.18 attempt.
