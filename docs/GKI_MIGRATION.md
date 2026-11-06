# GKI Migration Research

## Objective
Evaluate migration from the legacy Qualcomm 4.19 downstream kernel to an Android Common Kernel (ACK) GKI branch, with device-specific drivers supplied as vendor modules where the architecture permits.

## Important distinction
A kernel with loadable-module support is not automatically a GKI kernel. GKI requires the appropriate ACK source, build/configuration model, protected KMI surface, module ABI discipline, boot integration and vendor-module arrangement.

GKI also does not automatically make legacy vendor HALs compatible with a new kernel. Existing userspace components may depend on downstream kernel interfaces, device nodes, ioctls, memory allocators or firmware behavior.

## Workstreams
1. Choose a target branch using the official Android kernel compatibility matrix. Treat 6.18 as a candidate, not a prevalidated device target.
2. Audit actual GPT, boot header version, boot/vendor_boot/init_boot/dtbo/vendor_dlkm availability and AVB chain.
3. Identify required exported symbols and whether vendor modules can be built against the selected KMI.
4. Prefer upstream drivers; port downstream drivers only where needed; identify closed-source modules that cannot be rebuilt.
5. Test VINTF, HALs, firmware, SELinux, init and module load order.
6. Boot with minimal hardware first, then enable subsystems incrementally.

## Candidate architecture
- AOSP Android 17 system image
- Compatible vendor image and device firmware
- ACK/GKI kernel from a supported branch
- Device-specific DTB/DTBO and vendor modules, subject to actual boot architecture
- Existing proprietary userspace HALs where compatible

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
