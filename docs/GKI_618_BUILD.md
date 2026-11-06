# Android 17 GKI 6.18 — Reproducible Build

## Build system

Android 17 GKI 6.18 uses the official Android kernel repo manifest and Kleaf/Bazel build system. Do not treat a direct host make gki_defconfig smoke build as the authoritative GKI distribution build.

The official ARM64 distribution target is:

~~~bash
tools/bazel run //common:kernel_aarch64_dist -- --destdir=dist
~~~

The GitHub Actions workflow reproduces this path on ubuntu-24.04, using the pinned kernel/manifest and the pinned GKI release tag recorded in sources/SOURCE_LOCK.json. Run #5 completed successfully on 2026-11-06 using the upstream source checkout. The new `experiment/gki-6.18-repo-mirror` branch stores the exact kernel/common source snapshot in this repository; run #8 passed the same distribution build using that repository-owned snapshot ([evidence](https://github.com/xxbo/RMX2072-AOSP-Project/actions/runs/42194678844)). Both use the official Kleaf distribution target, not a modules_prepare-only smoke build.

## Pinned inputs

- Kernel source: android17-6.18-2026-09_r13
- Kernel source commit: ecdaacc9a0ee87eaf9544e1836d86bd9d590312e
- Repo manifest branch: common-android17-6.18
- Repo manifest commit: 46a1a5274ff0b40419952c861a8958bba5f28cfc
- Architecture: ARM64 / aarch64
- Build system: Kleaf through tools/bazel
- Rust: CONFIG_RUST=y in the GKI arm64 defconfig; toolchain is synced from the same manifest

Each run archives the resolved repo manifest, kernel and Kleaf source SHAs, build log, Rust configuration evidence, distribution files and SHA-256 checksums. Run #5 completed 1,378 Bazel actions; Bazel reported 1,242.471 seconds elapsed and a successful build. The uploaded artifact contained 158 files and was approximately 688 MB.

## Repository-owned kernel source

The exact `kernel/common` source snapshot is stored on branch `mirror/android17-6.18-2026-09_r13`. Its snapshot commit is `cfa72fb3d7f89372c7e449a4de2477551ea4c29c`, and its commit message records the upstream tag and source commit. The build's local manifest replaces the upstream `common` project with this branch. This is a source-only snapshot without upstream Git history; the official build manifest and toolchain dependencies remain pinned upstream. See [GKI_618_SOURCE_MIRROR.md](GKI_618_SOURCE_MIRROR.md).

## Why the manifest matters

The manifest synchronizes more than kernel/common. Its original project revisions include moving branches: a manifest commit alone does not freeze the dependencies. `build/gki-resolved-manifest.xml`, extracted from successful run #8, now fixes all 58 projects to exact commits, including Kleaf, Clang, Rust and build tools. `lock_gki_workspace.py` applies this overlay before sync and verifies every checkout afterward. The repo launcher/runtime is also pinned in SOURCE_LOCK.json. Bazel external dependencies retain the upstream build definitions and checksums. Building only the kernel/common Git repository with arbitrary host compilers is not equivalent to the official GKI build.

## Build output

The workflow uploads the complete kernel_aarch64_dist output under the artifact rmx2072-gki-618-kernel-N. It also records vmlinux, Module.symvers and module files when provided by the distribution target.

Run #5 produced `Image` (43.5 MB), `Image.gz` (17.7 MB), `Image.lz4` (20.8 MB), `vmlinux` (224.4 MB), `kernel_aarch64_Module.symvers`, `system_dlkm.erofs.img`, `system_dlkm.ext4.img` and the in-tree kernel modules. This proves the generic Android 17 GKI 6.18 ARM64 distribution can be built from the pinned source/toolchain. It does not prove RMX2072 board compatibility, device-tree correctness, vendor module compatibility, bootability or hardware operation.

## Next stages

1. Completed: repository-owned kernel snapshot and full Kleaf distribution build.
2. Inspect the actual GKI config and KMI artifacts.
3. Build a minimal Rust module using the exact kernel Rust toolchain.
4. Add RMX2072 device-specific configuration and platform support.
5. Port drivers one at a time and validate their KMI dependencies.
6. Integrate the resulting kernel, DTB/DTBO and vendor modules only after the board-level dependencies are understood.

## Strict driver gate on main

The main workflow is manual and read-only. It reuses the existing source mirror without creating or updating branches. With `nfc_probe=true`, it builds the NQ-NCI experiment through `ddk_module` against the same `//common:kernel_aarch64` target after the full distribution build. This consumes the real kernel symbols and generated headers. It does not set `KBUILD_MODPOST_WARN` or suppress failed commands. Failure logs are uploaded even when compilation fails.

The earlier modules_prepare-only smoke result remains separate evidence. Neither a successful compile nor a generated .ko proves KMI policy compliance, device-tree binding, module loading or physical NFC operation. Generic 6.18 build products must not be flashed as RMX2072 boot images.

The fully locked mainline run [#9](https://github.com/xxbo/RMX2072-AOSP-Project/actions/runs/42226214281) now passes both the complete generic GKI distribution and the strict NFC DDK build. All 58 project SHAs were verified after sync. Local checking of that run's NFC artifact against its kernel symvers found valid strong-import CRC coverage with no mismatches; see the porting log for the exact report.
