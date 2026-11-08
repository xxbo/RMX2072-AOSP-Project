// SPDX-License-Identifier: GPL-2.0-only
// Carry bounded early-entry evidence from old pstore into current reserved RAM.
#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

#define LIMIT (2U*1024U*1024U+4096U)
static const char magic[8] = "RMX618E0";

int main(int argc, char **argv) {
    if (argc == 2 && !strcmp(argv[1], "--check")) {
        puts("RMX2072 entry carrier ready");
        return 0;
    }
    int capture = argc == 2 && !strcmp(argv[1], "--capture");
    int inspect = argc == 3 && !strcmp(argv[1], "--inspect");
    if (!capture && !inspect) return 2;
    unsigned char *data = malloc(LIMIT);
    if (!data) return 1;
    int fd = open(capture ? "/sys/fs/pstore/pmsg-ramoops-0" : argv[2], O_RDONLY|O_CLOEXEC);
    if (fd < 0) { free(data); return 3; }
    size_t size = 0;
    while (size < LIMIT) {
        ssize_t n = read(fd, data+size, LIMIT-size);
        if (n < 0 && errno == EINTR) continue;
        if (n < 0) { close(fd); free(data); return 1; }
        if (!n) break;
        size += (size_t)n;
    }
    close(fd);
    size_t count = 0, first = 0;
    uint64_t first_record[8] = {0};
    for (size_t offset = 0; offset+64 <= size; ++offset) {
        uint64_t w[8];
        if (memcmp(data+offset, magic, 8)) continue;
        memcpy(w, data+offset, sizeof(w));
        if (memcmp(data+offset+48, magic, 8) || memcmp(data+offset+56, magic, 8) ||
            (w[1]&0x1fffff) != 0x80000 || w[4] != w[1]+0x180000 ||
            (w[2]&7) || w[2] < 0x80000000ULL || w[2] >= 0x280000000ULL ||
            (w[3] != 4 && w[3] != 8) || w[5] < 1 || w[5] > 64) continue;
        if (!count) { first = offset; memcpy(first_record, w, sizeof(w)); }
        ++count;
    }
    if (!count) { puts("RMX2072-ENTRY-CARRY records=0"); free(data); return 3; }
    size_t start = first > 256 ? first-256 : 0;
    size_t bytes = size-start < 8192 ? size-start : 8192;
    if (capture) {
    fd = open("/dev/pmsg0", O_WRONLY|O_CLOEXEC);
    struct stat st;
    if (fd < 0 || fstat(fd, &st) || !S_ISCHR(st.st_mode)) {
        if (fd >= 0) close(fd);
        free(data);
        return 1;
    }
    size_t written = 0;
    while (written < bytes) {
        ssize_t n = write(fd, data+start+written, bytes-written);
        if (n < 0 && errno == EINTR) continue;
        if (n <= 0) { close(fd); free(data); return 1; }
        written += (size_t)n;
    }
    close(fd);
    }
    printf("RMX2072-ENTRY-CARRY records=%zu wrapper=0x%llx dtb=0x%llx el=%llu kernel=0x%llx\n",
           count, (unsigned long long)first_record[1], (unsigned long long)first_record[2],
           (unsigned long long)first_record[3], (unsigned long long)first_record[4]);
    free(data);
    return 0;
}
