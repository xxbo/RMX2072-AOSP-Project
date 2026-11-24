/* Submit a real Vulkan transfer and verify GPU-written bytes on the CPU.
 * No display, filesystem or frequency changes. Reject software devices.
 */
#include <vulkan/vulkan.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#define CHECK(expr) do { VkResult r_ = (expr); if (r_ != VK_SUCCESS) { \
    fprintf(stderr, "VKTEST fail=%s result=%d\n", #expr, r_); exit(1); } } while (0)

static double monotonic_seconds(void)
{
    struct timespec now;
    if (clock_gettime(CLOCK_MONOTONIC, &now)) exit(1);
    return now.tv_sec + now.tv_nsec / 1e9;
}

int main(int argc, char **argv)
{
    setvbuf(stdout, NULL, _IONBF, 0);
    unsigned load_seconds = 0;
    if (argc != 1) {
        if (argc != 3 || strcmp(argv[1], "--load-seconds") ||
            strlen(argv[2]) != 1 || argv[2][0] < '1' || argv[2][0] > '8') {
            fputs("Usage: vulkan-gpu-smoke [--load-seconds 1..8]\n", stderr);
            return 2;
        }
        load_seconds = argv[2][0] - '0';
    }
    VkApplicationInfo app = {.sType=VK_STRUCTURE_TYPE_APPLICATION_INFO,
        .pApplicationName="RMX2072 GPU transfer audit", .apiVersion=VK_API_VERSION_1_1};
    VkInstanceCreateInfo ic = {.sType=VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO,
        .pApplicationInfo=&app};
    VkInstance instance;
    CHECK(vkCreateInstance(&ic, NULL, &instance));
    uint32_t count = 0;
    CHECK(vkEnumeratePhysicalDevices(instance, &count, NULL));
    printf("VKTEST physical_device_count=%u\n", count);
    if (!count || count > 16) {
        puts("VKTEST fail=no-usable-physical-device-enumeration");
        return 2;
    }
    VkPhysicalDevice devices[16], physical = VK_NULL_HANDLE;
    CHECK(vkEnumeratePhysicalDevices(instance, &count, devices));
    for (uint32_t i=0; i<count; i++) {
        VkPhysicalDeviceProperties props;
        vkGetPhysicalDeviceProperties(devices[i], &props);
        printf("VKTEST device=%s type=%u vendor=%#x device_id=%#x api=%#x\n",
            props.deviceName, props.deviceType, props.vendorID, props.deviceID, props.apiVersion);
        if (props.deviceType == VK_PHYSICAL_DEVICE_TYPE_INTEGRATED_GPU &&
            strstr(props.deviceName, "650")) physical = devices[i];
    }
    if (!physical) { puts("VKTEST fail=no-Adreno650-hardware-device"); return 2; }
    uint32_t nq=0, qi=UINT32_MAX;
    vkGetPhysicalDeviceQueueFamilyProperties(physical, &nq, NULL);
    if (!nq || nq > 32) return 2;
    VkQueueFamilyProperties queues[32];
    vkGetPhysicalDeviceQueueFamilyProperties(physical, &nq, queues);
    for (uint32_t i=0; i<nq; i++)
        if (queues[i].queueCount && (queues[i].queueFlags & VK_QUEUE_GRAPHICS_BIT)) { qi=i; break; }
    if (qi == UINT32_MAX) return 2;
    float priority=1.0f;
    VkDeviceQueueCreateInfo qc = {.sType=VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO,
        .queueFamilyIndex=qi, .queueCount=1, .pQueuePriorities=&priority};
    VkDeviceCreateInfo dc = {.sType=VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO,
        .queueCreateInfoCount=1, .pQueueCreateInfos=&qc};
    VkDevice device;
    CHECK(vkCreateDevice(physical, &dc, NULL, &device));
    VkQueue queue;
    vkGetDeviceQueue(device, qi, 0, &queue);
    const VkDeviceSize bytes=(load_seconds ? 16 : 1)*1024*1024;
    VkBufferCreateInfo bc = {.sType=VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO,
        .size=bytes, .usage=VK_BUFFER_USAGE_TRANSFER_DST_BIT, .sharingMode=VK_SHARING_MODE_EXCLUSIVE};
    VkBuffer buffer;
    CHECK(vkCreateBuffer(device, &bc, NULL, &buffer));
    VkMemoryRequirements req;
    vkGetBufferMemoryRequirements(device, buffer, &req);
    VkPhysicalDeviceMemoryProperties mp;
    vkGetPhysicalDeviceMemoryProperties(physical, &mp);
    uint32_t mt=UINT32_MAX;
    for (uint32_t i=0; i<mp.memoryTypeCount; i++)
        if ((req.memoryTypeBits & (1U<<i)) &&
            (mp.memoryTypes[i].propertyFlags & VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT)) { mt=i; break; }
    if (mt == UINT32_MAX) return 2;
    VkMemoryAllocateInfo ma = {.sType=VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO,
        .allocationSize=req.size, .memoryTypeIndex=mt};
    VkDeviceMemory memory;
    CHECK(vkAllocateMemory(device, &ma, NULL, &memory));
    CHECK(vkBindBufferMemory(device, buffer, memory, 0));
    uint32_t *mapped;
    CHECK(vkMapMemory(device, memory, 0, VK_WHOLE_SIZE, 0, (void**)&mapped));
    memset(mapped, 0, (size_t)bytes);
    VkMappedMemoryRange range={.sType=VK_STRUCTURE_TYPE_MAPPED_MEMORY_RANGE,
        .memory=memory, .size=VK_WHOLE_SIZE};
    CHECK(vkFlushMappedMemoryRanges(device, 1, &range));
    VkCommandPoolCreateInfo pc = {.sType=VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO,
        .queueFamilyIndex=qi};
    VkCommandPool pool;
    CHECK(vkCreateCommandPool(device, &pc, NULL, &pool));
    VkCommandBufferAllocateInfo ca={.sType=VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO,
        .commandPool=pool, .level=VK_COMMAND_BUFFER_LEVEL_PRIMARY, .commandBufferCount=1};
    VkCommandBuffer cmd;
    CHECK(vkAllocateCommandBuffers(device, &ca, &cmd));
    VkCommandBufferBeginInfo begin={.sType=VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO};
    CHECK(vkBeginCommandBuffer(cmd, &begin));
    const uint32_t pattern=0xa6500090;
    const unsigned fills = load_seconds ? 32 : 1;
    VkMemoryBarrier transfer={.sType=VK_STRUCTURE_TYPE_MEMORY_BARRIER,
        .srcAccessMask=VK_ACCESS_TRANSFER_WRITE_BIT, .dstAccessMask=VK_ACCESS_TRANSFER_WRITE_BIT};
    for (unsigned n=0; n<fills; n++) {
        vkCmdFillBuffer(cmd, buffer, 0, bytes, pattern);
        if (n+1 < fills)
            vkCmdPipelineBarrier(cmd, VK_PIPELINE_STAGE_TRANSFER_BIT,
                VK_PIPELINE_STAGE_TRANSFER_BIT, 0, 1, &transfer, 0, NULL, 0, NULL);
    }
    VkMemoryBarrier barrier={.sType=VK_STRUCTURE_TYPE_MEMORY_BARRIER,
        .srcAccessMask=VK_ACCESS_TRANSFER_WRITE_BIT, .dstAccessMask=VK_ACCESS_HOST_READ_BIT};
    vkCmdPipelineBarrier(cmd, VK_PIPELINE_STAGE_TRANSFER_BIT, VK_PIPELINE_STAGE_HOST_BIT,
        0, 1, &barrier, 0, NULL, 0, NULL);
    CHECK(vkEndCommandBuffer(cmd));
    VkFenceCreateInfo fc={.sType=VK_STRUCTURE_TYPE_FENCE_CREATE_INFO};
    VkFence fence;
    CHECK(vkCreateFence(device, &fc, NULL, &fence));
    VkSubmitInfo submit={.sType=VK_STRUCTURE_TYPE_SUBMIT_INFO,
        .commandBufferCount=1, .pCommandBuffers=&cmd};
    const double started = monotonic_seconds();
    unsigned submissions = 0;
    do {
        CHECK(vkResetFences(device, 1, &fence));
        CHECK(vkQueueSubmit(queue, 1, &submit, fence));
        CHECK(vkWaitForFences(device, 1, &fence, VK_TRUE, 5000000000ULL));
        submissions++;
    } while (load_seconds && monotonic_seconds()-started < load_seconds);
    CHECK(vkInvalidateMappedMemoryRanges(device, 1, &range));
    for (size_t i=0; i<bytes/4; i++)
        if (mapped[i] != pattern) { printf("VKTEST fail=readback word=%zu value=%#x\n", i, mapped[i]); return 1; }
    printf("VKTEST PASS hardware-submit-fence-readback bytes=%llu submissions=%u fills_per_submit=%u elapsed=%.3f; frame-rate NOT TESTED\n",
        (unsigned long long)bytes, submissions, fills, monotonic_seconds()-started);
    vkDestroyFence(device, fence, NULL);
    vkDestroyCommandPool(device, pool, NULL);
    vkUnmapMemory(device, memory);
    vkDestroyBuffer(device, buffer, NULL);
    vkFreeMemory(device, memory, NULL);
    vkDestroyDevice(device, NULL);
    vkDestroyInstance(instance, NULL);
    return 0;
}
