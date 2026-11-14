// SPDX-License-Identifier: Apache-2.0
#include <android/hardware/keymaster/4.0/IKeymasterDevice.h>
#include <android/log.h>
#include <hidl/HidlTransportSupport.h>
#include <cstdio>

using namespace android::hardware::keymaster::V4_0;

int main() {
    android::hardware::configureRpcThreadpool(1, false);
    auto device = IKeymasterDevice::tryGetService("default");
    if (!device || !device->isRemote()) return 1;
    bool returned = false;
    auto result = device->getHardwareInfo([&](SecurityLevel level, const auto& name,
                                               const auto& author) {
        char message[256];
        snprintf(message, sizeof(message), "getHardwareInfo reply level=%d name=%s author=%s",
                 static_cast<int>(level), name.c_str(), author.c_str());
        puts(message);
        __android_log_write(ANDROID_LOG_INFO, "RMXKeymaster", message);
        returned = true;
    });
    return result.isOk() && returned ? 0 : 1;
}
