# Android 17 GKI 6.18 Source Mirror

## Pinned source

- Upstream repository: https://android.googlesource.com/kernel/common
- Upstream tag: `android17-6.18-2026-09_r13`
- Upstream commit: `ecdaacc9a0ee87eaf9544e1836d86bd9d590312e`
- Repository-owned branch: `mirror/android17-6.18-2026-09_r13`
- Snapshot commit: `cfa72fb3d7f89372c7e449a4de2477551ea4c29c`
- Kernel version in the source Makefile: Linux 6.18.32

Browse the source snapshot:
https://github.com/xxbo/RMX2072-AOSP-Project/tree/mirror/android17-6.18-2026-09_r13

## Snapshot model

The mirror branch contains the complete tracked source tree exported from the pinned upstream commit. Its root is the Linux kernel source tree, so it can be used as the `common/` project in the Android kernel repo workspace.

This is a pinned source snapshot, not a full-history Git fork:
- The upstream source commit and tag are preserved in the mirror commit message.
- The snapshot branch intentionally has one root commit and does not duplicate the multi-gigabyte upstream Git history.
- Upstream COPYING, LICENSES and per-file SPDX identifiers are preserved by the source archive.
- The snapshot is immutable for this pinned GKI release. A newer GKI release gets a new mirror branch.

## Build workspace

The GitHub Actions build still initializes the official Android `kernel/manifest` branch `common-android17-6.18`. A local manifest removes the upstream `kernel/common` project and replaces it with this repository's mirror branch.

Kleaf, Clang, Rust, Bazel, build tools and their dependencies remain synchronized from the pinned official Android kernel manifest. Only the kernel/common source tree is mirrored into this project; mirroring every build-tool repository is unnecessary for a reproducible kernel build.

The build script verifies both:
1. The checked-out mirror commit equals the commit produced by the mirror job.
2. The mirror commit message's `Upstream-Commit` equals the pinned official GKI source SHA.

This prevents a moving branch or unrelated kernel source from silently entering the build.

## Validation

The first full upstream-source build succeeded in Actions run #5. Actions run #7 creates this repository-owned source snapshot and then builds the GKI distribution using the mirror. Its final build result is tracked in the workflow run linked from the project README.
