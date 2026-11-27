// SPDX-License-Identifier: Apache-2.0
// RMX2072 engineering Keymaster instance backed by the resident TEE app.
#include <android/hardware/keymaster/4.0/IKeymasterDevice.h>
#include <android/log.h>
#include <hidl/HidlTransportSupport.h>
#include <hwbinder/IPCThreadState.h>
#include <cstdio>
#include <cstring>
#include <fcntl.h>
#include <unistd.h>
#include <cerrno>
#include "operations.h"

using android::hardware::hidl_vec;
using android::hardware::Return;
using namespace android::hardware::keymaster::V4_0;
#include "selftest.h"

namespace {
using Bytes = hidl_vec<uint8_t>;
using Params = hidl_vec<KeyParameter>;
constexpr auto unsupported = ErrorCode::UNIMPLEMENTED;

void clearBuffer(void* buffer, size_t size) {
    auto* bytes = static_cast<volatile uint8_t*>(buffer);
    for (size_t i = 0; i < size; ++i) bytes[i] = 0;
}

class InfoDevice final : public IKeymasterDevice {
public:
    explicit InfoDevice(const char* name) : name_(name) {}

    Return<void> getHardwareInfo(getHardwareInfo_cb cb) override {
        cb(SecurityLevel::TRUSTED_ENVIRONMENT, name_, "RMX2072 AOSP Project");
        int pid = android::hardware::IPCThreadState::self()->getCallingPid();
        char message[192];
        snprintf(message, sizeof(message), "getHardwareInfo caller=%d level=TEE name=%s",
                 pid, name_.c_str());
        __android_log_write(ANDROID_LOG_INFO, "RMXKeymaster", message);
        return {};
    }

