# Source Manifest

> Snapshot date: **2026-11-06 UTC**
> Repository: [xxbo/RMX2072-AOSP-Project](https://github.com/xxbo/RMX2072-AOSP-Project)
> Target: realme X50 Pro Player Edition — RMX2072 / bladerunner_48m / Snapdragon 865 (SM8250/Kona)

This file is the human-readable index of the immutable source pins in [SOURCE_LOCK.json](./SOURCE_LOCK.json). The commit SHA is authoritative; branch names are retained only to show where the pin was found.

## Official Realme kernel sources

| Role | Repository / ref | Kernel | Pinned commit | Notes |
|---|---|---:|---|---|
| Device-specific baseline | [realmeX50Pro-5GPlay_AndroidQ-kernel-source](https://github.com/realme-kernel-opensource/realmeX50Pro-5GPlay_AndroidQ-kernel-source/tree/master) · master | 4.19.81 | 24a15224fbae8ab0e8ba29a9046c06ee7a9f53a4 | Official player-edition source; single branch; upload commit dated 2020-06-30 |
| Later shared reference | [realme_GTneo2-X50pro-GTMasterExploratory-AndroidS-kernel-source](https://github.com/realme-kernel-opensource/realme_GTneo2-X50pro-GTMasterExploratory-AndroidS-kernel-source/tree/master) · master | 4.19.157 | 4e5ec4aeeb781851b0fe6c268d9ba69953166fda | Shared source for GT Neo2 / X50 Pro / GT Master Explorer; latest commit dated 2023-03-17 |

## Community kernel references

| Role | Repository / ref | Kernel | Pinned commit | Notes |
|---|---|---:|---|---|
| Current inspected community baseline | [SM8250-Common/android_kernel_realme_sm8250](https://github.com/SM8250-Common/android_kernel_realme_sm8250/tree/lineage-24.0) · lineage-24.0 | 4.19.325 | b76eb6c93add8152b1aa873da0d8d7f495cccab0 | Latest inspected community tree; commit dated 2026-11-01; candidate for source comparison, not yet build-validated |
| Alternate community reference | [AOSPA/android_kernel_realme_sm8250](https://github.com/AOSPA/android_kernel_realme_sm8250/tree/uvite) · uvite | 4.19.318 | e5ca6a3e0e697e753cbefe54cf22e6819e44d3fb | Alternate SM8250 downstream tree |
| Historical community reference | [ProjectElixir-Devices/android_kernel_realme_sm8250](https://github.com/ProjectElixir-Devices/android_kernel_realme_sm8250/tree/Kraken-2.0) · Kraken-2.0 | 4.19.297 | 48f37e266a813f808fc4f7a852dacb4a4eef9ec9 | Explicitly describes X50 Pro and X50 Pro Player support; large repository (GitHub size metadata about 2,030,567 KB) |

## Device-specific trees

| Role | Repository / ref | Pinned commit | Notes |
|---|---|---|---|
| RMX2072 device tree | [IGaganpreetSingh/android_device_realme_bladerunner_48m](https://github.com/IGaganpreetSingh/android_device_realme_bladerunner_48m/tree/tiramisu-stable) · tiramisu-stable | 08afb1d784dd568fa04ca462684a350b37e2bf4a | Identifies RMX2072CN and codename bladerunner_48m; BoardConfig inherits device/realme/sm8250-common |
| Alternate RMX2072 device tree | [sreelekshman/android_device_realme_bladerunner_48m](https://github.com/sreelekshman/android_device_realme_bladerunner_48m/tree/typhoon) · typhoon | 2c524d8e94ffd741811223f307c39a177799a940 | BoardConfig targets RMX2072CN; device.mk inherits common device tree and device-specific vendor tree |
| Alternate RMX2072 device tree | [AOSPA/android_device_realme_bladerunner_48m](https://github.com/AOSPA/android_device_realme_bladerunner_48m/tree/topaz) · topaz | e0e0c05b6203403aeee3ab4d7d13b52080ac9c7a | Historical AOSPA product configuration |
| Current shared SM8250 device tree | [SM8250-Common/android_device_realme_sm8250-common](https://github.com/SM8250-Common/android_device_realme_sm8250-common/tree/lineage-24.0) · lineage-24.0 | 681bfa28e36003fddc004bfebef491234505adbc | Active shared configuration reference; not yet proven to pair with the older RMX2072 device-specific trees |

## Vendor / proprietary reference

| Role | Repository / ref | Pinned commit | Provenance and handling |
|---|---|---|---|
| RMX2072 vendor blobs reference | [sreelekshman/android_vendor_realme_bladerunner_48m](https://github.com/sreelekshman/android_vendor_realme_bladerunner_48m/tree/typhoon) · typhoon | 6f8c1c21395f3356b7182f576afe3b8e44b7b6c4 | Commit dated 2023-09-23 says blobs were updated to RMX2072_11.F.17; proprietary binary content is reference-only and is not mirrored here |

## Official Android Common Kernel / GKI reference

| Role | Repository / ref | Kernel | Pinned commit | Notes |
|---|---|---:|---|---|
| Android 17 GKI target reference | [kernel/common](https://android.googlesource.com/kernel/common/+/refs/tags/android17-6.18-2026-09_r13) · tag android17-6.18-2026-09_r13 | 6.18 | ecdaacc9a0ee87eaf9544e1836d86bd9d590312e | Official Android 17 GKI release tag dated 2026-11-05; tag object 910ab23e44c4d44c8c12a767c0d8ee9537c633f2 |

## Pinning rules

1. Use the full commit SHA from SOURCE_LOCK.json for reproducible checkouts.
2. Do not build from a moving branch name without first resolving and recording its commit.
3. Do not copy complete upstream repositories into this project. Keep upstream repositories as external sources and store only our own analysis, patches, configuration and scripts.
4. For large kernel repositories, inspect GitHub's reported repository size before cloning. Prefer one kernel checkout at a time; use a single-branch shallow clone for initial work, and use sparse checkout or partial clone for targeted source inspection where practical.
5. A pinned source is not a validated source. Build, boot and hardware-test status must be recorded separately.
6. Update the lock file only through a reviewed source refresh; retain the previous pin in Git history.

## Snapshot limitations

- GitHub's size field is approximate repository metadata, not a guaranteed download size.
- The repository metadata API reports NOASSERTION for several projects even when individual files contain SPDX or license headers. See [docs/SOURCE_LICENSE_AUDIT.md](../docs/SOURCE_LICENSE_AUDIT.md).
- The source pins identify upstream snapshots; they do not establish that the device tree, common tree, vendor blobs and kernel branch were originally built together.
