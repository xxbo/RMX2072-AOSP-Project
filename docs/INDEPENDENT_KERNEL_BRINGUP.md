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

This first reader was subsequently written after matching pre-reads and fully readback-verified; original DTBO stayed unchanged. It booted stock Android with UID 0, and live FDT confirmed `devinfo-size=0`. Its EDL/read/reset continuity control still showed damaged marker bytes. Alignment alone therefore did not establish a reliable log path. No physical DRAM fault has been diagnosed from these observations.

The next logging revision uses explicit DT `ecc-size=16` on both the ACK diagnostic writer and the stock reader; both actual kernel configurations include Reed-Solomon encode/decode support. Use 16, not the module-parameter shorthand 1, because DT parsing takes the literal parity-byte size. The reader builder's optional `--ecc-size 16` patches only the existing ECC properties in addition to devinfo and the boot ID. Prepared ECC-reader SHA-256 is `5ba5770fae6e5eae8c5474cbe497a77de12fa6197bf2d34a226789efba93a065` (62 differing bytes relative to the known booted original debug image). This candidate still needs physical boot and full-token continuity validation; the writer's device tree must be recompiled and its actual ECC value verified before packaging. Ftrace/pmsg ordering remains unaligned, so only console compatibility is targeted.

That ECC reader subsequently booted successfully, with live FDT confirming devinfo zero and ECC 16. Its stock-to-stock EDL/read/reset control preserved the complete unique token in pmsg and the exact 64-bit identifier in console; the complete console token still did not match. This validates stock-layout pmsg retention for this tested path, not cross-kernel pmsg compatibility or full console integrity.

The shared-layout revision sets ftrace-size to zero on both writer and reader, retaining the full original 4-MiB reservation and 0x200000 pmsg capacity. This removes the OEM/ACK ordering difference: seven 0x40000 dump zones, console at 0xb01c0000, pmsg at 0xb0200000, ECC 16, no device-info or ftrace buffer. Reader preparation uses `--ecc-size 16 --no-ftrace`; SHA-256 `9ae2f907fd029e88c841121f4fbeb6f3a1ae32322a6703d8d142bbba31bb93c3` (83 differing bytes). Validate this revision independently before pairing it with the new kernel.

Diagnostic init now creates the RAM-backed pmsg character node from its sysfs major/minor and records the actual kernel release with phases `init`, `udc-present`, `udc-bound` or `udc-bind-failed`, `acm-shell-ready`, or `no-udc`. The sysfs pmsg path was verified on the stock device. This changes only diagnostic observability, not handset block storage. A recovered 6.18 phase can prove that PID 1 ran even if USB failed, but it cannot by itself establish stability. `usb_diag_console.py` prepares read-only ACM runtime collection and requires an actual 6.18 uname line rather than accepting echoed commands as proof.

## Verified inputs for the third physical trial

Kernel run 42326221558 passed. Local rechecking confirmed all 49 fragment assignments, matching SHA256SUMS for the selected outputs and all 58 locked manifest project revisions. The actual config has both `HWSPINLOCK_QCOM=y` and `QCOM_WDT=y`; the [new config audit](../build/device/bootstrap-platform-revision2-config.json) is separate from the earlier configuration snapshot. Kernel Image SHA-256 is `3b437ded9bb2de1870f5933d85918f11a6ca6d982eb2cb0b36a70e021f588e33`.

Shared-layout device-tree [run 42328624543](https://github.com/xxbo/RMX2072-AOSP-Project/actions/runs/42328624543) also passed compilation and real overlay application. Its downloaded files match provenance hashes. The packager now requires the hardware mutex/watchdog, initramfs prerequisites, ECC codec configuration and exact shared ramoops layout; a prior no-ECC/ftrace-enabled DT cannot accidentally pass this gate.

The shared-layout stock reader (`9ae2f907...`) was written after matching pre-reads, fully readback-verified and successfully booted. Live FDT confirms devinfo zero, ftrace zero and ECC 16. Its subsequent EDL/UFS-read/reset control recovered the **complete console marker exactly**, with a changed boot ID and completed stock Android boot. This establishes one positive console continuity control for the intended recovery path, not universal RAM integrity or 6.18 execution. The local kit now contains this boot as `images/boot-log-reader.img` with paired original DTBO XML; unchanged original/debug recovery images remain available.

The third diagnostic initramfs mounts proc with an explicit BusyBox invocation before installing applet links, removing a potential `/proc/self/exe` installation dependency. This is a robustness fix, not a proven cause of the earlier loop. Shell syntax and eight focused AVB/reader-boundary tests pass. The [candidate record](../build/device/independent-kernel-candidate-2026-11-07.json) records the exact composed kernel/DT/ramdisk/image hashes. Prepared boot is `8af332e7fd63a8523cbf55f33a8e8c21a58eb69955145e61d1ed1512c70db969`; DTBO is `513e851e3540370b9e263d72e904861b102f16b3c5a1bea2e059b00cc1344589`. Device execution remains pending at this checkpoint.
