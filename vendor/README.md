# Vendor Assets Policy

This directory is reserved for vendor provenance metadata, extraction instructions and project-authored scripts.

The [project vendor source](https://github.com/xxbo/RMX2072-AOSP-Project/tree/da4385b38212ea8f84307f672a741da77172ecc5/device/realme/bladerunner_48m/m1-vendor) contains the RMX2072 fstab, device manifest, init/ueventd rules and split SELinux inputs. It is built from source for the [target GSI](../plan.md#target-system). This directory records provenance for comparison material.

## Rules

- Do not commit extracted proprietary HALs, firmware, calibration data, DRM components, modem files, factory images or other vendor binaries.
- Keep proprietary material in a local, access-controlled working directory outside this Git repository.
- Record only source URLs, source firmware build, extraction manifest revision, file paths and locally computed hashes where appropriate.
- Do not publish hashes or manifests that expose personal device identifiers.
- Before any redistribution, establish explicit rights for each component.

## Current RMX2072 reference

The pinned sreelekshman vendor-tree commit says its proprietary blobs were updated from RMX2072_11.F.17. The matching device-tree proprietary file list says RMX2072_11.F.15. Identify which version is measured if using these lists for historical comparison. Target builds use the project vendor.

The current SM8250 common-tree blob list is sourced from Realme GT Neo 3T RMX3371 and is not an RMX2072 vendor package.
