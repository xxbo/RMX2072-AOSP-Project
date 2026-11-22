// SPDX-License-Identifier: Apache-2.0
// RMX2072 framework bring-up: complete AIDL endpoints with no available audio
// devices. The current kernel exposes no PCM nodes. Never create fake streams,
// speaker routes, microphones, clocks or effect handles to imply working audio.
#include <aidl/android/hardware/audio/core/BnConfig.h>
#include <aidl/android/hardware/audio/core/BnModule.h>
#include <aidl/android/hardware/audio/effect/BnFactory.h>
#include <android-base/logging.h>
#include <android/binder_manager.h>
#include <android/binder_process.h>

#include <atomic>
#include <cstdlib>

namespace {
namespace core = aidl::android::hardware::audio::core;
namespace effect = aidl::android::hardware::audio::effect;
namespace common = aidl::android::media::audio::common;
using ndk::ScopedAStatus;

ScopedAStatus unsupported() {
    return ScopedAStatus::fromExceptionCode(EX_UNSUPPORTED_OPERATION);
}
ScopedAStatus invalid() {
    return ScopedAStatus::fromExceptionCode(EX_ILLEGAL_ARGUMENT);
}
template <typename T> ScopedAStatus empty(std::vector<T>* out) {
    out->clear();
    return ScopedAStatus::ok();
}
template <typename T> ScopedAStatus absent(std::shared_ptr<T>* out) {
    out->reset();
    return ScopedAStatus::ok();
}

class Config final : public core::BnConfig {
  public:
    ScopedAStatus getSurroundSoundConfig(core::SurroundSoundConfig* out) override {
        *out = {};
        LOG(INFO) << "RMX Audio surround formats=0";
        return ScopedAStatus::ok();
    }
    ScopedAStatus getEngineConfig(common::AudioHalEngineConfig* out) override {
        // No CAP configuration or board overrides. The AOSP policy engine
        // supports an empty strategy list and supplies its default strategies.
        *out = {};
        LOG(INFO) << "RMX Audio engine config: default engine, no board overrides";
        return ScopedAStatus::ok();
    }
};

class Module final : public core::BnModule {
  public:
    ScopedAStatus setModuleDebug(const core::ModuleDebug&) override { return unsupported(); }
    ScopedAStatus getTelephony(std::shared_ptr<core::ITelephony>* out) override { return absent(out); }
    ScopedAStatus getBluetooth(std::shared_ptr<core::IBluetooth>* out) override { return absent(out); }
    ScopedAStatus getBluetoothA2dp(std::shared_ptr<core::IBluetoothA2dp>* out) override { return absent(out); }
    ScopedAStatus getBluetoothLe(std::shared_ptr<core::IBluetoothLe>* out) override { return absent(out); }
    ScopedAStatus getSoundDose(std::shared_ptr<core::sounddose::ISoundDose>* out) override { return absent(out); }
    ScopedAStatus getAudioPatches(std::vector<core::AudioPatch>* out) override { return empty(out); }
    ScopedAStatus getAudioPortConfigs(std::vector<common::AudioPortConfig>* out) override { return empty(out); }
    ScopedAStatus getAudioPorts(std::vector<common::AudioPort>* out) override {
        if (!reported_.exchange(true)) LOG(INFO) << "RMX Audio getAudioPorts: 0, PCM backend unavailable";
        return empty(out);
    }
    ScopedAStatus getAudioRoutes(std::vector<core::AudioRoute>* out) override { return empty(out); }
    ScopedAStatus getMicrophones(std::vector<common::MicrophoneInfo>* out) override { return empty(out); }
    ScopedAStatus getAudioPort(int32_t, common::AudioPort* out) override {
        *out = {};
        return invalid();
    }
    ScopedAStatus getAudioRoutesForAudioPort(int32_t, std::vector<core::AudioRoute>* out) override {
        out->clear();
        return invalid();
    }
    ScopedAStatus connectExternalDevice(const common::AudioPort&, common::AudioPort* out) override {
        *out = {};
        return invalid();
    }
    ScopedAStatus disconnectExternalDevice(int32_t) override { return invalid(); }
    ScopedAStatus prepareToDisconnectExternalDevice(int32_t) override { return invalid(); }
    ScopedAStatus openInputStream(const OpenInputStreamArguments&, OpenInputStreamReturn* out) override {
        *out = {};
        return invalid();
    }
    ScopedAStatus openOutputStream(const OpenOutputStreamArguments&, OpenOutputStreamReturn* out) override {
        *out = {};
        return invalid();
    }
    ScopedAStatus getSupportedPlaybackRateFactors(SupportedPlaybackRateFactors* out) override {
        *out = {};
        return unsupported();
    }
    ScopedAStatus setAudioPatch(const core::AudioPatch&, core::AudioPatch* out) override {
        *out = {};
        return invalid();
    }
    ScopedAStatus setAudioPortConfig(const common::AudioPortConfig&, common::AudioPortConfig* suggested,
                                    bool* out) override {
        *suggested = {};
        *out = false;
        return invalid();
    }
    ScopedAStatus resetAudioPatch(int32_t) override { return invalid(); }
    ScopedAStatus resetAudioPortConfig(int32_t) override { return invalid(); }
    // The contract explicitly permits UNSUPPORTED for these hardware controls;
    // do not acknowledge a mute/volume change on hardware that is not connected.
    ScopedAStatus getMasterMute(bool* out) override { *out = false; return unsupported(); }
    ScopedAStatus setMasterMute(bool) override { return unsupported(); }
    ScopedAStatus getMasterVolume(float* out) override { *out = 0; return unsupported(); }
    ScopedAStatus setMasterVolume(float) override { return unsupported(); }
    ScopedAStatus getMicMute(bool* out) override { *out = false; return unsupported(); }
    ScopedAStatus setMicMute(bool) override { return unsupported(); }
    // Notifications have no device-side work while the port list is empty.
    ScopedAStatus updateAudioMode(common::AudioMode) override { return ScopedAStatus::ok(); }
    ScopedAStatus updateScreenRotation(ScreenRotation) override { return ScopedAStatus::ok(); }
    ScopedAStatus updateScreenState(bool) override { return ScopedAStatus::ok(); }
    ScopedAStatus generateHwAvSyncId(int32_t* out) override { *out = 0; return unsupported(); }
    ScopedAStatus getVendorParameters(const std::vector<std::string>&,
                                     std::vector<core::VendorParameter>* out) override {
        out->clear();
        return unsupported();
    }
    ScopedAStatus setVendorParameters(const std::vector<core::VendorParameter>&, bool) override {
        return unsupported();
    }
    ScopedAStatus addDeviceEffect(int32_t, const std::shared_ptr<effect::IEffect>&) override { return invalid(); }
    ScopedAStatus removeDeviceEffect(int32_t, const std::shared_ptr<effect::IEffect>&) override { return invalid(); }
    ScopedAStatus getMmapPolicyInfos(common::AudioMMapPolicyType,
                                   std::vector<common::AudioMMapPolicyInfo>* out) override { return empty(out); }
    ScopedAStatus supportsVariableLatency(bool* out) override { *out = false; return ScopedAStatus::ok(); }
    ScopedAStatus getAAudioMixerBurstCount(int32_t* out) override { *out = 0; return unsupported(); }
    ScopedAStatus getAAudioHardwareBurstMinUsec(int32_t* out) override { *out = 0; return unsupported(); }
    ScopedAStatus getFlushFromFrameSupport(const common::AudioPortConfig&,
                                         common::FlushFromFrameSupport* out) override {
        *out = {};
        return unsupported();
    }

