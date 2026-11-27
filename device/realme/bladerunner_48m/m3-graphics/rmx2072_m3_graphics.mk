PRODUCT_NAME := rmx2072_m3_graphics
PRODUCT_DEVICE := rmx2072_m3
PRODUCT_BRAND := realme
PRODUCT_MODEL := RMX2072
PRODUCT_MANUFACTURER := realme
PRODUCT_SHIPPING_API_LEVEL := 37
# CPU rendering is the first physical display integration, not Adreno support.
PRODUCT_PACKAGES := libEGL_angle libGLESv1_CM_angle libGLESv2_angle vulkan.pastel \
    android.hardware.graphics.allocator-service.minigbm mapper.minigbm gralloc.minigbm \
    android.hardware.composer.hwc3-service.rmx2072
