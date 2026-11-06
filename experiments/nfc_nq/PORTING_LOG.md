# NQ-NCI Porting Log

## 2026-11-06 — First GKI 6.18 compile pass

### Build environment

- GKI source ref: android17-6.18-2026-09_r13
- GKI commit: ecdaacc9a0ee87eaf9544e1836d86bd9d590312e
- Runner: GitHub Actions ubuntu-24.04
- Build stage: gki_defconfig -> modules_prepare -> external module compile
- Workflow run: [#5](https://github.com/xxbo/RMX2072-AOSP-Project/actions/runs/42183726745)
- Artifact: [nfc-nq-gki-618-5](https://github.com/xxbo/RMX2072-AOSP-Project/actions/runs/42183726745/artifacts/13486881243)

### Environment issue and resolution

The first attempts stopped before the driver compile because the host build environment lacked the DWARF development headers required by the kernel's gendwarfksyms host tool. The correct Debian/Ubuntu dependency is libdw-dev (plus libelf-dev and zlib1g-dev); the workflow now installs these packages. The pinned GKI defconfig and modules_prepare then completed.

### Driver compile findings

The first compile reached nq-nci.c and reported four errors:

1. nfc_ioctl_power_states() had external linkage without a previous prototype.
2. nfc_ioctl_core_reset_ntf() had external linkage without a previous prototype.
3. nfc_ioctl_nfcc_info() had external linkage without a previous prototype.
4. no_llseek was not declared in the pinned 6.18 headers; noop_llseek is available.

These three functions are only called inside this translation unit, so they are now static. The file_operations llseek callback now uses noop_llseek. The changes are in commit a5b4aab928ad2df2a4ad93e50fa247522067a353.

### Current result

- GKI source fetch and immutable SHA verification: passed.
- GKI defconfig: passed.
- modules_prepare: passed.
- First NQ-NCI C compile: reached the driver and failed on the four source issues above.
- Corrective patch: committed; a new compile run is expected.
- .ko generation, modpost, KMI audit, module load, probe and hardware tests: not yet passed or attempted.

The first compile is useful evidence, but it is not a successful module build. Continue to record each compile failure separately from host build-environment failures.


## 2026-11-06 — First AArch64 module artifact produced

### Build result

- Source revision: branch commit a5b4aab928ad2df2a4ad93e50fa247522067a353
- Workflow: [#6](https://github.com/xxbo/RMX2072-AOSP-Project/actions/runs/42184161348)
- Artifact: [nfc-nq-gki-618-6](https://github.com/xxbo/RMX2072-AOSP-Project/actions/runs/42184161348/artifacts/13486438423)
- Result: compile-smoke workflow passed; an AArch64 relocatable module nq-nci.ko was produced.
- Module SHA-256: 66813df1b9c05a5abf7f514e325a420f42141e694331e8522920fbac953398a4
- GKI config SHA-256: c435bb4dfeeed7c1870f166c28162e76b8df8aa942cef3ea4c5c54fb7b590e6b

### Important qualification

The module build used modules_prepare rather than a complete GKI kernel build. MODPOST explicitly warned that the output Module.symvers was missing and therefore emitted unresolved-symbol warnings. KBUILD_MODPOST_WARN=1 allowed the .ko to be produced so the C/API compile could be tested. BTF generation was skipped because vmlinux was unavailable.

This artifact proves that the current driver source compiles and links into an ARM64 relocatable module against the prepared pinned 6.18 source headers. It does **not** prove that the module imports only exported/protected GKI symbols, has valid symbol CRCs, can be loaded, or works on the handset.

### Next gate

Build the full pinned GKI kernel to obtain the authoritative Module.symvers, extract the module's undefined imports, compare them against the GKI exported-symbol and protected KMI lists, then rebuild with symbol-version checking. The legacy GPIO API is a likely area to review, but no symbol should be declared unavailable based only on the current modules_prepare MODPOST warnings.


## 2026-11-06 — Probe/remove resource cleanup review

A source review found an optional eSE GPIO cleanup defect inherited from the downstream driver:

- The probe error path checked the original DT GPIO number rather than the driver's successfully-requested GPIO state. If the optional eSE GPIO request failed but a later optional clock-request GPIO setup failed, the unwind path could call gpio_free() on a line it did not own.
- The remove path used 'ese_gpio > 0', which mishandles GPIO 0 and does not correctly express the invalid-GPIO sentinel. It also freed optional CLKREQ/FIRM lines without validating them.

The port now frees the eSE line only when the driver's stored GPIO is valid and guards GPIO release with gpio_is_valid(). This is a lifecycle-safety correction before any hardware test; the driver still uses the legacy integer GPIO API pending the GKI KMI audit.


## 2026-11-06 — Compile pass after GPIO ownership cleanup

- Workflow: [#11](https://github.com/xxbo/RMX2072-AOSP-Project/actions/runs/42184985092)
- Artifact: [nfc-nq-gki-618-11](https://github.com/xxbo/RMX2072-AOSP-Project/actions/runs/42184985092/artifacts/13486274740)
- Result: passed; the GPIO cleanup changes compile and the AArch64 relocatable module is produced.
- Module SHA-256: 63701348f0d369feb2399ec0b7e8c8569d33c6d7bf92786355af893d4dbff601
- MODPOST still reports the expected missing-Module.symvers warning from the modules_prepare-only build. The KMI allow-list audit has been added to the next workflow run.

## 2026-11-06 — Compare previous smoke imports to real kernel exports

The run #11 smoke module (SHA-256 `63701348f0d369feb2399ec0b7e8c8569d33c6d7bf92786355af893d4dbff601`) was downloaded and its ELF64 undefined symbols parsed locally. All 75 imported symbol names occur in `kernel_aarch64_Module.symvers` extracted from successful full Kleaf run #8. There are no missing strong exports in this name-presence comparison.

This corrects any assumption that the legacy GPIO names are necessarily unavailable in this pinned kernel. The module was still built by modules_prepare with no authoritative CRCs, so this comparison does not certify symbol versions, namespace imports, protected KMI policy, signatures or loading. The strict DDK build must pass independently. The reusable `scripts/kernel_research/audit_module_exports.py` records module/symvers hashes and export metadata; its report remains local.

The previous smoke module advertises `modversions` in vermagic but has a zero-byte `__versions` ELF section. This is direct evidence that its name-presence result cannot substitute for a versioned strict build.

The same 75 imports also appear in run #8 `abi_symbollist.raw`; every corresponding Module.symvers provider is vmlinux and none declares an export namespace. This narrows the outstanding checks but does not replace the strict module build, protected-export/signature policy or physical tests.

The ELF audit now parses both standard and extended module-version sections and can require strong-import CRC coverage/matches against the full-build Module.symvers. The old smoke artifact is a negative control: `--require-crcs` correctly fails with 75 missing CRCs and zero version entries. Future strict DDK runs invoke this audit automatically. The already-running run uses its original pinned checkout and will be audited locally after artifact download.