  private:
    std::atomic<bool> reported_{false};
};

class Factory final : public effect::BnFactory {
  public:
    ScopedAStatus queryEffects(const std::optional<common::AudioUuid>&,
                              const std::optional<common::AudioUuid>&,
                              const std::optional<common::AudioUuid>&,
                              std::vector<effect::Descriptor>* out) override {
        if (!reported_.exchange(true)) LOG(INFO) << "RMX Audio queryEffects: 0";
        return empty(out);
    }
    ScopedAStatus queryProcessing(const std::optional<effect::Processing::Type>&,
                                 std::vector<effect::Processing>* out) override { return empty(out); }
    ScopedAStatus createEffect(const common::AudioUuid&, std::shared_ptr<effect::IEffect>* out) override {
        out->reset();
        return invalid();
    }
    ScopedAStatus destroyEffect(const std::shared_ptr<effect::IEffect>&) override { return invalid(); }

  private:
    std::atomic<bool> reported_{false};
};

template <typename T> void registerService(const std::shared_ptr<T>& service) {
    const std::string name = std::string(T::descriptor) + "/default";
    CHECK_EQ(AServiceManager_addService(service->asBinder().get(), name.c_str()), STATUS_OK);
    LOG(INFO) << "RMX Audio registered " << name;
}
}  // namespace

int main(int argc, char** argv) {
    (void)argc;
    android::base::InitLogging(argv, android::base::LogdLogger(android::base::SYSTEM));
    ABinderProcess_setThreadPoolMaxThreadCount(4);
    auto config = ndk::SharedRefBase::make<Config>();
    auto module = ndk::SharedRefBase::make<Module>();
    auto factory = ndk::SharedRefBase::make<Factory>();
    registerService(config);
    registerService(module);
    registerService(factory);
    ABinderProcess_joinThreadPool();
    return EXIT_FAILURE;
}
