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
collecting a KMS snapshot capped at 256 KiB after each successful flip. It
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
The four comparison snapshots plus the restored KMS/state/FB snapshots have
a combined cap of 1664 KiB, below the witness's 2 MiB publication limit.
Trial 62's complete KMS snapshot is 156623 bytes; a 128 KiB cap would truncate
it and invalidate the experiment.

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

## Trial 63 result

[Kernel build 32](https://github.com/xxbo/RMX2072-AOSP-Project/actions/runs/43881361097)
passed at `fc9e6e3331ebf04ba8e5083f4d5dfa539442be02`. The complete probe/boot
recipe is `226f20238a64d224f3b03a61180d5f556db99b49`. Kernel Image SHA-256 is
`9d5c632948003fd8447ea7d5c086f71b5d19f9f290aab8b236a5670c9ee8df91`;
boot SHA-256 is `8bb26c3439c046566e380482860fca0f78e798d0a7f69eb0a235a8a878614cb6`.
Handset boot: `d328f362-2da1-4cf7-bb53-49c69e04eed5`.

All three hardware phases verify SRC_FORMAT `0x4237ff` (solid-fill bit 22
set), zero source addresses/strides and 1080x2400 source/destination geometry.
Constant colors are `0xff0000ff`, `0xff00ff00`, `0xffff0000`. Each full KMS
snapshot is 153049 bytes. The single-DSC route, DSC fields and DSI packet
registers remain the same across the captured phases. The complete published
display transcript is 830092 bytes with LF endings (849036 bytes in the local
Windows CRLF copy) and is not truncated.

**Physical result: FAIL.** The operator reported: “我能看到颜色的变化，但是还是有一条一条的噪声和缺失”.
Thus corruption reproduces even with SSPP hardware pixel generation and no
framebuffer source addresses. This makes framebuffer fetching unnecessary for
this reproduction; it does not identify a particular faulty DSC/DSI/panel
component or certify all other memory/graphics paths.

The ordinary red phase uses FB 91, IOVA `0x2000`, pitch 4352 and a 10444800-byte
allocation. Its fetch bit/address/stride checks pass, but the operator did not
observe it. Record this comparison as **NOT OBSERVED**, not clean or unchanged.
The restored row pattern uses FB 92 at IOVA `0x009f8000`, pitch 4352. Probe and
parent both report parameter zero; normal fetching is restored before Android.
No final Android physical observation or additional screenshot was requested
after the operator ended the session.

DTB/DTBO, source first-stage init, GSI/vendor, guard, pattern and writable seeds
match trial 62. The runner verifies all 17 existing super segments and the old
and new boot/DTBO pairs, writing only boot. Existing acceptance checks complete
after 195.578 seconds and the guardian is retained. Android returns with enforcing,
SurfaceFlinger, composer, allocator, maintenance and authenticated ADB. Activity
and window services are still absent; neither physical output nor AOSP desktop
is accepted. No cold-start or watchdog fault injection ran.

Work stops here at the user's request. Next resume the post-fill DPU/DSC/DSI
and panel path: compare encoding geometry, packet boundaries and actual output
configuration against the selected official panel, without repeating the
already failed dual/single-DSC or framebuffer-stride guesses. Keep complete,
correct physical output as the gate before Health/Launcher work.

Evidence: [handset record](../build/device/m3-display-63-2026-11-16.json),
[bypass and cleanup checks](../build/device/m3-solid-fill-isolation-2026-11-16.json),
[host checks](../build/device/m3-solid-fill-host-checks-2026-11-16.json).
