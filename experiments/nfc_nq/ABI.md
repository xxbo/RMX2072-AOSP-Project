# NQ-NCI Userspace ABI Inventory

> Source: SM8250-Common android_kernel_realme_sm8250 commit b76eb6c93add8152b1aa873da0d8d7f495cccab0.
> Purpose: preserve the existing RMX2072 vendor NFC userspace contract while adapting the kernel implementation to ACK/GKI 6.18.

## Device interface

- Character device: /dev/nq-nci
- Device class: nqx
- Bus: I2C
- NCI framing and protocol state machine are handled in userspace; the kernel driver transports bytes and controls power/IRQ/eSE signals.
- Maximum driver read/write buffer: 558 bytes in the newer SN100-aware source.
- Read path waits for the NFC IRQ and then reads from I2C. O_NONBLOCK returns -EAGAIN when no IRQ data is ready.
- Write path sends the supplied buffer over I2C and retries up to three times.

The port must preserve the device node, ioctl command numbers, argument semantics, buffer size and interrupt/power sequencing unless the matching vendor HAL/library is deliberately replaced.

## Ioctl command inventory

The ioctl numbers below are encoded in nq-nci.h and include/uapi/linux/nfc/nfcinfo.h. Keep the magic value and command numbers unchanged.

| Command | Encoded value | Argument / result semantics in the current source |
|---|---:|---|
| NFC_SET_PWR | _IOW(0xE9, 0x01, unsigned int) | NFC power/firmware-download state request |
| ESE_SET_PWR | _IOW(0xE9, 0x02, unsigned int) | eSE power on/off/cold-reset request |
| ESE_GET_PWR | _IOR(0xE9, 0x03, unsigned int) | Returns the eSE/VEN power state through the ioctl return value |
| SET_RX_BLOCK | _IOW(0xE9, 0x04, unsigned int) | Present in the ABI; current driver switch is a no-op |
| SET_EMULATOR_TEST_POINT | _IOW(0xE9, 0x05, unsigned int) | Present in the ABI; current driver switch is a no-op |
| NFCC_GET_INFO | _IOW(0xE9, 0x09, unsigned int) | Returns the packed chip/ROM/firmware version word through the ioctl return value |
| NFCC_INITIAL_CORE_RESET_NTF | _IOW(0xE9, 0x10, unsigned int) | Returns the stored initial CORE_RESET_NTF state through the ioctl return value |

NFCC_GET_INFO is historically encoded with _IOW even though the current implementation returns the packed value directly. Do not "correct" the direction bits without checking the userspace binary; changing them changes the ioctl number.

## Power argument enums

NFC_SET_PWR currently accepts these enum nfcc_ioctl_request values:

| Value | Meaning |
|---:|---|
| 0 | NFC_POWER_OFF |
| 1 | NFC_POWER_ON |
| 2 | NFC_FW_DWL_VEN_TOGGLE |
| 3 | NFC_ISO_RESET |
| 4 | NFC_FW_DWL_HIGH |
| 5 | NFC_HARD_RESET |
| 6 | NFC_FW_DWL_LOW |
| 7 | NFC_ENABLE |
| 8 | NFC_DISABLE |

ESE_SET_PWR uses enum ese_ioctl_request:

| Value | Meaning |
|---:|---|
| 0 | ESE_POWER_ON |
| 1 | ESE_POWER_OFF |
| 2 | ESE_COLD_RESET |
| 3 | ESE_POWER_STATE |

The native ioctl path dispatches SN100_A/SN100_B to sn100_ese_pwr(). The current compat_ioctl path does not mirror that dispatch and does not handle NFCC_GET_INFO or NFCC_INITIAL_CORE_RESET_NTF. Determine whether any 32-bit NFC client is used on the target vendor build before treating 32-bit compatibility as complete.

## Packed chip information UAPI

The local copy of include/uapi/linux/nfc/nfcinfo.h preserves:

- NFCC_MAGIC = 0xE9
- NFCC_GET_INFO = _IOW(NFCC_MAGIC, 0x09, unsigned int)
- struct nqx_devinfo with four bytes: chip type, ROM version, firmware major and firmware minor
- union nqx_uinfo exposing both the packed 32-bit integer and the four-byte structure

The driver recognizes SN100_A (0xa3) and SN100_B (0xa4) and uses that detection to select SN100 eSE behavior.

## Hardware control contract

The official RMX2072 20607 DTS maps the controller to I2C address 0x28 and the following signals:

| Signal | GPIO | Role |
|---|---:|---|
| IRQ | 34 | Data-ready interrupt |
| VEN | 12 | NFC controller enable/reset |
| FIRM | 35 | Firmware-download mode |
| CLKREQ | 31 | Clock request |

The 4.19.325 implementation also recognizes optional eSE power GPIO and optional VDDIO regulator properties. The official RMX2072 DTS node inspected so far does not declare those optional properties. Preserve the optional behavior, but do not invent GPIO or regulator mappings.

## Required ABI regression checks

Before module load and functional testing:

1. Compare every ioctl constant in the port with the source header and the vendor userspace binary's expected values.
2. Confirm /dev/nq-nci ownership, mode, SELinux label and init rules.
3. Verify native 64-bit ioctl behavior; separately decide whether 32-bit compat is needed.
4. Test NFC enable/disable, firmware-download mode, cold reset, eSE power state and initial CORE_RESET_NTF handling.
5. Test read blocking, nonblocking -EAGAIN, I2C short reads/writes and retry behavior.
6. Confirm NFC discovery and card communication through the existing vendor NFC HAL.
7. Test suspend/resume and wake IRQ behavior.
