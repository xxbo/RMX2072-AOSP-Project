# Source License and Redistribution Audit

> Snapshot date: 2026-11-06 UTC
> This is an initial source-level audit, not legal advice or a complete file-by-file license review.

## Summary

| Source class | Evidence found | Current handling |
|---|---|---|
| Realme kernel sources | Root COPYING states GPL-2.0 WITH Linux-syscall-note; Makefiles carry SPDX identifiers; other per-file licenses may apply | Keep as external upstream sources; review file-level SPDX before copying or redistributing patches |
| Community kernel sources | Same Linux kernel COPYING text and per-file SPDX patterns; GitHub API may show NOASSERTION | Do not interpret API metadata as a complete license grant; review affected files |
| Device trees | Some files explicitly use Apache-2.0 headers; repository metadata often has no detected license | Reuse only files whose headers and provenance are understood; preserve copyright and license notices |
| Vendor repositories | Proprietary binaries and firmware; repository-level license declaration not detected | Reference/extraction metadata only; do not mirror binaries or assume redistribution permission |
| Android Common Kernel | Official source tree includes COPYING, LICENSES/ and per-file licensing | Follow upstream per-file licensing and Android kernel contribution requirements |

## Specific findings

### Official Realme kernels

- The Android Q and Android S kernel repositories both contain a root COPYING file stating:
  - SPDX-License-Identifier: GPL-2.0 WITH Linux-syscall-note
  - Linux kernel files may also be subject to other licenses.
  - File-level licensing rules are documented in Documentation/process/license-rules.rst.
- The top-level Makefile uses SPDX-License-Identifier: GPL-2.0.
- Repository API license metadata returned NOASSERTION; the actual source headers are more informative than that metadata field.
- This does not authorize copying every file without reviewing its own SPDX/header and provenance.

### Community kernel repositories

- Project Elixir, AOSPA and SM8250-Common kernel trees contain the Linux kernel COPYING text.
- Their GitHub repository metadata reports NOASSERTION.
- Treat the kernel as a collection of individually licensed files; preserve notices and check third-party/vendor subtrees before extracting or publishing code.

### Device trees

- The RMX2072 device-tree BoardConfig.mk and device.mk inspected in the IGaganpreetSingh and sreelekshman repositories contain Apache License 2.0 headers.
- The repository API does not expose a repository-level license for these trees.
- Do not assume every file in the repository has the same license; review files individually.

### Vendor blobs

- The RMX2072 vendor repository contains proprietary firmware and userspace binaries.
- No repository-level license declaration was detected.
- This project will store only source URLs, provenance, extraction instructions, file paths and locally generated hashes. Proprietary blobs themselves stay outside Git unless explicit redistribution rights are established.

### Important provenance warning

- The sreelekshman device tree's proprietary-files.txt identifies RMX2072_11.F.15 as its source firmware.
- The corresponding vendor tree commit message says its proprietary blobs were updated to RMX2072_11.F.17.
- This mismatch must be resolved before treating the tree and vendor blobs as a matched build set.

- The current SM8250-Common common-device-tree branch's proprietary-files.txt identifies Realme GT Neo 3T RMX3371_14.0.0.2100(EX01) as its source. Those entries are not an RMX2072 vendor baseline.

## Project policy

1. Do not commit extracted vendor blobs, firmware, factory images, proprietary HALs, keys or full device dumps.
2. Do not remove upstream copyright or SPDX headers from copied source.
3. Keep an origin URL and exact commit SHA for every imported patch or file.
4. Add a project-wide license only after deciding which original project-authored files are intended for redistribution.
5. Before publishing any derived kernel source, review GPL obligations and all third-party license notices.
