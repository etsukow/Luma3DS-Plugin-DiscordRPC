#include "3ds.h"
#include "csvc.h"
#include "CTRPluginFramework.hpp"

#include <arpa/inet.h>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <malloc.h>
#include <netinet/in.h>
#include <string>
#include <sys/socket.h>
#include <unistd.h>
#include <vector>

#ifndef IP_PC_STR
#define IP_PC_STR "127.0.0.1"
#endif

#ifndef UDP_PORT_NUM
#define UDP_PORT_NUM 5005
#endif

extern "C"
{
    int socInit(void *contextAddr, u32 contextSize);
    void socExit(void);

    // Compatibility storage expected by older CTRPF syscalls bootstrap.
    u32 __syscalls[16] = {0};
}

namespace CTRPluginFramework
{
    namespace
    {
        static const u32 kSocBufferSize = 0x100000;

        static void *gSocBuffer = nullptr;
        static bool gSocInitialized = false;
        static int gUdpSocket = -1;
        static sockaddr_in gRemoteAddr;
        static bool gRemoteConfigured = false;

        static bool ConfigureRemote(void)
        {
            if (gRemoteConfigured)
                return true;

            std::memset(&gRemoteAddr, 0, sizeof(gRemoteAddr));
            gRemoteAddr.sin_family = AF_INET;
            gRemoteAddr.sin_port = htons(UDP_PORT_NUM);

            unsigned int a = 0;
            unsigned int b = 0;
            unsigned int c = 0;
            unsigned int d = 0;

            if (std::sscanf(IP_PC_STR, "%u.%u.%u.%u", &a, &b, &c, &d) != 4)
                return false;

            if (a > 255 || b > 255 || c > 255 || d > 255)
                return false;

            const u32 ip = (a << 24) | (b << 16) | (c << 8) | d;
            gRemoteAddr.sin_addr.s_addr = htonl(ip);

            gRemoteConfigured = true;
            return true;
        }

        static bool TryInitSoc(void)
        {
            if (gSocInitialized)
                return true;

            gSocBuffer = memalign(0x1000, kSocBufferSize);
            if (gSocBuffer == nullptr)
                return false;

            if (socInit(gSocBuffer, kSocBufferSize) != 0)
            {
                std::free(gSocBuffer);
                gSocBuffer = nullptr;
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

            gUdpSocket = socket(AF_INET, SOCK_DGRAM, 0);
            if (gUdpSocket >= 0)
                return true;

            if (!TryInitSoc())
                return false;

            gUdpSocket = socket(AF_INET, SOCK_DGRAM, 0);
            return (gUdpSocket >= 0);
        }

        static void CleanupUdp(void)
        {
            if (gUdpSocket >= 0)
            {
                close(gUdpSocket);
                gUdpSocket = -1;
            }

            if (gSocInitialized)
            {
                socExit();
                gSocInitialized = false;
            }

            if (gSocBuffer != nullptr)
            {
                std::free(gSocBuffer);
                gSocBuffer = nullptr;
            }
        }

        static std::string BuildPayload(const char *eventName)
        {
            char portBuffer[16];
            std::snprintf(portBuffer, sizeof(portBuffer), "%u", static_cast<unsigned int>(UDP_PORT_NUM));

            return std::string("{\"event\":\"") + eventName +
                "\",\"plugin\":\"discord-rpc\",\"target\":\"" +
                IP_PC_STR + ":" + portBuffer + "\"}";
        }

        static bool SendUdpPayload(const std::string &payload)
        {
            if (!EnsureUdpSocket())
                return false;

            ssize_t sent = sendto(gUdpSocket, payload.c_str(), payload.size(), 0,
                reinterpret_cast<const sockaddr *>(&gRemoteAddr), sizeof(gRemoteAddr));
            return (sent == static_cast<ssize_t>(payload.size()));
        }

        static void SendManualPing(MenuEntry *entry)
        {
            (void)entry;

            const bool ok = SendUdpPayload(BuildPayload("manual_ping"));
            OSD::Notify(ok ? "UDP ping envoye" : "UDP ping echec");
        }
    }

    // This patch the NFC disabling the touchscreen when scanning an amiibo, which prevents ctrpf to be used
    static void    ToggleTouchscreenForceOn(void)
    {
        static u32 original = 0;
        static u32 *patchAddress = nullptr;

        if (patchAddress && original)
        {
            *patchAddress = original;
            return;
        }

        static const std::vector<u32> pattern =
        {
            0xE59F10C0, 0xE5840004, 0xE5841000, 0xE5DD0000,
            0xE5C40008, 0xE28DD03C, 0xE8BD80F0, 0xE5D51001,
            0xE1D400D4, 0xE3510003, 0x159F0034, 0x1A000003
        };

        Result  res;
        Handle  processHandle;
        s64     textTotalSize = 0;
        s64     startAddress = 0;
        u32 *   found;

        if (R_FAILED(svcOpenProcess(&processHandle, 16)))
            return;

        svcGetProcessInfo(&textTotalSize, processHandle, 0x10002);
        svcGetProcessInfo(&startAddress, processHandle, 0x10005);
        if(R_FAILED(svcMapProcessMemoryEx(CUR_PROCESS_HANDLE, 0x14000000, processHandle, (u32)startAddress, textTotalSize)))
            goto exit;

        found = (u32 *)Utils::Search<u32>(0x14000000, (u32)textTotalSize, pattern);

        if (found != nullptr)
        {
            original = found[13];
            patchAddress = (u32 *)PA_FROM_VA((found + 13));
            found[13] = 0xE1A00000;
        }

        svcUnmapProcessMemoryEx(CUR_PROCESS_HANDLE, 0x14000000, textTotalSize);
exit:
        svcCloseHandle(processHandle);
    }

    // This function is called before main and before the game starts
    // Useful to do code edits safely
    void    PatchProcess(FwkSettings &settings)
    {
        (void)settings;
        ToggleTouchscreenForceOn();
    }

    // This function is called when the process exits
    // Useful to save settings, undo patchs or clean up things
    void    OnProcessExit(void)
    {
        CleanupUdp();
        ToggleTouchscreenForceOn();
    }

    void    InitMenu(PluginMenu &menu)
    {
        MenuEntry *sendPingEntry = new MenuEntry(
            "Send UDP ping",
            SendManualPing,
            "Envoie un datagramme UDP vers l'IP/port configure dans .env"
        );

        menu += sendPingEntry;
    }

    int     main(void)
    {
        PluginMenu *menu = new PluginMenu("discord-rpc", 0, 5, 1,
                                            "Discord Rich Presence bridge plugin for 3DS.");

        // Synnchronize the menu with frame event
        menu->SynchronizeWithFrame(true);

        // Init our menu entries & folders
        InitMenu(*menu);

        const bool startSent = SendUdpPayload(BuildPayload("plugin_start"));
        OSD::Notify(startSent ? "UDP plugin_start envoye" : "UDP plugin_start echec");

        // Launch menu and mainloop
        menu->Run();

        delete menu;

        // Exit plugin
        return (0);
    }
}
