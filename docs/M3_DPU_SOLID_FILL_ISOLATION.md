# M3: separate pixel fetching from the compressed output path

Trial 62 reproduced unchanged corruption with one DSC and verified routing.
The next experiment asks whether corruption still occurs when SSPP generates
pixels internally instead of fetching the framebuffer. It is not a proposed
PPS, clock or framebuffer-stride fix.

The pinned ACK already has `_dpu_plane_color_fill`, called by the plane flush
path, but exposes no setter for its `color_fill` field. The diagnostic patch
adds a default-zero, root-only `msm.rmx2072_solid_fill` parameter. Normal atomic
updates copy it into full-frame SM8250 primary planes. Existing driver code
then clears source addresses, writes the constant color and sets SRC_FORMAT
bit 22. Userspace never writes MMIO addresses.

The native probe displays red, green and blue for eight seconds each,
collecting a KMS snapshot capped at 128 KiB after each successful flip. It
then clears the parameter and shows an ordinary framebuffer filled with the
same RGB red for eight seconds. Only the inactive buffer is filled, using its
returned pitch; the other buffer retains the row pattern. Finally it restores
that pattern for ten seconds. This same-color comparison helps distinguish
pixel-source effects from differences caused by image complexity.
Its parent independently clears and rereads the parameter after
success, timeout or failure, before Android starts. A failed reset blocks
handoff. Packaging requires a matching verified patch and ramdisk marker.
The complete native probe has a 75-second outer timeout in this mode; the
normal row-pattern-only mode retains its original 50-second limit.

Keep the accepted single-DSC topology, PPS, DSI packets, source trees, graphics,
GSI and volume seeds. Verify the solid-fill bit, zero source address and
expected constant color, not just the command's return code. Preserve the
native pattern and Android observations separately.

- Noise during verified hardware solid fill reproduces the symptom without
  framebuffer fetching; then prioritize the remaining DPU/DSC/DSI/panel path.
- Clean solid colors alone do not prove a fetching bug: content-dependent
  compression faults can behave differently with constant pixels.
- A failed bypass check or cleanup invalidates the isolation. Never call an
  event, screenshot or clean color alone a complete physical-display pass.

Host validation: the static ARM64 probe builds with warnings as errors. Four
tests execute the actual parent-shell block with normal, failed and timed-out
probe fixtures and an unwritable reset target. The stale-kernel packer guard
rejects this experiment without changing the existing candidate. These checks
do not establish hardware bypass or display correctness.

Current status: [kernel build 32](https://github.com/xxbo/RMX2072-AOSP-Project/actions/runs/43881361097)
is pending; handset validation has not run. No cold-start or watchdog fault
injection is part of this display experiment.
