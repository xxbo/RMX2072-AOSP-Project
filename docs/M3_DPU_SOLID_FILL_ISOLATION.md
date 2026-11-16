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

The planned native probe will display red, green and blue for eight seconds
each, collecting a bounded KMS snapshot after each successful flip. It will
then clear the parameter, restore the row pattern and verify its normal
scanout. Its parent must also clear the parameter after timeout or failure,
before Android starts. Packaging must require a matching verified patch.

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

Current status: kernel-side probe prepared; userspace lifecycle and handset
validation remain pending. No cold-start or watchdog fault injection is part
of this display experiment.
