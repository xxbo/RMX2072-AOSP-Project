# RMX2072 development plan

Updated 2026-11-11 for the realme X50 Pro Player Edition (RMX2072, Snapdragon 865 / SM8250). This plan defines progress by what the handset can boot and operate. The [earlier M0–M8 plan](https://github.com/xxbo/RMX2072-AOSP-Project/blob/dfd17d95f25a0cda113af939adaa2be14142d798/plan.md) preserves the source research, legacy builds and original checklists.

## Target system

Boot an Android 17 ARM64 GSI from internal UFS on a project-built ACK 6.18 kernel. Build the RMX2072 device trees, boot ramdisk, device-specific vendor configuration, HALs and required kernel drivers from pinned source. Reuse working upstream drivers and port the board-specific parts. The release must operate independently of the realme Android partitions, F.20 kernel and modules, extracted Android HAL binaries and factory DTB/DTBO. The selected GSI is recorded in [build/gsi.json](build/gsi.json).

| Dependency | Treatment |
| --- | --- |
| F.20 Android, vendor/odm, boot and DTBO | Use for measurements, controlled comparisons and recovery. Identify each borrowed item in a trial and the milestone that replaces it. |
| Board and Android integration | Build the board DTB/DTBO, boot-v2 ramdisk and minimal vendor image from source. Own the fstab, init rules, VINTF declarations, SELinux policy and HAL integration. Test the GSI against this vendor image. |
| Silicon boot ROM, subsequent boot stages, secure world, modem/DSP or peripheral firmware, and calibration | Record each required component separately: source or provenance, who loads it, affected functions and replacement status. Distinguish immutable hardware from replaceable shipped binaries. Any retained factory binary remains an explicit dependency in the release report. A claim of complete factory independence requires evidence accounting for every entry. |

## Verified starting point

| Where the result lives | What the physical test established | What remains open |
| --- | --- | --- |
| [Mainline USB record](build/device/usb-soak-2026-11-09.json) | 6.18 reached the RAM diagnostic and passed 606 seconds of paced ACM traffic. The F.20 boot reader and original DTBO were restored and checked. | Uncapped USB transfers showed short reads. Android ADB and a full `super` restore have separate acceptance tests. |
| [Watchdog](https://github.com/xxbo/RMX2072-AOSP-Project/pull/2), [EDL](https://github.com/xxbo/RMX2072-AOSP-Project/pull/3) and [UFS HS-G3](https://github.com/xxbo/RMX2072-AOSP-Project/blob/f2f6385af354d1c157b319030d5d458134a66acf/build/device/ufs-g3-2026-11-10.json) | Two warm boots enumerated six LUNs at two-lane HS-G3 and completed 76 MiB of direct reads each. Software return to EDL worked. | The accepted profiles use the factory-derived DTB and original DTBO. Cold start on project-built trees remains open. |
| [Dynamic partitions](https://github.com/xxbo/RMX2072-AOSP-Project/pull/7) and [verified mounts](https://github.com/xxbo/RMX2072-AOSP-Project/pull/8) | 6.18 read both F.20 super metadata slots and mounted stock system, vendor and product read-only through dm-verity. | A self-contained layout for the target GSI and project vendor still needs validation. |
| [Android 17 trial](https://github.com/xxbo/RMX2072-AOSP-Project/blob/f2f6385af354d1c157b319030d5d458134a66acf/build/device/gsi17-usb-mount-2026-11-10.json) | The phone mounted CP3A.260905.010 over USB and ran its toybox in a chroot. Android release 17 and API 37 came from the mounted image. | The diagnostic init remained PID 1. The recorded `sys.boot_completed=1` belongs to the restored F.20 system. |

The November 10 records above are from the [bring-up PR stack](https://github.com/xxbo/RMX2072-AOSP-Project/pull/9). Keep the tested commit, image hashes and boot identity with each result.

## Milestones and acceptance

| Milestone | Status | Evidence required on RMX2072 |
| --- | --- | --- |
| M1 · Headless Android 17 from UFS | **Active.** USB-backed GSI execution demonstrated. | Cold-boot with the image-serving computer disconnected. After boot, connect ADB and record the 6.18 kernel release, Android API 37, Android init as PID 1, first- and second-stage init logs, and the UFS-backed sources of system and the project-built vendor. Record any factory boot/DT or firmware dependencies still in use. |
| M2 · Project-built board description | Open. Can proceed alongside M1. | Boot with source-built board DTB/DTBO and ramdisk. Record packaged and selected tree identities. Reproduce cold boot, six UFS LUNs, verified partition reads, USB diagnostics and recovery. Repeat M1 on these exact artifacts. |
| M3 · Interactive Android desktop | Open. Panel and touch work can start on the diagnostic kernel. | Show a test pattern on the physical panel and record GT9886 input events. Integrate the allocator, graphics composer and SurfaceFlinger with the project vendor. Record the launcher rendering, a physical tap opening an app and Android boot completion on the same build. |
| M4 · Daily-use hardware and release | Open. Validate each subsystem independently. | Exercise calls and mobile data, Wi-Fi/Bluetooth, audio, camera, sensors and biometrics. Verify charging, thermal control, suspend/wake and encrypted userdata across reboot. Publish hardware results, remaining firmware dependencies, build inputs, image hashes and a tested update/recovery procedure. |

## Automated handset testing

Run the checks from the computer attached to the RMX2072. CI builds the artifacts and exercises host-side checks. The handset supplies the boot, driver and physical evidence. The bring-up branch already has [ACM, UFS, super, verity and GSI probes](https://github.com/xxbo/RMX2072-AOSP-Project/tree/f2f6385af354d1c157b319030d5d458134a66acf/scripts/device_audit). The common report and the Android test stages below are planned work.

| When to run | Automated checks | Physical evidence |
| --- | --- | --- |
| M1 bring-up, before ADB | Through ACM, identify the diagnostic trial and kernel, exercise paced USB, enumerate the six UFS LUNs and verify read-only partition mappings. On the USB-backed profile, check verity and GSI toybox separately. At the Android init handoff, capture the earliest mount result and its error from the early log channel. | Label USB-backed trials and UFS cold boots separately. |
| M1 with ADB; repeat for M2 | After a disconnected cold start, attach ADB. Check the running kernel, API 37, the identity of PID 1 and the backing devices for system and the project vendor. For M2 also verify the selected DTB/DTBO and repeat the USB, UFS and recovery checks. | Match all observations to the same boot and image set. A boot of the restored F.20 reader gets its own report. |
| M3 interactive desktop | As the relevant HALs come up, run matching VTS modules. Once the framework is ready, run focused CTS modules and use UI Automator for repeatable launcher and Settings flows. Record the seed and event count for Monkey stress runs so a crash or ANR can be replayed. | Verify panel output and record a real GT9886 touch opening an app. Injected input covers the Android UI path only. |
| M4 daily use | Expand VTS/CTS and functional checks by enabled subsystem. Exercise suspend/wake, encrypted-data persistence and reconnection after reboot. | Use a fixture or operator for observations such as audible output, a completed call or the captured camera scene. Record the observation alongside the automated result. |

### Failure report and retest

- Emit a short summary and machine-readable results per trial. Record the build and boot identity, test name, expected and observed values, and a timestamp or log reference. Use `PASS` or `FAIL` for executed checks, `BLOCKED` for a missing prerequisite, and `NOT RUN` for checks outside that trial. Identify host, cable or runner errors separately.
- Lead with the first observed failure on each affected path. If the vendor mount fails, attach the mount error and mark dependent HAL tests blocked. Keep independent USB/UFS results visible. Use the early boot transcript before ADB and collect logcat or a bugreport once the required Android services are available.
- After a fix, rerun the failed check, its subsystem tests and the known-good boot/USB/UFS checks. Compare new failures, fixes and remaining failures with the previous comparable build. For a changed build, start a fresh targeted suite run. Within a run on the same build, use the suite retry feature for failed or unexecuted cases.

See [VTS for HALs and kernels](https://source.android.com/docs/core/tests/vts), [CTS execution and retry](https://source.android.com/docs/compatibility/cts/run), [UI Automator](https://developer.android.com/training/testing/other-components/ui-automator) and [Monkey](https://developer.android.com/studio/test/other-testing-tools/monkey).

## Next work on M1

1. **Capture the first Android init handoff.** Keep the verified 6.18 kernel and G3 DT configuration fixed. Prepare a boot-v2 ramdisk for Android first-stage init and retain an early log channel across the handoff. A USB-backed trial can produce the first log while local storage work proceeds. Record the first successful mount or the first failed operation and its error. Use this trial to produce the first [failure report](#failure-report-and-retest) from the existing probes.
2. **Build the minimal vendor and verify its interfaces.** Start with board fstab, init and device-node rules, VINTF and SELinux policy. Check the selected GSI against the built vendor and record the AVB trust inputs actually used for system and vendor. F.20's FCM 5, VNDK 30 and GSI key list describe the comparison system. They do not define the interfaces of the new vendor.
3. **Place the GSI on UFS.** The current F.20 logical group falls short by 1,095,585,792 bytes if all other logical partitions are kept. Calculate the fit for the chosen GSI and project vendor using actual image sizes. Identify the affected partitions and verify a recovery route for them before changing their layout. The existing boot/DTBO restore covers those two partitions. [Measured layout](docs/GSI_PREFLIGHT_2026-11-06.md)
4. **Run the M1 cold-boot test.** Collect kernel, PID 1, mount and ADB evidence from the same boot. Record the first unmet criterion if the boot stops. Keep the USB-backed fixture available to isolate storage and userspace regressions.

Each milestone record should identify the source revision, kernel/DT/ramdisk/GSI/vendor hashes, boot conditions, observed output and the route back to a known-good image. Track subsystem results in the [compatibility matrix](docs/COMPATIBILITY_MATRIX.md) and use the [driver dependency map](docs/DRIVER_DEPENDENCY_MAP.md) to sequence ports.
