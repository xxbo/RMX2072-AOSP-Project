# M3: distinguish transmitted PPS from panel state

Goal: correct complete physical output with project 6.18, Android 17 GSI and
ported drivers, then the AOSP desktop. Trial 63 reproduces strip noise with
verified SSPP solid fill and zero source addresses/strides. Framebuffer fetching
and Android composition are not necessary to reproduce this failure.

## Evidence gap

The prior panel message saying PPS was accepted only established that the DSI
host completed its transfer. It did not read the panel decoder. Kernel `%ph`
also prints at most 64 bytes, so the message omitted 24 bytes of the 88-byte
DSC 1.1 payload, including part of the rate-control ranges. The calculated
reference and DPU registers agreed, but a complete runtime transmit witness
and panel response were missing.

Trial 63's five native DSI snapshots show FIFO `0x11111010` (idle/empty flags,
not the lane underflow flags), ACK error zero and timeout zero. Its kernel
transcript has no DSI error-worker report. This is sampled host evidence, not
proof of an error-free stream or correct panel decoding. Packet word count
1081, chunk 540 and compressed width 360 remain consistent with the official
two-slice-per-packet configuration. Do not repeat the already failed slice
count, pitch or single/dual DSC experiments without a new distinguishing test.

## Bounded experiment

The panel driver now logs all 88 transmitted PPS bytes in three chunks of at
most 32 bytes, explicitly labelled host transfer rather than decoder acceptance.
An opt-in `panel_samsung_rm19795.readback=1` performs one diagnostic during
the first enable only. Default operation does not issue the reads.

1. Read LP DCS `0x0a`, one byte. The selected official panel's ESD check
   documents this operation and expected value `0x9c`. Otherwise stop.
2. Reuse the original `0x9f` unlock/relock pair and try 16 bytes at `0x9e`,
   the panel's PPS write address. Readability of this address is unverified.
3. Only if the returned prefix has DSC 1.1 / 8 bpc shape, request 88 bytes and
   compare them with the transmitted PPS. Always attempt the original relock.

No PPS, clocks, routing, voltage or reset timing is changed. Short reads, zero
data, timeouts and unrecognized responses are recorded as unavailable evidence.
Even a PPS-shaped response requires cautious interpretation because the read
semantics of vendor register `0x9e` are undocumented. A failure does not mean
that the decoder contains zeroes or that it rejected the write. Read diagnostics
do not turn a KMS event or host transfer into a physical pass.

The candidate retains trial 63's single-DSC route, board trees, GSI/vendor and
writable seeds. It uses the original row pattern without the prior optional
solid-fill sequence. The packer requires the verified current panel source,
so an older kernel cannot silently ignore the new boot option. Retain usable
GSI ADB, recover F.20 only if startup fails. No cold-start or watchdog fault
injection test is included.

Status: code prepared; new kernel build and handset evidence pending.
