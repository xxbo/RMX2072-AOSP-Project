// SPDX-License-Identifier: Apache-2.0
// Stock control for the one-shot 6.18 temporary-key probe.
#include <android/hardware/keymaster/4.0/IKeymasterDevice.h>
#include <hidl/HidlTransportSupport.h>
#include <cstdio>

using android::hardware::hidl_vec;
using namespace android::hardware::keymaster::V4_0;

int main() {
    android::hardware::configureRpcThreadpool(1, false);
    auto device = IKeymasterDevice::tryGetService("default");
    if (!device || !device->isRemote()) return 1;

    hidl_vec<KeyParameter> params;
    params.resize(6);
    params[0].tag = Tag::ALGORITHM;
    params[0].f.algorithm = Algorithm::HMAC;
    params[1].tag = Tag::KEY_SIZE;
    params[1].f.integer = 256;
    params[2].tag = Tag::PURPOSE;
    params[2].f.purpose = KeyPurpose::SIGN;
    params[3].tag = Tag::DIGEST;
    params[3].f.digest = Digest::SHA_2_256;
    params[4].tag = Tag::MIN_MAC_LENGTH;
    params[4].f.integer = 256;
    params[5].tag = Tag::NO_AUTH_REQUIRED;
    params[5].f.boolValue = true;

    hidl_vec<uint8_t> transient;
    auto generated = device->generateKey(params, [&](ErrorCode error, const auto& blob, const auto&) {
        printf("generate status=%d blob_bytes=%zu\n", static_cast<int>(error), blob.size());
        if (error == ErrorCode::OK) transient = blob;
    });
    if (!generated.isOk() || !transient.size()) return 2;
    auto deleted = device->deleteKey(transient);
    if (!deleted.isOk()) return 3;
    auto status = static_cast<ErrorCode>(deleted);
    printf("delete status=%d\n", static_cast<int>(status));
    return status == ErrorCode::OK ? 0 : 4;
}
