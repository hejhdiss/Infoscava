#include <stdio.h>       
#include <stdlib.h>      
#include <string.h>      
#include <unistd.h>      
#include <sys/wait.h>    
#include <libgen.h>      
#include <limits.h>     
const char APP_SUBDIRECTORY[] = "main";
const char MAIN_EXECUTABLE_NAME[] = "main";
int main(int argc, char* argv[]) {
    char launcher_path_buffer[PATH_MAX];          
    char install_root_dir_buffer[PATH_MAX];       
    char main_app_executable_path_buffer[PATH_MAX]; 
    char working_directory_for_main_app_buffer[PATH_MAX]; 
    ssize_t len = readlink("/proc/self/exe", launcher_path_buffer, sizeof(launcher_path_buffer) - 1);
    if (len == -1) {
        fprintf(stderr, "Error: Could not determine launcher path.\n");
        return 1;
    }
    launcher_path_buffer[len] = '\0';
    strcpy(install_root_dir_buffer, launcher_path_buffer);
    char* dir_name = dirname(install_root_dir_buffer);
    strcpy(install_root_dir_buffer, dir_name); 
    snprintf(main_app_executable_path_buffer, sizeof(main_app_executable_path_buffer),
             "%s/%s/%s", install_root_dir_buffer, APP_SUBDIRECTORY, MAIN_EXECUTABLE_NAME);
    const char* user_home_env = getenv("HOME");
    if (user_home_env) {
        strcpy(working_directory_for_main_app_buffer, user_home_env);
    } else {
        strcpy(working_directory_for_main_app_buffer, install_root_dir_buffer);
    }
    char* argv_exec[4]; /
    int arg_count = 0;

    argv_exec[arg_count++] = main_app_executable_path_buffer; 

    if (argc > 1) {
        argv_exec[arg_count++] = (char*)"--file";
        argv_exec[arg_count++] = argv[1]; 
    }
    argv_exec[arg_count] = NULL; 
    if (chdir(working_directory_for_main_app_buffer) != 0) {
        fprintf(stderr, "Warning: Could not change working directory to %s\n", working_directory_for_main_app_buffer);
    }
    pid_t pid = fork();

    if (pid == -1) {
        fprintf(stderr, "Error: Failed to fork process.\n");
        return 1;
    } else if (pid == 0) {
        execvp(main_app_executable_path_buffer, argv_exec);
        fprintf(stderr, "Error: Failed to execute main application: %s\n", main_app_executable_path_buffer);
        _exit(1); 
    } else {
        int status;
        waitpid(pid, &status, 0); 

        if (WIFEXITED(status) && WEXITSTATUS(status) != 0) {
            fprintf(stderr, "Main application exited with error code: %d\n", WEXITSTATUS(status));
        }
    }
    return 0; /
}
