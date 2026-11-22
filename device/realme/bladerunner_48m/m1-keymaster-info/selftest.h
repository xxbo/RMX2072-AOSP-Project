// SPDX-License-Identifier: Apache-2.0
// Temporary HIDL AES-GCM control. Never prints raw keys, wrapped blobs or data.
#pragma once
#include <sys/random.h>
#include <android/log.h>
#include <cstdarg>
#include <cstring>
#include <vector>
#include "wire.h"

inline void aesTestLog(const char* format, ...) {
    char message[256]; va_list args; va_start(args,format);
    vsnprintf(message,sizeof(message),format,args); va_end(args);
    fputs(message,stdout);
    __android_log_write(ANDROID_LOG_INFO,"RMXKeymasterTest",message);
}

inline int aesSelftest(const android::sp<IKeymasterDevice>& device) {
    using android::hardware::hidl_vec;
    using Bytes = hidl_vec<uint8_t>;
    using Params = hidl_vec<KeyParameter>;
    auto scalar=[](Tag tag,uint64_t value) {
        KeyParameter p{}; p.tag=tag; memcpy(&p.f,&value,8); return p;
    };
    auto emptyAuth=HardwareAuthToken{};
    auto emptyVerify=VerificationToken{};
    Params params={scalar(Tag::ALGORITHM,uint32_t(Algorithm::AES)), scalar(Tag::KEY_SIZE,256),
        scalar(Tag::PURPOSE,uint32_t(KeyPurpose::ENCRYPT)),scalar(Tag::PURPOSE,uint32_t(KeyPurpose::DECRYPT)),
        scalar(Tag::BLOCK_MODE,uint32_t(BlockMode::GCM)),scalar(Tag::PADDING,uint32_t(PaddingMode::NONE)),
        scalar(Tag::MIN_MAC_LENGTH,128),scalar(Tag::NO_AUTH_REQUIRED,1)};
    Bytes raw,blob; raw.resize(32);
    if (getrandom(raw.data(),raw.size(),0)!=ssize_t(raw.size())) {
        rmxkm::wipe(raw.data(),raw.size()); return 2;
    }
    ErrorCode status=ErrorCode::UNKNOWN_ERROR;
    auto imported=device->importKey(params,KeyFormat::RAW,raw,[&](ErrorCode e,const auto& b,const auto& c) {
        status=e; if(e==ErrorCode::OK) blob=b;
        aesTestLog("aes_import status=%d blob_bytes=%zu hw_params=%zu sw_params=%zu\n",int(e),b.size(),c.hardwareEnforced.size(),c.softwareEnforced.size());
    });
    rmxkm::wipe(raw.data(),raw.size());
    if (!imported.isOk() || status!=ErrorCode::OK || !blob.size()) return 3;
    uint64_t handle=0;
    auto cleanup=[&](int result) {
        if(handle) { device->abort(handle).isOk(); handle=0; }
        auto deleted=device->deleteKey(blob);
        bool ok=deleted.isOk() && ErrorCode(deleted)==ErrorCode::OK;
        aesTestLog("aes_delete pass=%d\n",ok);
        rmxkm::wipe(blob.data(),blob.size()); return ok ? result : 20;
    };
    Params op={scalar(Tag::BLOCK_MODE,uint32_t(BlockMode::GCM)),
        scalar(Tag::PADDING,uint32_t(PaddingMode::NONE)),scalar(Tag::MAC_LENGTH,128)};
    Bytes nonce;
    auto begun=device->begin(KeyPurpose::ENCRYPT,blob,op,emptyAuth,[&](ErrorCode e,const auto& out,uint64_t h) {
        status=e; handle=h;
        for(const auto& p:out) if(p.tag==Tag::NONCE) nonce=p.blob;
        aesTestLog("aes_encrypt_begin status=%d nonce_bytes=%zu\n",int(e),nonce.size());
    });
    if(!begun.isOk() || status!=ErrorCode::OK || nonce.size()!=12) return cleanup(4);
    Bytes plain; plain.resize(51); for(size_t i=0;i<plain.size();++i) plain[i]=uint8_t(i*7+3);
    Bytes prefix; prefix.resize(31); memcpy(prefix.data(),plain.data(),prefix.size());
    std::vector<uint8_t> encrypted;
    uint32_t used=0;
    auto updated=device->update(handle,{},prefix,emptyAuth,emptyVerify,[&](ErrorCode e,uint32_t n,const auto&,const auto& out) {
        status=e; used=n; encrypted.insert(encrypted.end(),out.begin(),out.end());
        aesTestLog("aes_update status=%d consumed=%u output=%zu\n",int(e),n,out.size());
    });
    if(!updated.isOk() || status!=ErrorCode::OK || used>prefix.size()) return cleanup(5);
    Bytes tail; tail.resize(plain.size()-used); memcpy(tail.data(),plain.data()+used,tail.size());
    auto finished=device->finish(handle,{},tail,{},emptyAuth,emptyVerify,[&](ErrorCode e,const auto&,const auto& out) {
        status=e; encrypted.insert(encrypted.end(),out.begin(),out.end());
        aesTestLog("aes_encrypt_finish status=%d output=%zu\n",int(e),out.size());
    });
    if(!finished.isOk() || status!=ErrorCode::OK) return cleanup(6);
    handle=0;
    if(encrypted.size()!=plain.size()+16) return cleanup(7);
    op.resize(4); op[3].tag=Tag::NONCE; op[3].blob=nonce;
    for(int tamper=0;tamper<2;++tamper) {
        begun=device->begin(KeyPurpose::DECRYPT,blob,op,emptyAuth,[&](ErrorCode e,const auto&,uint64_t h) { status=e; handle=h; });
        if(!begun.isOk() || status!=ErrorCode::OK) return cleanup(8);
        Bytes cipher; cipher.resize(encrypted.size()); memcpy(cipher.data(),encrypted.data(),cipher.size());
        if(tamper) cipher[cipher.size()-1]^=1;
        bool match=false; size_t outBytes=0;
        finished=device->finish(handle,{},cipher,{},emptyAuth,emptyVerify,[&](ErrorCode e,const auto&,const auto& out) {
            status=e; outBytes=out.size(); match=out.size()==plain.size() && !memcmp(out.data(),plain.data(),plain.size());
        });
        aesTestLog("aes_decrypt tampered=%d status=%d output=%zu match=%d\n",tamper,int(status),outBytes,match);
        if(!finished.isOk()) return cleanup(9);
        handle=0;
        if((!tamper && (status!=ErrorCode::OK || !match)) ||
           (tamper && (status!=ErrorCode::VERIFICATION_FAILED || outBytes))) return cleanup(10);
    }
    rmxkm::wipe(encrypted.data(),encrypted.size());
    return cleanup(0);
}
