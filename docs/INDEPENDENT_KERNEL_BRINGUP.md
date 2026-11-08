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

## Third physical result and next control

Full pre-reads matched the verified reader boot plus original DTBO. The third pair was written, both complete readbacks matched the candidate hashes, and reset succeeded. No diagnostic USB appeared; the user observed another restart loop. Holding both volume keys recovered 9008 again. Pre-restore reads matched the diagnostic pair; restoring the shared-layout reader plus original DTBO passed full readback verification. Stock Android completed boot afterwards, without formatting data or changing other partitions.

Captured pstore has a 233,029-byte console and 235-byte pmsg. Neither contains a diagnostic phase, 6.18 kernel-version record or identified new kernel panic. Console content is still pre-trial stock output. Numeric timestamps such as `[6.18...]` are not kernel-version proof. The omissions therefore remain an early handoff/kernel-init boundary problem, not a diagnosed driver panic; no claim of successful 6.18 execution is made.

The next control packages the device-tested stock 4.19 kernel and its 25-DTB shared-reader bundle with the diagnostic command line/BusyBox initramfs, paired with unchanged original DTBO. Its goal is to test PID1 phase recording independently of the new kernel and upstream DTS. Actual stock config has ACM disabled, so this control does not require an ACM terminal to succeed. All BusyBox applets used by diagnostic init were found on the device, but its `reboot` applet is absent.

For an automatic return, `reboot_edl.c` is statically built with installed Android NDK 28.2.13676358 for API 29. `--check` ran successfully on the handset without rebooting. It invokes RESTART2 with `edl` only with that explicit argument. The ramdisk builder can include this helper and a control-only 90-second timer; normal diagnostic images have no timer file and do not schedule this return. Helper binary SHA-256 is `cde8d7dd01712ce96335e08088b2e8d964c71b7307e5915ba3817e17c0809d29`. This is a local diagnostic helper build, separate from the Actions kernel build.

`pack_stock_control.py` accepts only the verified shared-reader boot and confirms that its extracted stock kernel/DTB bytes survive packaging unchanged. Prepared control boot SHA-256 is `d2a1885c39fcfabe01717f1e4bca25e4d587b0cab839beb5822255a5addde90f`. Its AVB envelope remains stock metadata around a modified payload, for this unlocked device only. This control is not a 6.18 image and has not yet been device-tested at this checkpoint.

## Stock control result: PID 1 exits

The stock control was subsequently flashed and fully readback-verified with unchanged original DTBO. It did not return to EDL automatically. The user reached stock Recovery; its displayed reason was `phenix.kernel_to_recovery`. The displayed Android-init SIGABRT text had an unverified `02-02` timestamp and is not attributed to this experiment. Recovery restart while holding both volume keys entered 9008; restoring the logging reader and original DTBO passed full readback verification, and Android completed boot.

Freshly captured pstore contains the actual stock-kernel control command line with `rdinit=/init`, an initramfs-unpack attempt, execution of `/init`, and `Kernel panic - not syncing: Attempted to kill init! exitcode=0x00000000` with PID 1 named `sh`. A BusyBox mount process attempted devtmpfs shortly before the panic; the stock kernel has DEVTMPFS disabled. This establishes execution of the stock control's script path, not 6.18 execution. The same log reports 3,183 corrected bytes and 1,080 unrecoverable ECC blocks: some text remains damaged, so retain raw evidence and avoid treating all decoded bytes as intact.

The diagnostic script had an unsafe gadget-directory failure fallback, `exec sh`, which could replace PID 1 with a shell lacking usable input and exit successfully. The precise triggering command still needs tracing; this branch is not declared the proven cause. The revised ramdisk uses a separate shell supervisor as PID 1, runs the diagnostic body as a traced child with stdin from `/dev/null` and stderr/stdout to `/dev/kmsg`, records child exits, and remains alive on failure. The optional timed EDL return belongs to the supervisor rather than a child that might terminate. The body now reports gadget-directory failure and exits only its child process. A kmsg device node exists in the archive before either script runs. Both scripts pass shell syntax checking.

Prepared supervisor control boot SHA-256 is `591876c73449f55181d3f1b48a11c1a448169e6aac43709dc9495b37a2c416b6`; stock kernel and DTB bundle are unchanged. Validate this stock control before another 6.18 trial.

## November 8: supervisor control passes

The handset was reverified on stock 4.19 Android with completed boot, UID 0 and unlocked state. The new archive was independently listed by the handset's BusyBox, confirming separate `init`/`diag-init.sh`, kmsg node, return helper and timer file. After matching reader/original-DTBO pre-reads, supervisor control `591876c7...` was written and fully readback-verified; DTBO remained original.

It automatically returned to 9008 approximately 90 seconds later; Sahara completed without a physical-button recovery. An intermediate status update incorrectly described the return as missing before reading the completed background monitor; its saved log confirms the successful return. Pre-restore reads again matched the control image and original DTBO. The logging reader was restored, both readbacks matched, and Android completed boot.

Captured pmsg records stock `4.19.157-perf+` supervisor start, diagnostic init, UDC present, UDC bind failure and console-shell preparation, followed by a complete `phase=control-return-edl` marker. Console also records the `reboot-edl` process restarting with command `edl`. ACM bind/ttyGS0 failures are expected for the stock configuration, which has ACM disabled. Some preserved bytes remain damaged (the pmsg reports three corrected bytes and two unrecoverable blocks), so exact recovered lines and partial text must remain distinguishable. This positive control establishes the supervised diagnostic/automatic-return path on stock kernel; it is not a 6.18 runtime result. The next trial reuses this tested ramdisk with the existing hardware-mutex/watchdog 6.18 build and shared-layout DTS, without additional platform changes.

## Fourth 6.18 trial and isolated kernel-handoff probe

The supervised ramdisk was paired with the same 6.18 kernel/upstream-binding board DTS. Boot SHA-256 `1e3411541f6f49bd504eaaeedf5120309eb0966b1f3d5db67353bb28c51f5e8e` and the unchanged no-op DTBO were fully readback-verified before reset. No diagnostic USB or automatic EDL return appeared; the user observed another restart loop. Both-volume-key recovery worked again. Diagnostic pre-restore hashes matched; the original-DTBO/log-reader pair was restored and fully verified. Android completed boot.

Raw captures are local under outputs/device-root-after-618-attempt4-2026-11-08. Pstore contains 235 bytes of pmsg and 233,029 bytes of console, with no new identifiable 6.18 version, supervisor phase or panic. The stock control has already validated the supervised ramdisk, but the target's early boundary remains unresolved.

The next isolation keeps the verified stock-reader DTB bundle (only logging-layout properties differ from stock), original DTBO and identical supervised RAM-only ramdisk; only the kernel is replaced by the hash-verified 6.18 Image. This probes the bootloader/kernel/DT boundary. Downstream 4.19 board bindings are not assumed compatible with 6.18, so neither a failure nor partial kernel progress should be represented as supported hardware operation.

`pack_stock_control.py --kernel-override ... --expected-kernel-sha256 ...` verifies raw ARM64 magic and exact hash, preserves the source DTB bundle byte-for-byte and retains load/OS metadata. The default stock control still reproduces the successful `591876c7...` image byte-for-byte, and an incorrect override hash is rejected before packaging. Prepared handoff boot SHA-256 is `e61a93e1fcf989bb261426a726632f27eb21889abe8d8e48b79796204642f516`; pair only with original DTBO. It is not yet device-tested at this checkpoint.
