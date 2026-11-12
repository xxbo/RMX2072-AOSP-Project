# GKI Migration Research

## Objective
Build the pinned Android 17 ACK 6.18 kernel for RMX2072. Use upstream drivers or port the required board drivers, using modules where the boot architecture and KMI permit. Track handset acceptance in the [development plan](../plan.md).

## Important distinction
A kernel with loadable-module support is not automatically a GKI kernel. GKI requires the appropriate ACK source, build/configuration model, protected KMI surface, module ABI discipline, boot integration and vendor-module arrangement.

GKI also does not automatically make legacy vendor HALs compatible with a new kernel. Existing userspace components may depend on downstream kernel interfaces, device nodes, ioctls, memory allocators or firmware behavior.

## Workstreams
1. Pin the exact ACK 6.18 revision, configuration and toolchain used for each hardware trial.
2. Audit actual GPT, boot header version, boot/vendor_boot/init_boot/dtbo/vendor_dlkm availability and AVB chain.
3. Identify required exported symbols and whether vendor modules can be built against the selected KMI.
4. Prefer upstream drivers; port downstream drivers only where needed; identify closed-source modules that cannot be rebuilt.
5. Test VINTF, HALs, firmware, SELinux, init and module load order.
6. Boot with minimal hardware first, then enable subsystems incrementally.

## Target architecture
- Android 17 ARM64 GSI and source-built RMX2072 vendor image
- Project-built ACK 6.18 kernel, board DTB/DTBO and device modules
- Source-built Android HALs and a per-subsystem record of remaining firmware dependencies

## Key risks
- 4.19 downstream drivers may require substantial API and architecture changes.
- Qualcomm KGSL, camera/ISP, memory and secure-world paths are high-risk.
- KMI compatibility is branch-specific; moving between branches requires renewed validation and potentially module rebuilds.
- A new kernel may boot while camera, audio, biometrics, charging or modem functions remain broken.

## Official references
- [Android kernel overview](https://source.android.com/docs/core/architecture/kernel)
- [Generic Kernel Image](https://source.android.com/docs/core/architecture/kernel/generic-kernel-image)
- [Android Common Kernel source](https://android.googlesource.com/kernel/common/)
- [Android kernel release branches](https://source.android.com/docs/core/architecture/kernel/gki-release-builds)
