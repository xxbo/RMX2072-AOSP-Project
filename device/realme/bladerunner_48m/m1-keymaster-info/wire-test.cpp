// SPDX-License-Identifier: Apache-2.0
#include "wire.h"
#include <cassert>
#include <cstdio>
int main() {
    using namespace rmxkm;
    uint8_t nonce[12]{};
    Packet begin(24,0x10f);
    uint8_t keyblob[455]{};
    assert(begin.blob(8,keyblob,sizeof(keyblob)));
    assert(begin.params(16,{{0x10000004,32},{0x900003e9,0,nonce,12}}));
    assert(u32(begin.bytes.data()+16)==479);
    assert(u32(begin.bytes.data()+479+12+4)==24); // relative to params, not 503
    assert(begin.bytes.size()==515);
    Packet overflow(12,0x108);
    assert(!overflow.params(4,std::vector<Parameter>(65)));
    Packet badTag(12,0x108); assert(!badTag.params(4,{{0,0}}));
    Packet badBool(12,0x108); assert(!badBool.params(4,{{0x700001f7,0}}));
    Packet huge(12,0x108); assert(!huge.blob(4,nonce,SIZE_MAX));

    Packet response(64,0); const uint8_t* data; size_t n;
    response.put32(8,20); response.put32(12,44);
    assert(output(response.bytes.data(),64,20,data,n) && n==44);
    response.put32(12,45); assert(!output(response.bytes.data(),64,20,data,n));
    response.put32(8,0xffffffff); response.put32(12,1);
    assert(!output(response.bytes.data(),64,20,data,n));
    response.put32(8,4); assert(!output(response.bytes.data(),64,20,data,n));

    Packet b(455,0); b.put64(0,0x4b4d4b44ULL); b.put64(8,0x400000001ULL);
    b.put32(0x18,13);
    constexpr size_t t=0x1c;
    b.put32(t,0); b.put32(t+4,1); b.put32(t+0x14,2);
    b.put32(t+0x22,32); b.put32(t+0x36,1);
    b.put32(t+0x5e,1); b.put32(t+0x7e,1);
    b.bytes[t+0x18]=1; b.put32(t+0x19,32);
    b.bytes[t+0x1d]=1; b.put32(t+0x1e,256);
    b.bytes[t+0x83]=1; b.put32(t+0x84,128);
    b.bytes[t+0xd3]=1;
    b.bytes[t+0xe0]=1; b.put32(t+0xe1,2);
    b.bytes[t+0xe6]=1; b.put32(t+0xe7,170000);
    b.bytes[t+0xeb]=1; b.put32(t+0xec,202609);
    b.put32(0x13f,1); b.put32(0x13f+6,19700101); b.bytes[0x13f+10]=1;
    std::vector<Scalar> hw,sw;
    assert(characteristics(b.bytes.data(),b.bytes.size(),hw,sw));
    assert(hw.size()==13 && sw.empty());
    assert(hw[4].tag==0x10000002 && hw[4].value==32);
    assert(hw.back().tag==0x10000130 && hw.back().value==1);
    for(size_t size=0;size<0x18b;++size) assert(!characteristics(b.bytes.data(),size,hw,sw));
    b.put32(0x18,14); assert(!characteristics(b.bytes.data(),b.bytes.size(),hw,sw));
    b.put32(0x18,13); b.put32(t+0x14,0xffffffff);
    assert(!characteristics(b.bytes.data(),b.bytes.size(),hw,sw));
    puts("PASS: relative indirect offsets, bounded requests/replies, authorization metadata and truncation rejection");
}
