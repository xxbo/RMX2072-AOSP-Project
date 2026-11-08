/* SPDX-License-Identifier: GPL-2.0-only */
/* Assemble/objcopy .text; the generator supplies the real header and Image.
 * RMX2072 shared pmsg reservation: 0xb0200000..0xb0400000.
 * Write 64 records to DATA only, never its persistent-RAM header or devices.
 * x0-x3 are untouched. x9-x16 and NZCV are scratch under the boot protocol.
 */
.text
.Lwrapper_start:
    .space 64
.Lprobe:
    mov x9, #0x10
    movk x9, #0xb020, lsl #16
    adr x10, .Lwrapper_start
    mov x11, #64
    ldr x12, .Lmagic
    mrs x13, CurrentEL
    add x14, x10, #0x180, lsl #12
.Lrecord:
    stp x12, x10, [x9], #16
    stp x0, x13, [x9], #16
    stp x14, x11, [x9], #16
    stp x12, x12, [x9], #16
    subs x11, x11, #1
    b.ne .Lrecord
    /* SM8250 D-cache lines are 64 bytes; clean the touched RAM to PoC. */
    mov x15, #0
    movk x15, #0xb020, lsl #16
    mov x16, #0x1040
    movk x16, #0xb020, lsl #16
.Lclean:
    dc cvac, x15
    add x15, x15, #64
    cmp x15, x16
    b.lo .Lclean
    dsb sy
    b .Loriginal
    .p2align 3
.Lmagic:
    .ascii "RMX618E0"
    .org 0x180000
.Loriginal:
    nop