    Return<void> getHmacSharingParameters(getHmacSharingParameters_cb cb) override {
        struct Reply {
            int32_t status;
            uint8_t seed[32];
            uint8_t nonce[32];
        } reply{};
        static_assert(sizeof(Reply) == 68);
        ErrorCode error = ErrorCode::SECURE_HW_COMMUNICATION_FAILED;
        int fd = open("/sys/firmware/rmx2072_hmac_parameters", O_RDONLY | O_CLOEXEC);
        if (fd >= 0) {
            ssize_t n = TEMP_FAILURE_RETRY(read(fd, &reply, sizeof(reply)));
            close(fd);
            if (n == sizeof(reply)) error = static_cast<ErrorCode>(reply.status);
        }
        HmacSharingParameters parameters{};
        if (error == ErrorCode::OK) {
            parameters.seed.setToExternal(reply.seed, sizeof(reply.seed));
            memcpy(parameters.nonce.data(), reply.nonce, sizeof(reply.nonce));
        }
        int caller = android::hardware::IPCThreadState::self()->getCallingPid();
        cb(error, parameters);
        char message[96];
        snprintf(message, sizeof(message), "getHmacSharingParameters caller=%d status=%d",
                 caller, static_cast<int>(error));
        __android_log_write(ANDROID_LOG_INFO, "RMXKeymaster", message);
        clearBuffer(&reply, sizeof(reply));
        clearBuffer(parameters.nonce.data(), parameters.nonce.size());
        return {};
    }
    Return<void> computeSharedHmac(const hidl_vec<HmacSharingParameters>& params,
                                   computeSharedHmac_cb cb) override {
        if (!params.size() || params.size()>16) { cb(ErrorCode::INVALID_ARGUMENT,{}); return {}; }
        rmxkm::Packet p(12,0x20f); p.put32(4,12); p.put32(8,params.size());
        for (const auto& v:params) {
            if (v.seed.size()!=32) { cb(ErrorCode::INVALID_ARGUMENT,{}); return {}; }
            p.append(v.seed.data(),32); p.append(v.nonce.data(),32);
        }
        rmxops::Reply r; auto error=rmxops::call(p,r); Bytes check;
        if (error==ErrorCode::OK) { check.resize(32); memcpy(check.data(),r.bytes.data()+4,32); }
        cb(error,check); rmxops::wipe(check); rmxops::log("computeSharedHmac",error); return {};
    }
    Return<void> verifyAuthorization(uint64_t, const Params&, const HardwareAuthToken&,
                                     verifyAuthorization_cb cb) override {
        cb(unsupported, {}); return {};
    }
    Return<ErrorCode> addRngEntropy(const Bytes&) override { return unsupported; }
    Return<void> generateKey(const Params& params, generateKey_cb cb) override {
        auto error=rmxops::supportedKey(params); Bytes blob; KeyCharacteristics c;
        if (error==ErrorCode::OK) {
            rmxkm::Packet p(12,0x108); p.params(4,rmxops::parameters(params));
            rmxops::Reply r; error=rmxops::call(p,r);
            if (error==ErrorCode::OK) error=rmxops::keyResult(r,blob,c);
        }
        cb(error,blob,c); rmxops::log("generateKey",error,blob.size()); rmxops::wipe(blob); return {};
    }
    Return<void> importKey(const Params& params, KeyFormat format, const Bytes& key, importKey_cb cb) override {
        auto error=rmxops::supportedKey(params); Bytes blob; KeyCharacteristics c;
        if (format!=KeyFormat::RAW) error=ErrorCode::UNSUPPORTED_KEY_FORMAT;
        if (error==ErrorCode::OK) {
            rmxkm::Packet p(24,0x10b); p.put32(4,uint32_t(format));
            p.params(8,rmxops::parameters(params)); p.blob(16,key.data(),key.size());
            rmxops::Reply r; error=rmxops::call(p,r);
            if (error==ErrorCode::OK) error=rmxops::keyResult(r,blob,c);
        }
        cb(error,blob,c); rmxops::log("importKey",error,blob.size()); rmxops::wipe(blob); return {};
    }
    Return<void> importWrappedKey(const Bytes&, const Bytes&, const Bytes&, const Params&,
                                  uint64_t, uint64_t, importWrappedKey_cb cb) override {
        cb(unsupported, {}, {}); return {};
    }
    Return<void> getKeyCharacteristics(const Bytes&, const Bytes&, const Bytes&,
                                       getKeyCharacteristics_cb cb) override {
        cb(unsupported, {}); return {};
    }
    Return<void> exportKey(KeyFormat, const Bytes&, const Bytes&, const Bytes&,
                           exportKey_cb cb) override { cb(unsupported, {}); return {}; }
    Return<void> attestKey(const Bytes&, const Params&, attestKey_cb cb) override {
        cb(unsupported, {}); return {};
    }
    Return<void> upgradeKey(const Bytes&, const Params&, upgradeKey_cb cb) override {
        cb(unsupported, {}); return {};
    }
    Return<ErrorCode> deleteKey(const Bytes& blob) override {
        rmxkm::Packet p(12,0x10d); p.blob(4,blob.data(),blob.size());
        rmxops::Reply r; auto error=rmxops::call(p,r); rmxops::log("deleteKey",error); return error;
    }
    Return<ErrorCode> deleteAllKeys() override { return unsupported; }
    Return<ErrorCode> destroyAttestationIds() override { return unsupported; }
    Return<void> begin(KeyPurpose purpose, const Bytes& blob, const Params& params, const HardwareAuthToken& auth,
                       begin_cb cb) override {
        if (!rmxops::noToken(auth)) { cb(unsupported,{},0); return {}; }
        rmxkm::Packet p(24,0x10f); p.put32(4,uint32_t(purpose)); p.blob(8,blob.data(),blob.size());
        p.params(16,rmxops::parameters(params)); rmxops::Reply r; auto error=rmxops::call(p,r);
        Params out; uint64_t handle=0;
        if (error==ErrorCode::OK) {
            handle=rmxkm::u64(r.bytes.data()+8);
            uint32_t n=rmxkm::u32(r.bytes.data()+36);
            if (!handle || n>16) error=ErrorCode::UNKNOWN_ERROR;
            else if (n) { out.resize(1); out[0].tag=Tag::NONCE; out[0].blob.resize(n); memcpy(out[0].blob.data(),r.bytes.data()+20,n); }
            if (error!=ErrorCode::OK && handle) { abort(handle); handle=0; }
        }
        cb(error,out,handle); rmxops::log("begin",error); return {};
    }
    Return<void> update(uint64_t handle, const Params& params, const Bytes& input, const HardwareAuthToken& auth,
                        const VerificationToken& verify, update_cb cb) override {
        if (!rmxops::noToken(auth) || !rmxops::noToken(verify)) { cb(unsupported,0,{},{}); return {}; }
        size_t n=std::min(input.size(),size_t(8192));
        rmxkm::Packet p(28,0x111); p.put64(4,handle); p.params(12,rmxops::parameters(params));
        p.blob(20,input.data(),n); rmxops::Reply r; auto error=rmxops::call(p,r);
        Bytes out; uint32_t used=0;
        if (error==ErrorCode::OK) {
            used=rmxkm::u32(r.bytes.data()+16);
            if (used>n || !rmxops::dataResult(r,20,out)) { error=ErrorCode::UNKNOWN_ERROR; used=0; abort(handle); }
        }
        cb(error,used,{},out); rmxops::log("update",error,out.size()); rmxops::wipe(out); return {};
    }
    Return<void> finish(uint64_t handle, const Params& params, const Bytes& input, const Bytes& signature,
                        const HardwareAuthToken& auth, const VerificationToken& verify, finish_cb cb) override {
        if (!rmxops::noToken(auth) || !rmxops::noToken(verify)) { abort(handle); cb(unsupported,{},{}); return {}; }
        if (input.size()>8192) { abort(handle); cb(ErrorCode::INVALID_INPUT_LENGTH,{},{}); return {}; }
        rmxkm::Packet p(36,0x112); p.put64(4,handle); p.params(12,rmxops::parameters(params));
        p.blob(20,input.data(),input.size()); p.blob(28,signature.data(),signature.size());
        rmxops::Reply r; auto error=rmxops::call(p,r); Bytes out;
        if (error==ErrorCode::OK && !rmxops::dataResult(r,16,out)) error=ErrorCode::UNKNOWN_ERROR;
        if (error!=ErrorCode::OK) abort(handle);
        cb(error,{},out); rmxops::log("finish",error,out.size()); rmxops::wipe(out); return {};
    }
    Return<ErrorCode> abort(uint64_t handle) override {
        rmxkm::Packet p(12,0x113); p.put64(4,handle); rmxops::Reply r;
        auto error=rmxops::call(p,r); rmxops::log("abort",error); return error;
    }

private:
    std::string name_;
};
}

