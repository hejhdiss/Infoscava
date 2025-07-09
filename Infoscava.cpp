#include <iostream>      
#include <string>        
#include <filesystem>    
#include <windows.h>    
#include <cstdlib>       
const std::string APP_SUBDIRECTORY = "main";
const std::string MAIN_EXECUTABLE_NAME = "main.exe";

int main(int argc, char* argv[]) {
    char buffer[MAX_PATH];
    GetModuleFileNameA(NULL, buffer, MAX_PATH);
    std::filesystem::path launcher_path = buffer;
    std::filesystem::path install_root_dir = launcher_path.parent_path();
    std::filesystem::path main_app_executable_path = install_root_dir / APP_SUBDIRECTORY / MAIN_EXECUTABLE_NAME;
    std::string arguments_to_pass = ""; 
    char* user_profile_env = getenv("USERPROFILE");
    std::string working_directory_for_main_app_str;
    if (user_profile_env) {
        working_directory_for_main_app_str = user_profile_env;
    } else { 
        working_directory_for_main_app_str = install_root_dir.string(); 
    }
    if (argc > 1) {
        std::string filePathArg = argv[1];
        if (filePathArg.find(' ') != std::string::npos) {
            arguments_to_pass = "--file \"" + filePathArg + "\"";
        } else {
            arguments_to_pass = "--file " + filePathArg;
        }
    } else {
        arguments_to_pass = "";
    }
    const char* args_c_str = arguments_to_pass.empty() ? NULL : arguments_to_pass.c_str();
    const char* working_dir_c_str = working_directory_for_main_app_str.empty() ? NULL : working_directory_for_main_app_str.c_str();
    HINSTANCE result = ShellExecuteA(NULL, "open", main_app_executable_path.string().c_str(),
                                     args_c_str,
                                     working_dir_c_str,
                                     SW_SHOWDEFAULT);
    if (reinterpret_cast<INT_PTR>(result) <= 32) {
    }
    return 0;
}
