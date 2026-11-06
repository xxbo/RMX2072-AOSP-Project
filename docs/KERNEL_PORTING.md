# Kernel Porting Strategy

## Starting point
Use the official RMX2072 Android Q 4.19 source as the device-specific baseline. Compare it with the later shared Realme Android S 4.19 tree and community SM8250 kernel. Do not assume the shared tree is a drop-in replacement until its device configuration and history are checked.

## Staged approach
1. Reproduce the stock/community kernel build before modifying it.
2. Diff source trees by subsystem and identify Realme/OPlus downstream changes.
3. Map each driver to upstream Linux, Android Common Kernel or vendor-only implementations.
4. Record dependencies on private headers, exported symbols, firmware, device-tree bindings and userspace ioctls.
5. Port a small, independently testable subsystem at a time.
6. Build, boot and hardware-test each increment with a known-good rollback image.

## Driver migration inventory

| Area | Main investigation | Risk |
| --- | --- | --- |
| Display | DRM/MDSS, DSI, panel, backlight, DSC | High |
| GPU | KGSL or upstream DRM path; userspace driver compatibility | Very high |
| Camera | sensors, CSIPHY/CSID, ISP interfaces | Very high |
| Memory | ION dependencies, DMA-BUF heaps, secure heaps | Very high |
| WLAN | CNSS and WLAN driver/firmware interface | High |
| Audio | ASoC, DSP, codec and vendor userspace interface | High |
| Touch/input | controller driver, firmware loading, gestures | Medium |
| Storage | UFS, PHY, regulators and device tree | Medium |
| Power/thermal | cpufreq, devfreq, thermal zones, charger | High |
| Sensors/NFC | bus drivers, firmware and HAL expectations | Medium/High |

## Rules
- Prefer upstream drivers where they cover the exact hardware.
- Treat vendor kernel modules and proprietary userspace libraries as separate compatibility surfaces.
- Compiling a driver does not prove runtime correctness.
- Track required symbols and module dependencies.
- Keep stock boot/vendor images and a tested recovery route available.
