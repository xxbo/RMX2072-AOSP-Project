// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "wire.h"
#include "../bootstrap-probes/rmx2072-keymaster-transport.h"
#include <sys/ioctl.h>
#include <sys/system_properties.h>

namespace rmxops {
using namespace android::hardware::keymaster::V4_0;
using Bytes = android::hardware::hidl_vec<uint8_t>;
using Params = android::hardware::hidl_vec<KeyParameter>;

struct Reply {
    std::vector<uint8_t> bytes;
    ~Reply() { rmxkm::wipe(bytes.data(), bytes.size()); }
};
inline std::vector<rmxkm::Parameter> parameters(const Params& in) {
    std::vector<rmxkm::Parameter> out;
    if (in.size() > rmxkm::maxParams) { out.resize(rmxkm::maxParams+1); return out; }
    for (const auto& p : in) {
        uint64_t value = 0;
        // HIDL's untagged integer union stores each enum at the same offset.
        switch (uint32_t(p.tag) >> 28) {
        case 5: case 6: case 10: memcpy(&value, &p.f, 8); break;
        case 7: value = p.f.boolValue ? 1 : 0; break;
        default: memcpy(&value, &p.f, 4); break;
        }
        out.push_back({uint32_t(p.tag), value, p.blob.data(), p.blob.size()});
    }
    return out;
}
inline void log(const char* op, ErrorCode error, size_t size=0) {
    __android_log_print(ANDROID_LOG_INFO, "RMXKeymaster", "%s status=%d bytes=%zu",
                        op, int(error), size);
}
inline ErrorCode call(rmxkm::Packet& p, Reply& reply) {
    if (!p.valid || p.bytes.size() < 4 || p.bytes.size() > rmxkm::maxRequest)
        return ErrorCode::INVALID_ARGUMENT;
    reply.bytes.resize(rmxkm::capacity-p.bytes.size());
    int fd = open("/dev/rmx2072_keymaster", O_RDWR | O_CLOEXEC);
    if (fd < 0) return ErrorCode::SECURE_HW_COMMUNICATION_FAILED;
    rmx2072_km_xfer x{0,0,uint32_t(p.bytes.size()),uint32_t(reply.bytes.size()),
        reinterpret_cast<uintptr_t>(p.bytes.data()), reinterpret_cast<uintptr_t>(reply.bytes.data())};
    // An interrupted command must not be resubmitted: its secure-world effect
    // could already have happened. The transport serializes/finishes the call.
    int rc = ioctl(fd, RMX2072_KM_CALL, &x);
    int saved = errno; close(fd);
    if (rc) {
        __android_log_print(ANDROID_LOG_ERROR,"RMXKeymaster","transport method=%u errno=%d",
                            rmxkm::u32(p.bytes.data()), saved);
        return ErrorCode::SECURE_HW_COMMUNICATION_FAILED;
    }
    return static_cast<ErrorCode>(static_cast<int32_t>(rmxkm::u32(reply.bytes.data())));
}
inline ErrorCode configure() {
    char os[PROP_VALUE_MAX]{}, patch[PROP_VALUE_MAX]{}, vendor[PROP_VALUE_MAX]{};
    __system_property_get("ro.build.version.release",os);
    __system_property_get("ro.build.version.security_patch",patch);
    __system_property_get("ro.vendor.build.security_patch",vendor);
    if (strcmp(os,"17") || strcmp(patch,"2026-09-05") || strcmp(vendor,"1970-01-01")) {
        __android_log_print(ANDROID_LOG_ERROR,"RMXKeymaster",
            "configure property mismatch release=%s system_patch=%s vendor_patch=%s",os,patch,vendor);
        return ErrorCode::INVALID_ARGUMENT;
    }
    rmxkm::Packet p(12,0x116);
    p.params(4,{{0x300002c1,170000},{0x300002c2,202609},{0x300002ce,19700101}});
    Reply r; auto error=call(p,r); log("configure",error); return error;
}
inline bool characteristics(const uint8_t* blob, size_t size, KeyCharacteristics& out) {
    std::vector<rmxkm::Scalar> hw, sw;
    if (!rmxkm::characteristics(blob,size,hw,sw)) return false;
    auto assign=[](const std::vector<rmxkm::Scalar>& a, Params& to) {
        to.resize(a.size());
        for (size_t i=0;i<a.size();++i) {
            to[i].tag=static_cast<Tag>(a[i].tag);
            memcpy(&to[i].f,&a[i].value,sizeof(a[i].value));
        }
    };
    assign(hw,out.hardwareEnforced); assign(sw,out.softwareEnforced); return true;
}
inline ErrorCode keyResult(Reply& r, Bytes& blob, KeyCharacteristics& c) {
    const uint8_t* data; size_t size;
    if (!rmxkm::output(r.bytes.data(),r.bytes.size(),16,data,size) || !size)
        return ErrorCode::UNKNOWN_ERROR;
    if (!characteristics(data,size,c)) {
        // A successful create/import may consume a secure rollback slot. If
        // its metadata cannot be decoded, delete exactly that returned blob.
        rmxkm::Packet cleanup(12,0x10d); cleanup.blob(4,data,size);
        Reply deleted; auto error=call(cleanup,deleted); log("rejectBlobCleanup",error);
        return ErrorCode::UNKNOWN_ERROR;
    }
    blob.resize(size); memcpy(blob.data(),data,size); return ErrorCode::OK;
}
inline void wipe(Bytes& b) { rmxkm::wipe(b.data(),b.size()); }
inline bool emptyMac(const Bytes& mac) {
    // KeyMint compatibility may represent an absent token with 32 zero bytes.
    return (!mac.size() || mac.size()==32) &&
        std::all_of(mac.begin(),mac.end(),[](uint8_t byte) { return byte==0; });
}
inline bool noToken(const HardwareAuthToken& t) {
    return !t.challenge && !t.userId && !t.authenticatorId && !t.timestamp &&
        !uint32_t(t.authenticatorType) && emptyMac(t.mac);
}
inline bool noToken(const VerificationToken& t) {
    return !t.challenge && !t.timestamp && !t.parametersVerified.size() && emptyMac(t.mac);
}
inline ErrorCode supportedKey(const Params& p) {
    for (const auto& v:p) if (v.tag==Tag::ALGORITHM) {
        return v.f.algorithm==Algorithm::AES || v.f.algorithm==Algorithm::HMAC ?
            ErrorCode::OK : ErrorCode::UNSUPPORTED_ALGORITHM;
    }
    return ErrorCode::INVALID_ARGUMENT;
}
inline bool dataResult(Reply& r, size_t header, Bytes& out) {
    const uint8_t* data; size_t n;
    if (!rmxkm::output(r.bytes.data(),r.bytes.size(),header,data,n)) return false;
    out.resize(n); if (n) memcpy(out.data(),data,n); return true;
}
} // namespace rmxops
