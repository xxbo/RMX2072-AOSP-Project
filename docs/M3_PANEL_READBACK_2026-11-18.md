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
solid-fill sequence. The native probe additionally reads the CCF rates/parents/
reference counts for MDP, AHB, escape and vsync clocks alongside the existing
DSI clocks, including a sample after four flips. These are software clock
diagnostics, not measurements of electrical frequency or proof of PLL lock.
No clock is written. The packer requires the verified current panel source,
so an older kernel cannot silently ignore the new boot option. Retain usable
GSI ADB, recover F.20 only if startup fails. No cold-start or watchdog fault
injection test is included.

## Factory configuration cross-check

The recorded F.20 command line selects boot DTB 12 and DTBO 17, with the
RM19795 command-mode panel. Applying these original local recovery trees in
memory confirms byte-identical 60 Hz on (375 bytes), enable (36), off (36)
and PHY timing (14) arrays against the pinned official Android Q source.
Sixteen scalar values also agree: dimensions, refresh, porches, pulse widths,
660 MHz link rate and DSC geometry/count/bit depths. The comparison includes
the original PPS packet inside the on-command array. No missing F.20 command
was found in these arrays; it does not prove that all runtime programming,
electrical timing or the ACK-generated PPS agrees with stock.

`scripts/device_audit/compare_m3_factory_panel.py` reproduces the comparison
without booting F.20 or writing the handset. It derives selectors from the
captured factory command line, verifies the pinned official source hash, and
compares only the selected normal panel's timing@0 (not the no-TE variant).
[Machine-readable result](../build/device/m3-f20-panel-source-comparison-2026-11-18.json).

The readback decoder rejects incomplete, duplicated or misordered byte chunks
and associates host traffic with the accepted boot's display gate. Six host
tests pass, including rejection of the old 64-byte truncation and missing
response bytes, plus decoding the complete vendor 88-byte DSC 1.1 payload
through the standard 128-byte parser without claiming the reserved padding
as observed bytes. The old kernel candidate is also rejected by the packer before
any output is changed. [Host checks](../build/device/m3-panel-readback-host-checks-2026-11-18.json).

Kernel build 33 at `456c663` succeeded. Selected source/distribution digests
verify (the full remote archive digest is not independently verified).
The new Image SHA-256 is `77a081f77179e9792b994700267637612da68ace83027082fc660e219bf254bb`.
Recipe `04fe0a0` produces boot `121d6b49d3e43a25dd9c9054e200daf66b616afb7de2bb7abcb52ab0ea7ce50a`.

The host execution session was interrupted during the first pre-write boot
read, after Sahara and before any program command. No candidate boot was
written. A read-only drain received the remaining stream and a terminating
Firehose ACK with rawmode=false. The runner has a narrow `--resume-prewrite`
entry for precisely this checkpoint: only the first boot-read XML may exist,
the two-event timeline, drained ACK, saved retained identity and every current
candidate metadata object must match. A separate evidence directory is used.
All recovery/candidate host hashes and complete old boot, DTBO and 17 super
reads run again before any write; no partial read is accepted. It does not
resume interrupted writes or resets. Fresh read errors use the existing F.20
recovery path. This is a host interruption, not a kernel or display result.

The first resume attempt was rejected during host candidate hashing, before
any device command: unchanged factory chunk 8 differed by one bit at byte
121272271 (`b0` instead of `b2`). Its cause is unknown; timestamps do not
establish who or what changed a byte. The corresponding recovery chunk still
matched its established SHA-256. Replacing only this current-candidate chunk
from that verified source restored its digest and the complete container digest
`d42a1d7ba3b2cbea77cb3d9f3d5715ee55e6ed31307388cdbeb6123f420e4178`.
No corrupt image was programmed. The next attempt uses the separate
`ufs-host-g3-gsi17-firststage-ufs-64-resume2` evidence directory and repeats
all host and device checks. [Interruption and repair evidence](../build/device/m3-trial64-host-interruption-2026-11-18.json).

New handset evidence is pending.
The previously installed kernel 32 has been handed off to enforcing GSI ADB
on boot `bcf5ec80-82f6-4e79-bd69-79412653e65c` and retained after 195.813 seconds.
Today's resumed physical output was not observed and is not a new display pass.
