// SPDX-License-Identifier: GPL-2.0-only
// Satisfy dm-user reads from a single host-side image over the diagnostic ACM port.
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <linux/dm-user.h>
#include <poll.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <zlib.h>

#define PACKET 4096
#define MAX_BIO (4U * 1024U * 1024U)

static int receive(int fd, void *buffer, size_t size)
{
    unsigned char *p = buffer;
    while (size) {
        struct pollfd event = { .fd = fd, .events = POLLIN };
        int ready = poll(&event, 1, 8000);
        if (ready < 0 && errno == EINTR)
            continue;
        if (ready <= 0) {
            if (!ready)
                errno = ETIMEDOUT;
            return -1;
        }
        ssize_t n = read(fd, p, size);
        if (n < 0 && errno == EINTR)
            continue;
        if (n <= 0)
            return -1;
        p += n;
        size -= n;
    }
    return 0;
}

static int write_all(int fd, const void *buffer, size_t size)
{
    const unsigned char *p = buffer;
    while (size) {
        ssize_t n = write(fd, p, size);
        if (n < 0 && errno == EINTR)
            continue;
        if (n <= 0)
            return -1;
        p += n;
        size -= n;
    }
    return 0;
}

static int serve(int channel, int tty, uint64_t image_size)
{
    struct dm_user_message *msg = malloc(sizeof(*msg) + MAX_BIO);
    if (!msg)
        return -1;
    for (;;) {
        ssize_t n = read(channel, msg, sizeof(*msg));
        if (n < 0 && errno == EINTR)
            continue;
        if (n != (ssize_t)sizeof(*msg)) {
            if (n >= 0)
                errno = EPROTO;
            break;
        }
        if (msg->type == DM_USER_REQ_MAP_FLUSH && msg->len == 0) {
            msg->type = DM_USER_RESP_SUCCESS;
            if (write_all(channel, msg, sizeof(*msg)) < 0)
                break;
            continue;
        }
        if (msg->type != DM_USER_REQ_MAP_READ || !msg->len || msg->len > MAX_BIO ||
            msg->sector >= image_size / 512 || msg->len > image_size - msg->sector * 512) {
            fprintf(stderr, "unsupported operation type=%llu sector=%llu bytes=%llu\n",
                    (unsigned long long)msg->type, (unsigned long long)msg->sector,
                    (unsigned long long)msg->len);
            errno = EINVAL;
            break;
        }
        for (size_t pos = 0; pos < msg->len;) {
            size_t size = msg->len - pos < PACKET ? msg->len - pos : PACKET;
            uint64_t offset = msg->sector * 512 + pos;
            char line[96];
            int count = snprintf(line, sizeof(line), "GSI17 READ %" PRIu64 " %zu\n", offset, size);
            uint32_t checksum;
            if (write_all(tty, line, count) < 0 ||
                receive(tty, &checksum, sizeof(checksum)) < 0 ||
                receive(tty, msg->buf + pos, size) < 0)
                goto done;
            if ((uint32_t)crc32(0, msg->buf + pos, size) != checksum) {
                fprintf(stderr, "packet checksum mismatch at %" PRIu64 "\n", offset);
                errno = EBADMSG;
                goto done;
            }
            pos += size;
        }
        msg->type = DM_USER_RESP_SUCCESS;
        msg->flags = 0;
        if (write_all(channel, msg, sizeof(*msg) + msg->len) < 0)
            break;
    }
done:
    free(msg);
    return -1;
}

int main(int argc, char **argv)
{
    if (argc != 4)
        return 2;
    char *end;
    uint64_t size = strtoull(argv[3], &end, 10);
    if (!size || size % 512 || *end)
        return 2;
    int channel = open(argv[1], O_RDWR | O_CLOEXEC);
    int tty = open(argv[2], O_RDWR | O_NOCTTY | O_CLOEXEC);
    if (channel < 0 || tty < 0) {
        perror("open dm-user/ACM");
        return 1;
    }
    serve(channel, tty, size);
    perror("dm-user/ACM");
    close(channel);
    close(tty);
    return 1;
}
