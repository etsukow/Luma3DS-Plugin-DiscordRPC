#include "3ds.h"
#include "common.h"
#include "plgldr.h"
#include "csvc.h"

#include <arpa/inet.h>
#include <errno.h>
#include <malloc.h>
#include <netinet/in.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <unistd.h>

#ifndef IP_PC_STR
#define IP_PC_STR "127.0.0.1"
#endif

#ifndef UDP_PORT_NUM
#define UDP_PORT_NUM 5005
#endif

#define SOC_ALIGN 0x1000
#define SOC_BUFFERSIZE 0x100000
#define HEARTBEAT_INTERVAL_MS 10000
#define RETRY_INTERVAL_MS 2000
#define SOC_RETRY_INTERVAL_MS 15000
#define MAX_RETRY_INTERVAL_MS 30000
#define PROTOCOL_SCHEMA_VERSION 1

static Handle thread;
static u8 stack[STACK_SIZE] __attribute__((aligned(8)));

void *__service_ptr = NULL;

// libctru service/thread objects reference these symbols during plugin linkage.
u32 __apt_appid = 0;
u32 __system_runflags = 0;
u32 __tdata_align = 8;

static void *gSocBuffer = NULL;
static bool gSocInitialized = false;
static int gUdpSocket = -1;
static struct sockaddr_in gRemoteAddr;
static bool gRemoteConfigured = false;
static bool gSocTemporarilyUnavailable = false;
static u64 gNextSocRetryMs = 0;

static void ResetUdpSocket(void)
{
    if (gUdpSocket >= 0)
    {
        close(gUdpSocket);
        gUdpSocket = -1;
    }
}

static bool ConfigureRemote(void)
{
    if (gRemoteConfigured)
        return true;

    memset(&gRemoteAddr, 0, sizeof(gRemoteAddr));
    gRemoteAddr.sin_family = AF_INET;
    gRemoteAddr.sin_port = htons(UDP_PORT_NUM);

    unsigned int a = 0;
    unsigned int b = 0;
    unsigned int c = 0;
    unsigned int d = 0;

    if (sscanf(IP_PC_STR, "%u.%u.%u.%u", &a, &b, &c, &d) != 4)
        return false;

    if (a > 255 || b > 255 || c > 255 || d > 255)
        return false;

    gRemoteAddr.sin_addr.s_addr = htonl((a << 24) | (b << 16) | (c << 8) | d);
    gRemoteConfigured = true;
    return true;
}

static bool TryInitSoc(void)
{
    if (gSocInitialized)
        return true;

    if (gSocTemporarilyUnavailable)
    {
        if (osGetTime() < gNextSocRetryMs)
            return false;
        gSocTemporarilyUnavailable = false;
    }

    if (gSocBuffer == NULL)
    {
        gSocBuffer = memalign(SOC_ALIGN, SOC_BUFFERSIZE);
        if (gSocBuffer == NULL)
            return false;
    }

    Result rc = socInit((u32 *)gSocBuffer, SOC_BUFFERSIZE);
    if (R_FAILED(rc))
    {
        gSocTemporarilyUnavailable = true;
        gNextSocRetryMs = osGetTime() + SOC_RETRY_INTERVAL_MS;
        return false;
    }

    gSocInitialized = true;
    return true;
}

static bool EnsureUdpSocket(void)
{
    if (gUdpSocket >= 0)
        return true;

    if (!ConfigureRemote())
        return false;

    if (!TryInitSoc())
        return false;

    errno = 0;
    gUdpSocket = socket(AF_INET, SOCK_DGRAM, 0);
    if (gUdpSocket < 0)
    {
        gSocTemporarilyUnavailable = true;
        gNextSocRetryMs = osGetTime() + SOC_RETRY_INTERVAL_MS;
        return false;
    }

    return true;
}

