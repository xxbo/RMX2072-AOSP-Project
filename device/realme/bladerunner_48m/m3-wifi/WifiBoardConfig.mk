# Real AOSP AIDL supplicant with the native nl80211 station path.
# SM8250 does not support SVE; inherit the project's armv8-a/generic target.
$(call soong_config_set_bool,wpa_supplicant_8,wifi_hidl_unified_supplicant_service_rc_entry,true)
# Do not link a downstream private ioctl library to the upstream ath11k driver.
# This upstream flag removes driver_cmd from the nl80211 ops. Its legacy P2P
# no-op helpers are not acceptance for P2P/NoA; those features remain untested.
$(call soong_config_set_bool,wpa_supplicant_8,wpa_supplicant_use_stub_lib,true)
