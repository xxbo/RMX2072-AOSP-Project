// SPDX-License-Identifier: GPL-2.0-only
// Query the SM8250 TLMM reset line's metadata without requesting the line.
#include <fcntl.h>
#include <inttypes.h>
#include <linux/gpio.h>
#include <stdio.h>
#include <string.h>
#include <sys/ioctl.h>
#include <unistd.h>

int main(int argc, char **argv)
{
	struct gpiochip_info chip = {0};
	struct gpio_v2_line_info line = { .offset = 180 };
	int fd;

	if (argc != 2)
		return 2;
	fd = open(argv[1], O_RDONLY | O_CLOEXEC);
	if (fd < 0) {
		perror("open gpiochip");
		return 1;
	}
	if (ioctl(fd, GPIO_GET_CHIPINFO_IOCTL, &chip) < 0) {
		perror("GPIO_GET_CHIPINFO_IOCTL");
		close(fd);
		return 1;
	}
	if (chip.lines != 181 || !strstr(chip.label, "pinctrl")) {
		fprintf(stderr, "Unexpected GPIO controller: %s (%u lines)\n", chip.label, chip.lines);
		close(fd);
		return 1;
	}
	if (ioctl(fd, GPIO_V2_GET_LINEINFO_IOCTL, &line) < 0) {
		perror("GPIO_V2_GET_LINEINFO_IOCTL");
		close(fd);
		return 1;
	}
	printf("chip=%s lines=%u offset=%u name=%s consumer=%s flags=0x%" PRIx64 "\n",
	       chip.label, chip.lines, line.offset, line.name, line.consumer, (uint64_t)line.flags);
	close(fd);
	return 0;
}
