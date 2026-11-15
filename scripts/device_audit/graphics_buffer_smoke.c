/* SPDX-License-Identifier: Apache-2.0 */
/* GSI-only userspace check: real allocator -> EGL image -> GLES -> CPU pixels.
 * No DRM master, modeset or storage writes. Run with a bounded host timeout.
 * Passing this does not establish SurfaceFlinger, panel output or acceleration.
 */
#include <android/hardware_buffer.h>
#include <EGL/egl.h>
#include <EGL/eglext.h>
#include <GLES2/gl2.h>
#include <GLES2/gl2ext.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

static int pixel_ok(const uint8_t *p)
{
	return abs((int)p[0] - 32) <= 1 && abs((int)p[1] - 128) <= 1 &&
	       abs((int)p[2] - 223) <= 1 && p[3] == 255;
}

int main(void)
{
	EGLDisplay display = EGL_NO_DISPLAY;
	EGLContext context = EGL_NO_CONTEXT;
	EGLSurface surface = EGL_NO_SURFACE;
	EGLImageKHR image = EGL_NO_IMAGE_KHR;
	AHardwareBuffer *buffer = NULL;
	GLuint texture = 0, fbo = 0;
	int result = 1;
	const char *stage = "egl-display";
	PFNEGLCREATEIMAGEKHRPROC create_image = NULL;
	PFNEGLDESTROYIMAGEKHRPROC destroy_image = NULL;
	setvbuf(stdout, NULL, _IONBF, 0);
	puts("GFXTEST begin=egl-display physical_display=NOT_TESTED");
	display = eglGetDisplay(EGL_DEFAULT_DISPLAY);
	EGLint major, minor;
	if (display == EGL_NO_DISPLAY || !eglInitialize(display, &major, &minor)) goto out;
	printf("GFXTEST egl=%d.%d vendor=%s\n", major, minor, eglQueryString(display, EGL_VENDOR));
	stage = "egl-context";
	const EGLint config_attrs[] = {EGL_SURFACE_TYPE, EGL_PBUFFER_BIT,
		EGL_RENDERABLE_TYPE, EGL_OPENGL_ES2_BIT, EGL_RED_SIZE, 8,
		EGL_GREEN_SIZE, 8, EGL_BLUE_SIZE, 8, EGL_ALPHA_SIZE, 8, EGL_NONE};
	const EGLint context_attrs[] = {EGL_CONTEXT_CLIENT_VERSION, 2, EGL_NONE};
	const EGLint surface_attrs[] = {EGL_WIDTH, 1, EGL_HEIGHT, 1, EGL_NONE};
	EGLConfig config;
	EGLint count;
	if (!eglBindAPI(EGL_OPENGL_ES_API) ||
	    !eglChooseConfig(display, config_attrs, &config, 1, &count) || count != 1) goto out;
	context = eglCreateContext(display, config, EGL_NO_CONTEXT, context_attrs);
	surface = eglCreatePbufferSurface(display, config, surface_attrs);
	if (context == EGL_NO_CONTEXT || surface == EGL_NO_SURFACE ||
	    !eglMakeCurrent(display, surface, surface, context)) goto out;
	printf("GFXTEST gl_vendor=%s renderer=%s version=%s\n",
	       glGetString(GL_VENDOR), glGetString(GL_RENDERER), glGetString(GL_VERSION));
	stage = "native-buffer-extensions";
	PFNEGLGETNATIVECLIENTBUFFERANDROIDPROC client_buffer =
		(PFNEGLGETNATIVECLIENTBUFFERANDROIDPROC)eglGetProcAddress("eglGetNativeClientBufferANDROID");
	create_image = (PFNEGLCREATEIMAGEKHRPROC)eglGetProcAddress("eglCreateImageKHR");
	destroy_image = (PFNEGLDESTROYIMAGEKHRPROC)eglGetProcAddress("eglDestroyImageKHR");
	PFNGLEGLIMAGETARGETTEXTURE2DOESPROC image_texture =
		(PFNGLEGLIMAGETARGETTEXTURE2DOESPROC)eglGetProcAddress("glEGLImageTargetTexture2DOES");
	if (!client_buffer || !create_image || !destroy_image || !image_texture) goto out;
	stage = "allocate-hardware-buffer";
	AHardwareBuffer_Desc desc = {.width = 64, .height = 64, .layers = 1,
		.format = AHARDWAREBUFFER_FORMAT_R8G8B8A8_UNORM,
		.usage = AHARDWAREBUFFER_USAGE_GPU_SAMPLED_IMAGE |
			 AHARDWAREBUFFER_USAGE_GPU_COLOR_OUTPUT | AHARDWAREBUFFER_USAGE_CPU_READ_RARELY};
	int status = AHardwareBuffer_allocate(&desc, &buffer);
	printf("GFXTEST allocate_status=%d\n", status);
	if (status || !buffer) goto out;
	AHardwareBuffer_describe(buffer, &desc);
	printf("GFXTEST buffer=%ux%u stride=%u format=%u\n", desc.width, desc.height, desc.stride, desc.format);
	stage = "import-egl-image";
	EGLClientBuffer client = client_buffer(buffer);
	const EGLint image_attrs[] = {EGL_IMAGE_PRESERVED_KHR, EGL_TRUE, EGL_NONE};
	if (!client) goto out;
	image = create_image(display, EGL_NO_CONTEXT, EGL_NATIVE_BUFFER_ANDROID, client, image_attrs);
	if (image == EGL_NO_IMAGE_KHR) goto out;
	stage = "render-to-hardware-buffer";
	glGenTextures(1, &texture);
	glBindTexture(GL_TEXTURE_2D, texture);
	glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST);
	glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST);
	image_texture(GL_TEXTURE_2D, image);
	if (glGetError() != GL_NO_ERROR) goto out;
	glGenFramebuffers(1, &fbo);
	glBindFramebuffer(GL_FRAMEBUFFER, fbo);
	glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, texture, 0);
	GLenum framebuffer_status = glCheckFramebufferStatus(GL_FRAMEBUFFER);
	printf("GFXTEST framebuffer_status=%#x\n", framebuffer_status);
	if (framebuffer_status != GL_FRAMEBUFFER_COMPLETE) goto out;
	glViewport(0, 0, 64, 64);
	glClearColor(0.125f, 0.5f, 0.875f, 1.0f);
	glClear(GL_COLOR_BUFFER_BIT);
	glFinish();
	uint8_t pixel[4] = {0};
	glReadPixels(0, 0, 1, 1, GL_RGBA, GL_UNSIGNED_BYTE, pixel);
	GLenum error = glGetError();
	printf("GFXTEST gl_pixel=%u,%u,%u,%u error=%#x\n", pixel[0], pixel[1], pixel[2], pixel[3], error);
	if (error != GL_NO_ERROR || !pixel_ok(pixel)) goto out;
	stage = "cpu-read-same-buffer";
	void *mapped = NULL;
	status = AHardwareBuffer_lock(buffer, AHARDWAREBUFFER_USAGE_CPU_READ_RARELY, -1, NULL, &mapped);
	printf("GFXTEST cpu_lock_status=%d\n", status);
	if (status || !mapped) goto out;
	const uint8_t *cpu_pixel = mapped;
	int matches = pixel_ok(cpu_pixel);
	printf("GFXTEST cpu_pixel=%u,%u,%u,%u matches=%d\n",
	       cpu_pixel[0], cpu_pixel[1], cpu_pixel[2], cpu_pixel[3], matches);
	status = AHardwareBuffer_unlock(buffer, NULL);
	if (status || !matches) goto out;
	puts("GFXTEST buffer_render=PASS physical_display=NOT_TESTED");
	result = 0;
out:
	if (result) printf("GFXTEST failed_stage=%s egl_error=%#x\n", stage, eglGetError());
	if (fbo) glDeleteFramebuffers(1, &fbo);
	if (texture) glDeleteTextures(1, &texture);
	if (image != EGL_NO_IMAGE_KHR && destroy_image) destroy_image(display, image);
	if (buffer) AHardwareBuffer_release(buffer);
	if (display != EGL_NO_DISPLAY) {
		eglMakeCurrent(display, EGL_NO_SURFACE, EGL_NO_SURFACE, EGL_NO_CONTEXT);
		if (surface != EGL_NO_SURFACE) eglDestroySurface(display, surface);
		if (context != EGL_NO_CONTEXT) eglDestroyContext(display, context);
		eglTerminate(display);
	}
	return result;
}
