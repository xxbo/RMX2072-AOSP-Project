# M3: isolate the dual-DSC merge path

Goal: correct physical output from the 6.18 kernel and Android 17 GSI, then
continue toward the AOSP desktop. This is a display experiment, not a cold-boot
qualification. Trial 61 reproduced corruption before Android; its physical
output did not pass.

## Source and hardware comparison, 2026-11-16

The [official 20607 panel timing](https://github.com/realme-kernel-opensource/realmeX50Pro-5GPlay_AndroidQ-kernel-source/blob/24a15224fbae8ab0e8ba29a9046c06ee7a9f53a4/arch/arm64/boot/dts/20607/dsi-panel-rm19795samsung-ams641rw01_1080_2340.dtsi#L600)
lists `<1 1 1>, <2 2 1>`, selecting index 1. The three values describe layer
mixers, DSC encoders and interfaces. Both entries retain the same 1080x2400,
540x48 slices and two slices per packet. Listing a topology is source evidence
for an isolation experiment, not proof of a working 6.18 implementation.

Trial 61's native FB 91 maps at MDP IOVA `0x2000`; SSPP0 SRC0_ADDR is also
`0x2000`. Its returned pitch and SSPP stride both equal 4352. This narrows the
address/stride question but does not prove the fetched pixel bytes are correct.
CTL0 enables DSC0+1 and INTF1. PP0+1 DSC mode and byte swaps agree with the pinned
downstream setup. INTF1's mux is at offset `0x25c`, with low bits selecting PP0;
offset `0xb0` is not that mux. Generic merge-3D is not enabled in CTL0.

The DSI stream word count is 1081 (1080 payload bytes plus DCS command), total
width is 360 compressed pixel clocks, and chunk size is 540. These agree with
the downstream two-slice packet calculation. Repeating the PPS or packet-count
changes from trials 55/59 would not establish a new test.

Comparison implementation: [pinned downstream encoder](https://github.com/SM8250-Common/android_kernel_realme_sm8250/blob/b76eb6c93add8152b1aa873da0d8d7f495cccab0/techpack/display/msm/sde/sde_encoder.c)
and [DSI controller](https://github.com/SM8250-Common/android_kernel_realme_sm8250/blob/b76eb6c93add8152b1aa873da0d8d7f495cccab0/techpack/display/msm/dsi/dsi_ctrl_hw_cmn.c).
This community implementation is a code comparison, not a captured F.20 trace.

## Candidate for trial 62

An opt-in read-only boot parameter, `msm.rmx2072_single_dsc=1`, selects one
encoder for this SM8250, single-DSI, 1080x2400, two 540x48-slice configuration.
Without it, upstream topology selection is unchanged. The existing CRTC
resource calculation selects one layer mixer for one DSC. One encoder handles
both soft slices; the dual-encoder split/multiplex path is no longer used.

The patch also extends the existing runtime-PM-owned native KMS snapshot with
the four input mux words at DPU offsets `0x81800..0x8180c`. The previous DSC
bank length of `0x140` did not cover those words. It adds no hardware writes
for this capture and no per-frame logging. Generic merge-3D bank readback is
still absent; CTL enable state must not be described as that readback.

Keep the source panel, PPS, DSI packet settings, source DTB/DTBO, GSI, vendor
graphics, pattern and writable volume seeds unchanged. The kernel change and
boot parameter are recorded separately. Only boot components need updating.
The packer rejects the experiment unless the kernel patch digest is verified.

Acceptance and interpretation:

- Verify CTL0 selects only DSC0, the active input mux selects PP0, and DSC
  split/multiplex common mode is zero. Unused banks can retain old values.
- Verify PPS fields and DSI packet settings still match trial 61. A mismatch
  makes the isolation invalid until explained.
- Compare the native and Android physical image. A correct single-DSC image
  implicates the split/merge configuration or its resource-dependent behavior;
  it does not by itself identify one faulty register.
- If corruption remains, record the changed or unchanged pattern and continue
  with the common fetch, encoded stream and panel path. Do not call this fixed.
- Retain usable GSI ADB; restore F.20 on a failed startup. No unplug/power-key
  or watchdog fault-injection test is part of this experiment.

Status at recipe commit: prepared for build; no trial 62 device result yet.
