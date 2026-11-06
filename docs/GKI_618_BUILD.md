# Android 17 GKI 6.18 — Reproducible Build

## Build system

Android 17 GKI 6.18 uses the official Android kernel repo manifest and Kleaf/Bazel build system. Do not treat a direct host make gki_defconfig smoke build as the authoritative GKI distribution build.

The official ARM64 distribution target is:

~~~bash
tools/bazel run //common:kernel_aarch64_dist -- --destdir=dist
~~~

The GitHub Actions workflow reproduces this path on ubuntu-24.04, using the pinned kernel/manifest and the pinned GKI release tag recorded in sources/SOURCE_LOCK.json. Run #5 completed successfully on 2026-11-06. The build used the official Kleaf distribution target, not a modules_prepare-only smoke build.

## Pinned inputs

- Kernel source: android17-6.18-2026-09_r13
- Kernel source commit: ecdaacc9a0ee87eaf9544e1836d86bd9d590312e
- Repo manifest branch: common-android17-6.18
- Repo manifest commit: 46a1a5274ff0b40419952c861a8958bba5f28cfc
- Architecture: ARM64 / aarch64
- Build system: Kleaf through tools/bazel
- Rust: CONFIG_RUST=y in the GKI arm64 defconfig; toolchain is synced from the same manifest

Each run archives the resolved repo manifest, kernel and Kleaf source SHAs, build log, Rust configuration evidence, distribution files and SHA-256 checksums. Run #5 completed 1,378 Bazel actions; Bazel reported 1,242.471 seconds elapsed and a successful build. The uploaded artifact contained 158 files and was approximately 688 MB.

## Why the manifest matters

The manifest synchronizes more than kernel/common. It also pins the Kleaf build repository, Clang, Rust toolchain, build tools and Bazel module dependencies. Building only the kernel/common Git repository with arbitrary host compilers is not equivalent to the official GKI build.

## Build output

The workflow uploads the complete kernel_aarch64_dist output under the artifact rmx2072-gki-618-kernel-N. It also records vmlinux, Module.symvers and module files when provided by the distribution target.

Run #5 produced `Image` (43.5 MB), `Image.gz` (17.7 MB), `Image.lz4` (20.8 MB), `vmlinux` (224.4 MB), `kernel_aarch64_Module.symvers`, `system_dlkm.erofs.img`, `system_dlkm.ext4.img` and the in-tree kernel modules. This proves the generic Android 17 GKI 6.18 ARM64 distribution can be built from the pinned source/toolchain. It does not prove RMX2072 board compatibility, device-tree correctness, vendor module compatibility, bootability or hardware operation.

## Next stages

1. Mirror the exact pinned `kernel/common` source snapshot into a repository branch and build from that mirror.
2. Inspect the actual GKI config and KMI artifacts.
3. Build a minimal Rust module using the exact kernel Rust toolchain.
4. Add RMX2072 device-specific configuration and platform support.
5. Port drivers one at a time and validate their KMI dependencies.
6. Integrate the resulting kernel, DTB/DTBO and vendor modules only after the board-level dependencies are understood.
