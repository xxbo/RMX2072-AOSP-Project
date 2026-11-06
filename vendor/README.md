# Vendor Assets Policy

This directory is reserved for vendor provenance metadata, extraction instructions and project-authored scripts.

## Rules

- Do not commit extracted proprietary HALs, firmware, calibration data, DRM components, modem files, factory images or other vendor binaries.
- Keep proprietary material in a local, access-controlled working directory outside this Git repository.
- Record only source URLs, source firmware build, extraction manifest revision, file paths and locally computed hashes where appropriate.
- Do not publish hashes or manifests that expose personal device identifiers.
- Before any redistribution, establish explicit rights for each component.

## Current RMX2072 reference

The pinned sreelekshman vendor-tree commit says its proprietary blobs were updated from RMX2072_11.F.17. The matching device-tree proprietary file list says RMX2072_11.F.15. This discrepancy is open and must be resolved before using the blob set in a build.

The current SM8250 common-tree blob list is sourced from Realme GT Neo 3T RMX3371 and is not an RMX2072 vendor package.