static bool TryGetCurrentTitleId(u64 *outTitleId)
{
    if (outTitleId == NULL)
        return false;

    s64 programId = 0;

    // Prefer the commonly used process-info key for ProgramID and keep one fallback.
    Result rc = svcGetProcessInfo(&programId, CUR_PROCESS_HANDLE, 0x10001);
    if (R_FAILED(rc))
        rc = svcGetProcessInfo(&programId, CUR_PROCESS_HANDLE, 0x10000);

    if (R_FAILED(rc) || programId == 0)
        return false;

    *outTitleId = (u64)programId;
    return true;
}

static bool SendRawUdp(const void *data, size_t size)
{
    if (data == NULL || size == 0)
        return false;

    if (!EnsureUdpSocket())
        return false;

    ssize_t sent = sendto(gUdpSocket, data, size, 0,
        (const struct sockaddr *)&gRemoteAddr, sizeof(gRemoteAddr));

    if (sent != (ssize_t)size)
    {
        ResetUdpSocket();
        return false;
    }

    return true;
}

static bool SendEventWithTitleId(const char *eventName)
{
    u64 titleId = 0;
    if (!TryGetCurrentTitleId(&titleId))
        return false;

    char payload[192];
    snprintf(payload, sizeof(payload),
        "{\"schemaVersion\":%d,\"event\":\"%s\",\"titleId\":\"%016llX\"}",
        PROTOCOL_SCHEMA_VERSION,
        eventName,
        (unsigned long long)titleId);

    return SendRawUdp(payload, strlen(payload));
}

static void ThreadMain(void *arg)
{
    (void)arg;

    bool startupSent = false;
    u64 retryIntervalMs = RETRY_INTERVAL_MS;
    u64 nextRetry = osGetTime();
    u64 nextHeartbeat = 0;

    while (1)
    {
        svcSleepThread(100000000);
        u64 now = osGetTime();

        if (!startupSent)
        {
            if (now >= nextRetry)
            {
                if (SendEventWithTitleId("plugin_start"))
                {
                    startupSent = true;
                    retryIntervalMs = RETRY_INTERVAL_MS;
                    nextHeartbeat = now + HEARTBEAT_INTERVAL_MS;
                }
                else
                {
                    nextRetry = now + retryIntervalMs;
                    if (retryIntervalMs < MAX_RETRY_INTERVAL_MS)
                    {
                        retryIntervalMs *= 2;
                        if (retryIntervalMs > MAX_RETRY_INTERVAL_MS)
                            retryIntervalMs = MAX_RETRY_INTERVAL_MS;
                    }
                }
            }
            continue;
        }

        if (now >= nextHeartbeat)
        {
            if (SendEventWithTitleId("heartbeat"))
            {
                nextHeartbeat = now + HEARTBEAT_INTERVAL_MS;
            }
            else
            {
                startupSent = false;
                nextRetry = now + retryIntervalMs;
            }
        }
    }
}

extern char *fake_heap_start;
extern char *fake_heap_end;
extern u32 __ctru_heap;
extern u32 __ctru_linear_heap;

u32 __ctru_heap_size = 0;
u32 __ctru_linear_heap_size = 0;

static void __system_allocateHeaps(PluginHeader *header)
{
    __ctru_heap_size = header->heapSize;
    __ctru_heap = header->heapVA;

    fake_heap_start = (char *)__ctru_heap;
    fake_heap_end = fake_heap_start + __ctru_heap_size;
}

void main(void)
{
    PluginHeader *header = (PluginHeader *)0x07000000;

    if (header->magic != HeaderMagic)
        return;

    __system_allocateHeaps(header);

    srvInit();
    plgLdrInit();

    Result createRes = svcCreateThread(&thread, ThreadMain, 0,
        (u32 *)(stack + STACK_SIZE), 30, -1);
    if (R_FAILED(createRes))
    {
        PLGLDR__DisplayErrMessage("discord-rpc", "svcCreateThread failed", (u32)createRes);
        return;
    }
    svcCloseHandle(thread);
}
