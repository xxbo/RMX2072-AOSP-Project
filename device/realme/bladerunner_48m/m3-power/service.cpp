// SPDX-License-Identifier: Apache-2.0
// Project Power HAL capability endpoint. No performance driver is implemented
// yet: do not advertise upstream example sessions, boosts or fake measurements.
#include <aidl/android/hardware/power/BnPower.h>
#include <android-base/logging.h>
#include <android/binder_manager.h>
#include <android/binder_process.h>

#include <atomic>
#include <cstdlib>

namespace {
using namespace aidl::android::hardware::power;
using ndk::ScopedAStatus;

ScopedAStatus unsupported() {
    return ScopedAStatus::fromExceptionCode(EX_UNSUPPORTED_OPERATION);
}

class Power final : public BnPower {
  public:
    // IPower permits ignoring unsupported oneway mode/boost hints. Clients
    // querying either the legacy methods or getSupportInfo see no support.
    ScopedAStatus setMode(Mode, bool) override { return ScopedAStatus::ok(); }
    ScopedAStatus setBoost(Boost, int32_t) override { return ScopedAStatus::ok(); }
    ScopedAStatus isModeSupported(Mode, bool* out) override {
        *out = false;
        return ScopedAStatus::ok();
    }
    ScopedAStatus isBoostSupported(Boost, bool* out) override {
        *out = false;
        return ScopedAStatus::ok();
    }
    ScopedAStatus getSupportInfo(SupportInfo* out) override {
        // Value initialization retains the upstream parcelable defaults but
        // sets every capability bit/boolean to false. Nested parcels are real
        // values, so Java callers receive non-null headroom/compositionData.
        *out = SupportInfo{};
        if (!reported_.exchange(true)) {
            LOG(INFO) << "RMX Power getSupportInfo: sessions=0 modes=0 boosts=0 "
                         "composition=0 cpuHeadroom=0 gpuHeadroom=0";
        }
        return ScopedAStatus::ok();
    }
    ScopedAStatus createHintSession(int32_t, int32_t, const std::vector<int32_t>&,
                                   int64_t, std::shared_ptr<IPowerHintSession>* out) override {
        out->reset();
        return unsupported();
    }
    ScopedAStatus createHintSessionWithConfig(
            int32_t, int32_t, const std::vector<int32_t>&, int64_t, SessionTag,
            SessionConfig* config, std::shared_ptr<IPowerHintSession>* out) override {
        *config = SessionConfig{};
        out->reset();
        return unsupported();
    }
    ScopedAStatus getHintSessionPreferredRate(int64_t* out) override {
        *out = 0;
        return unsupported();
    }
    ScopedAStatus getSessionChannel(int32_t, int32_t, ChannelConfig* out) override {
        *out = ChannelConfig{};
        return unsupported();
    }
    ScopedAStatus closeSessionChannel(int32_t, int32_t) override {
        return ScopedAStatus::ok();
    }
    ScopedAStatus getCpuHeadroom(const CpuHeadroomParams&, CpuHeadroomResult* out) override {
        *out = CpuHeadroomResult{};
        return unsupported();
    }
    ScopedAStatus getGpuHeadroom(const GpuHeadroomParams&, GpuHeadroomResult* out) override {
        *out = GpuHeadroomResult{};
        return unsupported();
    }
    ScopedAStatus sendCompositionData(const std::vector<CompositionData>&) override {
        return ScopedAStatus::ok();
    }
    ScopedAStatus sendCompositionUpdate(const CompositionUpdate&) override {
        return ScopedAStatus::ok();
    }

  private:
    std::atomic<bool> reported_{false};
};
}  // namespace

int main(int argc, char** argv) {
    (void)argc;
    android::base::InitLogging(argv, android::base::LogdLogger(android::base::SYSTEM));
    ABinderProcess_setThreadPoolMaxThreadCount(0);
    auto service = ndk::SharedRefBase::make<Power>();
    const std::string instance = std::string(Power::descriptor) + "/default";
    CHECK_EQ(AServiceManager_addService(service->asBinder().get(), instance.c_str()), STATUS_OK);
    LOG(INFO) << "RMX Power registered; performance controls are not implemented";
    ABinderProcess_joinThreadPool();
    return EXIT_FAILURE;
}
