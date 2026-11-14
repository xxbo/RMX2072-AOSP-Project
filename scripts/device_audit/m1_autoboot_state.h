/* SPDX-License-Identifier: GPL-2.0-only */
/* pmsg is binary and may contain torn records. Use the last complete marker;
 * a later damaged marker must never expose an older retained decision. */
static int autoboot_state(const char *path) {
    const char prefix[] = "RMX-M1-AUTO boot=";
    const size_t limit = 2U * 1024U * 1024U + 4096U;
    FILE *file = fopen(path, "rb");
    if (!file) {
        if (errno == ENOENT) { puts("none"); return 0; }
        perror("autoboot journal"); return 1;
    }
    char *data = malloc(limit + 1);
    if (!data) { fclose(file); return 1; }
    size_t size = fread(data, 1, limit + 1, file);
    int bad = ferror(file) || size > limit;
    fclose(file);
    if (bad) { free(data); return 1; }
    char latest[100] = "none";
    for (size_t i = 0; i + sizeof(prefix) - 1 <= size; i++) {
        if (memcmp(data + i, prefix, sizeof(prefix) - 1)) continue;
        bad = 1;
        size_t at = i + sizeof(prefix) - 1;
        if (at + 43 >= size) continue;
        int valid = 1;
        for (unsigned j = 0; j < 36; j++) {
            char c = data[at+j];
            if (j == 8 || j == 13 || j == 18 || j == 23) valid &= c == '-';
            else valid &= (c >= '0' && c <= '9') || (c >= 'a' && c <= 'f');
        }
        if (!valid || memcmp(data + at + 36, " state=", 7)) continue;
        at += 43;
        size_t end = at;
        while (end < size && end-at < 32 &&
               ((data[end] >= 'a' && data[end] <= 'z') || data[end] == '-')) end++;
        if (end == at || end == size || data[end] != '\n' || end-i >= sizeof(latest)) continue;
        memcpy(latest, data+i, end-i); latest[end-i] = 0;
        bad = 0;
    }
    free(data);
    if (bad) { fputs("damaged autoboot marker\n", stderr); return 1; }
    puts(latest);
    return 0;
}
