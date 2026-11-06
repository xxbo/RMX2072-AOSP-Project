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
