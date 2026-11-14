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

using android::hardware::hidl_vec;
using android::hardware::Return;
using namespace android::hardware::keymaster::V4_0;

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
    Return<void> computeSharedHmac(const hidl_vec<HmacSharingParameters>&,
                                   computeSharedHmac_cb cb) override {
        cb(unsupported, {}); return {};
    }
    Return<void> verifyAuthorization(uint64_t, const Params&, const HardwareAuthToken&,
                                     verifyAuthorization_cb cb) override {
        cb(unsupported, {}); return {};
    }
    Return<ErrorCode> addRngEntropy(const Bytes&) override { return unsupported; }
    Return<void> generateKey(const Params&, generateKey_cb cb) override {
        cb(unsupported, {}, {}); return {};
    }
    Return<void> importKey(const Params&, KeyFormat, const Bytes&, importKey_cb cb) override {
        cb(unsupported, {}, {}); return {};
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
    Return<ErrorCode> deleteKey(const Bytes&) override { return unsupported; }
    Return<ErrorCode> deleteAllKeys() override { return unsupported; }
    Return<ErrorCode> destroyAttestationIds() override { return unsupported; }
    Return<void> begin(KeyPurpose, const Bytes&, const Params&, const HardwareAuthToken&,
                       begin_cb cb) override { cb(unsupported, {}, 0); return {}; }
    Return<void> update(uint64_t, const Params&, const Bytes&, const HardwareAuthToken&,
                        const VerificationToken&, update_cb cb) override {
        cb(unsupported, 0, {}, {}); return {};
    }
    Return<void> finish(uint64_t, const Params&, const Bytes&, const Bytes&,
                        const HardwareAuthToken&, const VerificationToken&, finish_cb cb) override {
        cb(unsupported, {}, {}); return {};
    }
    Return<ErrorCode> abort(uint64_t) override { return unsupported; }

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
    android::hardware::configureRpcThreadpool(1, true);
    android::sp<IKeymasterDevice> device = new InfoDevice(name);
    if (device->registerAsService("default") != android::OK) {
        __android_log_write(ANDROID_LOG_ERROR, "RMXKeymaster", "registration failed");
        return 1;
    }
    __android_log_write(ANDROID_LOG_INFO, "RMXKeymaster", "registered default");
    android::hardware::joinRpcThreadpool();
    return 1;
}
