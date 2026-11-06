# Kernel Research Pipeline

## Purpose

The Kernel Source Research workflow provides a repeatable, read-only first pass over the immutable source revisions in sources/SOURCE_LOCK.json. It replaces repeated manual repository browsing with a consistent source inventory and structural path comparison.

## Workflow

- Workflow file: .github/workflows/kernel-source-research.yml
- Scanner: scripts/kernel_research/audit_sources.py
- Trigger: manual workflow_dispatch, relevant source-lock/scanner/workflow pushes, and a weekly Monday schedule
- Runner: GitHub-hosted ubuntu-latest
- Runtime: Python 3.12; standard library only
- Permissions: contents:read
- Outputs: Markdown and JSON reports uploaded as a 30-day workflow artifact

The workflow does not push commits, open pull requests, modify upstream repositories, download vendor binaries, build a kernel, or flash a device.

## Research steps

1. Read the pinned source lock.
2. Verify each GitHub kernel commit through the GitHub API.
3. Resolve the official Android Common Kernel 6.18 reference through Gitiles.
4. Enumerate selected kernel source trees: arch, drivers, techpack, include, kernel, mm, fs, net, block, sound, scripts, security, crypto, init, ipc and virt.
5. Extract Linux version fields from the top-level Makefile where available.
6. Extract build variables from build.config files and OplusKernelEnvConfig.mk.
7. Inventory ARM64 defconfigs, Qualcomm-related config names, driver subsystem directories and techpack modules.
8. Compare file paths in selected subsystems against the official RMX2072 Android Q 4.19.81 baseline.
9. Emit JSON for further analysis and Markdown for human review.

## Run manually

1. Open the repository's Actions tab.
2. Select Kernel Source Research.
3. Choose Run workflow on the main branch.
4. Wait for the Inventory and structural diff job to complete.
5. Download the kernel-source-research artifact from the completed run.

The weekly schedule runs at 03:17 UTC on Mondays. Scheduled workflows may start later depending on GitHub-hosted runner availability.

## Output interpretation

- Expected kernel version comes from the source lock; the Makefile version is independently parsed where possible.
- Commit verification confirms that the pinned commit resolves to the exact requested SHA.
- File-path additions/removals are structural indicators only. They do not prove that code behavior changed, that a driver is compatible, or that a removed path has no replacement.
- The Android Common Kernel 6.18 source is queried through Gitiles directory listings and is not yet part of the full recursive file-path comparison.
- GitHub's recursive tree API may truncate very large trees; the scanner falls back to smaller subtrees where possible.
- A failed source lookup is reported and causes a non-green job so that incomplete results are not mistaken for a successful audit.

## Next automation stages

### Stage A — Source structure and configuration

Current scope: commit verification, directory inventory, defconfig and vendor config-fragment parsing, module Makefile content diffs, and path-level comparison. Findings are recorded in docs/KERNEL_TREE_DIFF_FINDINGS.md.

### Stage B — Content-aware subsystem diffs

Add sparse, commit-pinned source retrieval for KGSL/Adreno, DRM/display, camera/ISP, DMA-BUF/ION, IPA/WLAN, thermal and power. Generate C/header content diffs and function-level change summaries. The current workflow already compares defconfig options and selected module Makefiles.

### Stage C — Reproducible build experiments

Only after the correct source/device-tree/vendor pairing is established, add a separate build workflow. Build jobs must use pinned toolchains and source SHAs, preserve logs and artifact hashes, and keep proprietary blobs and signing material outside the public repository.

### Stage D — GKI compatibility analysis

Compare the 4.19 downstream driver interfaces with the Android Common Kernel 6.18 interfaces, classify each hardware subsystem as upstream-supported, port-required, rewrite-required or vendor-dependent, and record evidence for every conclusion.

## Security and resource policy

- Use the workflow's read-only GITHUB_TOKEN permission.
- Keep upstream repositories external; do not mirror full kernel trees into this project.
- Do not store extracted vendor binaries, factory images, modem firmware, DRM assets, keys, personal device dumps or credentials in workflow artifacts.
- Keep artifact retention finite.
- Do not run full kernel builds on every push. Build workflows will be explicit and separately gated.
