# Project Overview

## Mission
Maintain an independent AOSP platform for the realme X50 Pro Player Edition (RMX2072 / bladerunner_48m), powered by Snapdragon 865 / SM8250. The first milestone is a reproducible Android 17 boot using the least risky compatible kernel/vendor combination. Modern GKI migration is a separate research track.

## Scope
- Device identification and stock-firmware preservation
- AOSP/GSI build and boot validation
- Device-tree and vendor compatibility
- Kernel source inventory and migration research
- Hardware validation and recovery procedures

## Milestones
1. M0 — Capture model, region, firmware, bootloader, partition map, boot metadata and AVB state.
2. M1 — Reproduce a known community build for the exact device variant.
3. M2 — Evaluate Android 17 GSI, then a device-specific AOSP product build if needed.
4. M3 — Compare official/community 4.19 trees and map upstream driver availability.
5. M4 — Prototype ACK/GKI and port only the drivers/interfaces required for boot.
6. M5 — Validate display, touch, modem, Wi-Fi, Bluetooth, audio, camera, sensors, charging, biometrics, encryption and DRM.

## Evidence labels
- Source-confirmed: visible in a named source repository or official documentation.
- Device-confirmed: captured from the actual handset.
- Build-tested: compiled successfully with recorded toolchain/configuration.
- Boot-tested: booted on physical hardware.
- Hardware-tested: a specific function was exercised and logs retained.

Do not promote claims to a stronger evidence level without reproducible evidence.
