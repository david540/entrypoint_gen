

import clang.cindex
import sys
import os
import subprocess
import json

# Configure the clang index using the CLANG_LIBRARY_FILE environment variable if it is set.
clang_library_path = os.getenv('CLANG_LIBRARY_FILE')
if clang_library_path and os.path.exists(clang_library_path):
    try:
        clang.cindex.Config.set_library_file(clang_library_path)
    except Exception as e:
        print(f"Error setting libclang path: {e}", file=sys.stderr)
        sys.exit(1)

def preprocess_c_file(file_path, compile_commands_dir):
    """
    Preprocesses a C file using clang -E -P with options from compile_commands.json.

    Args:
        file_path (str): The absolute path to the C file.
        compile_commands_dir (str): The absolute path to the directory containing compile_commands.json.

    Returns:
        str: The preprocessed output, or an empty string if an error occurs.
    """
    if not os.path.exists(file_path):
        print(f"Error: File not found at {file_path}", file=sys.stderr)
        return ""

    try:
        compdb = clang.cindex.CompilationDatabase.fromDirectory(compile_commands_dir)
    except clang.cindex.CompilationDatabaseError:
        print(f"Error: Could not load compile_commands.json from {compile_commands_dir}", file=sys.stderr)
        return ""

    commands = compdb.getCompileCommands(file_path)
    if not commands:
        print(f"Error: Could not find compile commands for {file_path}", file=sys.stderr)
        return ""

    # Extract relevant preprocessing options (e.g., -I, -D, -U)
    args = list(commands[0].arguments)
    preprocessor_options = []
    for i, arg in enumerate(args):
        if arg.startswith('-I') or arg.startswith('-D') or arg.startswith('-U'):
            preprocessor_options.append(arg)
        # Some options like -isystem have a space, so we need to get the next argument
        elif arg in ['-isystem', '-I', '-include', '-D', '-U'] and i + 1 < len(args):
            preprocessor_options.append(arg)
            preprocessor_options.append(args[i + 1])

    # Build and run the clang command
    clang_command = ['clang', '-E', '-P'] + preprocessor_options + [file_path]
    
    print(f"Running command: {' '.join(clang_command)}")

    try:
        result = subprocess.run(clang_command, capture_output=True, text=True, check=True)
        return result.stdout
    except FileNotFoundError:
        print("Error: 'clang' command not found. Please ensure it is installed and in your PATH.", file=sys.stderr)
        return ""
    except subprocess.CalledProcessError as e:
        print(f"Error running clang: {e}", file=sys.stderr)
        print(f"Stderr: {e.stderr}", file=sys.stderr)
        return ""

if __name__ == '__main__':
    # Create a dummy project structure
    build_dir = os.path.abspath("build")
    src_dir = os.path.abspath("src")
    os.makedirs(build_dir, exist_ok=True)
    os.makedirs(src_dir, exist_ok=True)

    # Create a dummy C file
    c_file_path = os.path.join(src_dir, "test.c")
    with open(c_file_path, "w") as f:
        f.write("""
#include "my_header.h"

#ifdef MY_MACRO
#define STRING_MACRO "Hello from macro!"
#else
#define STRING_MACRO "Macro not defined!"
#endif

int main() {
    const char* my_string = STRING_MACRO;
    return 0;
}
""")

    # Create a dummy header file
    header_file_path = os.path.join(src_dir, "my_header.h")
    with open(header_file_path, "w") as f:
        f.write("// This is a dummy header file.\n")

    # Create a dummy compile_commands.json
    compile_commands = [
        {
            "directory": src_dir,
            "command": f"gcc -c {c_file_path} -o {os.path.join(build_dir, 'test.o')} -DMY_MACRO -I{src_dir}",
            "file": c_file_path
        }
    ]
    compile_commands_path = os.path.join(build_dir, "compile_commands.json")
    with open(compile_commands_path, "w") as f:
        json.dump(compile_commands, f, indent=2)

    print(f"--- Preprocessing {c_file_path} ---")
    preprocessed_code = preprocess_c_file(c_file_path, build_dir)

    if preprocessed_code:
        print("\n--- Preprocessed Output ---")
        print(preprocessed_code)
        print("--- End Preprocessed Output ---")

    # Clean up the dummy files and directories
    os.remove(c_file_path)
    os.remove(header_file_path)
    os.remove(compile_commands_path)
    os.rmdir(src_dir)
    os.rmdir(build_dir)

