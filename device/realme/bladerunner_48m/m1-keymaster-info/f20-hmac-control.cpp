// SPDX-License-Identifier: Apache-2.0
// Exercise the GSI's first unsupported HIDL method on the original F.20 HAL.
#include <android/hardware/keymaster/4.0/IKeymasterDevice.h>
#include <hidl/HidlTransportSupport.h>
#include <cstdio>

using namespace android::hardware::keymaster::V4_0;

int main() {
    android::hardware::configureRpcThreadpool(1, false);
    auto device = IKeymasterDevice::tryGetService("default");
    if (!device || !device->isRemote()) return 1;
    bool success = false;
    auto result = device->getHmacSharingParameters(
        [&](ErrorCode error, const HmacSharingParameters&) {
            // The control only needs the return status. No parameter is logged.
            printf("getHmacSharingParameters rc=%d\n", static_cast<int>(error));
            success = error == ErrorCode::OK;
        });
    return result.isOk() && success ? 0 : 1;
}