int main() {
    constexpr char version[] = "/sys/module/rmx2072_keymaster_lookup/parameters/version_info";
    FILE* file = fopen(version, "re");
    if (!file) {
        __android_log_write(ANDROID_LOG_ERROR, "RMXKeymaster", "open version_info failed");
        return 1;
    }
    unsigned api_major, api_minor, ta_major, ta_minor;
    int fields = fscanf(file, "transport_rc=0 status=0 api=%u.%u ta=%u.%u",
                        &api_major, &api_minor, &ta_major, &ta_minor);
    fclose(file);
    if (fields != 4 || ta_major == 0) {
        __android_log_write(ANDROID_LOG_ERROR, "RMXKeymaster", "TEE version unavailable");
        return 1;
    }
    char name[80];
    snprintf(name, sizeof(name), "RMX2072 keymaster64 API %u.%u TA %u.%u",
             api_major, api_minor, ta_major, ta_minor);
    if (rmxops::configure()!=ErrorCode::OK) return 1;
    android::hardware::configureRpcThreadpool(1, true);
    android::sp<IKeymasterDevice> device = new InfoDevice(name);
    // Engineering candidate only: exercise the exact HAL methods before
    // registration, in its own enforcing domain. Framework IPC is checked
    // separately after registration. No shell access to the transport is added.
    const char* test = getenv("RMX_KEYMASTER_AES_SELFTEST");
    if (test && !strcmp(test,"1")) {
        aesTestLog("aes_selftest_begin\n");
        int result=aesSelftest(device);
        aesTestLog("aes_selftest_end result=%d\n",result);
    }
    if (device->registerAsService("default") != android::OK) {
        __android_log_write(ANDROID_LOG_ERROR, "RMXKeymaster", "registration failed");
        return 1;
    }
    __android_log_write(ANDROID_LOG_INFO, "RMXKeymaster", "registered default");
    android::hardware::joinRpcThreadpool();
    return 1;
}
