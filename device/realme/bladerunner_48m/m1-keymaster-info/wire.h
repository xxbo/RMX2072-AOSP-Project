// SPDX-License-Identifier: Apache-2.0
// Bounded codec for the measured RMX2072 F.20 legacy Keymaster protocol.
// Evidence and scope: docs/M3_KEYMASTER_OPERATIONS_2026-11-22.md.
#pragma once
#include <algorithm>
#include <cstdint>
#include <cstring>
#include <vector>

namespace rmxkm {
constexpr size_t capacity = 40960, maxRequest = 16384, maxParams = 64;
inline void wipe(void* p, size_t n) {
    auto* b = static_cast<volatile uint8_t*>(p);
    while (n--) *b++ = 0;
}
inline uint32_t u32(const uint8_t* p) {
    return uint32_t(p[0]) | uint32_t(p[1]) << 8 | uint32_t(p[2]) << 16 | uint32_t(p[3]) << 24;
}
inline uint64_t u64(const uint8_t* p) { return u32(p) | uint64_t(u32(p + 4)) << 32; }
struct Parameter { uint32_t tag; uint64_t value; const uint8_t* data = nullptr; size_t size = 0; };
struct Scalar { uint32_t tag; uint64_t value; };

class Packet {
public:
    std::vector<uint8_t> bytes;
    bool valid = true;
    explicit Packet(size_t header, uint32_t method) {
        bytes.reserve(capacity); bytes.resize(header); put32(0, method);
    }
    Packet(const Packet&) = delete;
    Packet& operator=(const Packet&) = delete;
    ~Packet() { wipe(bytes.data(), bytes.size()); }
    void put32(size_t at, uint32_t n) {
        if (at > bytes.size() || bytes.size() - at < 4) { valid = false; return; }
        for (unsigned i = 0; i < 4; ++i) bytes[at+i] = n >> (i*8);
    }
    void put64(size_t at, uint64_t n) { put32(at, n); put32(at+4, n >> 32); }
    bool append(const uint8_t* data, size_t n) {
        if ((!data && n) || bytes.size() > maxRequest || n > maxRequest-bytes.size())
            return valid = false;
        if (n) bytes.insert(bytes.end(), data, data+n);
        return valid;
    }
    bool blob(size_t pair, const uint8_t* data, size_t n) {
        put32(pair, n ? bytes.size() : 0); put32(pair+4, n);
        return append(data, n);
    }
    bool params(size_t pair, const std::vector<Parameter>& p) {
        if (p.size() > maxParams || bytes.size()+p.size()*12 > maxRequest)
            return valid = false;
        size_t start = bytes.size();
        put32(pair, p.empty() ? 0 : start); put32(pair+4, p.size());
        bytes.resize(start + p.size()*12);
        for (size_t i = 0; i < p.size(); ++i) {
            const auto& v = p[i]; size_t at = start+i*12;
            put32(at, v.tag);
            switch (v.tag >> 28) {
            case 1: case 2: case 3: case 4: put32(at+4, v.value); break;
            case 5: case 6: case 10: put64(at+4, v.value); break;
            case 7:
                if (v.value != 1) return valid = false;
                put32(at+4, 1); break;
            case 8: case 9:
                if (v.size > 4096) return valid = false;
                // F.20 KeymasterBuffer::get_indirect_buf_offset_from_main
                // returns table_bytes + indirect_bytes, relative to this
                // parameter block, not to the complete command header.
                put32(at+4, bytes.size()-start); put32(at+8, v.size);
                if (!append(v.data, v.size)) return false;
                break;
            default: return valid = false;
            }
        }
        return valid;
    }
};

inline bool output(const uint8_t* reply, size_t size, size_t header,
                   const uint8_t*& data, size_t& bytes) {
    data = nullptr; bytes = 0;
    if (size < header || header < 16) return false;
    uint32_t offset = u32(reply+8), n = u32(reply+12);
    if (!n) return true;
    if (offset < header || offset > size || n > size-offset) return false;
    data = reply+offset; bytes = n; return true;
}

// Authorization lists in the TA-authenticated legacy wrapped blob. Never infer
// hardware enforcement from the input request. Unknown counts/versions fail.
inline bool characteristics(const uint8_t* blob, size_t n,
                            std::vector<Scalar>& hw, std::vector<Scalar>& sw) {
    hw.clear(); sw.clear();
    if (n < 0x18b || u64(blob) != 0x4b4d4b44ULL) return false;
    uint64_t version = u64(blob+8);
    if ((version >> 32) != 4 || version < 0x400000001ULL) return false;
    uint32_t hc = u32(blob+0x18), sc = u32(blob+0x111);
    if (hc > maxParams || sc > maxParams) return false;
    const uint8_t* t = blob+0x1c;
    auto list = [&](uint32_t tag, size_t at, size_t count, size_t limit, size_t width) {
        uint32_t total = u32(t+count);
        if (total > limit) return false;
        for (uint32_t i=0; i<total; ++i)
            hw.push_back({tag, width == 8 ? u64(t+at+i*width) : u32(t+at+i*width)});
        return true;
    };
    if (!list(0x20000001, 0, 0x14, 5, 4) ||
        !list(0x20000004, 0x22, 0x36, 5, 4) ||
        !list(0x20000005, 0x3a, 0x5a, 8, 4) ||
        !list(0x20000006, 0x5e, 0x7e, 8, 4) ||
        !list(0xa00001f6, 0xa7, 0xcf, 5, 8)) return false;
    struct Field { uint32_t tag; uint16_t flag, value; uint8_t width; };
    constexpr Field tee[] = {
        {0x10000002,0x18,0x19,4}, {0x30000003,0x1d,0x1e,4},
        {0x70000007,0x82,0x82,1}, {0x30000008,0x83,0x84,4},
        {0x1000000a,0x88,0x89,4}, {0x500000c8,0x8d,0x8e,8},
        {0x700000ca,0x96,0x96,1}, {0x1000012d,0x97,0x98,4},
        {0x30000193,0x9c,0x9d,4}, {0x30000194,0xa1,0xa2,4},
        {0x700001f4,0xa6,0xa6,1}, {0x700001f7,0xd3,0xd3,1},
        {0x100001f8,0xd4,0xd5,4}, {0x300001f9,0xd9,0xda,4},
        {0x70000258,0xde,0xde,1}, {0x7000025a,0xdf,0xdf,1},
        {0x100002be,0xe0,0xe1,4}, {0x7000012f,0xe5,0xe5,1},
        {0x300002c1,0xe6,0xe7,4}, {0x300002c2,0xeb,0xec,4},
    };
    auto fields = [](const uint8_t* p, const Field* f, size_t count, std::vector<Scalar>& dest) {
        for (size_t i=0; i<count; ++i) if (p[f[i].flag]) {
            uint64_t value = f[i].width == 8 ? u64(p+f[i].value) :
                f[i].width == 4 ? u32(p+f[i].value) : 1;
            dest.push_back({f[i].tag, value});
        }
    };
    fields(t, tee, sizeof(tee)/sizeof(tee[0]), hw);
    const uint8_t* t2 = blob+0x13f;
    constexpr Field tee2[] = {
        {0x300002cf,0xf,0xb,4}, {0x300002ce,0xa,0x6,4},
        {0x700001fb,4,4,1}, {0x700001fc,5,5,1},
    };
    fields(t2, tee2, sizeof(tee2)/sizeof(tee2[0]), hw);
    hw.push_back({0x10000130, u32(t2)});
    constexpr Field software[] = {
        {0x60000190,0,1,8}, {0x60000191,9,10,8}, {0x60000192,0x12,0x13,8},
        {0x300001f5,0x1b,0x1c,4}, {0x700001fa,0x20,0x20,1},
        {0x600002bd,0x21,0x22,8},
    };
    fields(blob+0x115, software, sizeof(software)/sizeof(software[0]), sw);
    if (blob[0x158]) sw.push_back({0x700001fd,1});
    if (hw.size() != hc || sw.size() != sc) { hw.clear(); sw.clear(); return false; }
    return true;
}
} // namespace rmxkm
