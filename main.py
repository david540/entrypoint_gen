import clang.cindex
import sys
import os
import subprocess
import json
import tempfile

# Configure the clang index using the CLANG_LIBRARY_FILE environment variable if it is set.
clang_library_path = os.getenv('CLANG_LIBRARY_FILE')
if clang_library_path and os.path.exists(clang_library_path):
    try:
        clang.cindex.Config.set_library_file(clang_library_path)
    except Exception as e:
        print(f"Error setting libclang path: {e}", file=sys.stderr)
        sys.exit(1)

# --- Function from extract_c_functions.py ---
def extract_functions_from_c(file_path):
    if not os.path.exists(file_path):
        print(f"Error: File not found at {file_path}", file=sys.stderr)
        return []
    index = clang.cindex.Index.create()
    tu = index.parse(file_path, args=['-Xclang', '-fsyntax-only', '-ferror-limit=0'], options=clang.cindex.TranslationUnit.PARSE_DETAILED_PROCESSING_RECORD)
    if not tu:
        return []
    functions = []
    for cursor in tu.cursor.walk_preorder():
        if cursor.kind == clang.cindex.CursorKind.FUNCTION_DECL and cursor.is_definition():
            if cursor.location.file and cursor.location.file.name == os.path.abspath(file_path):
                functions.append(cursor.spelling)
    return functions

# --- Function from preprocess_c_file.py ---
def preprocess_c_file(file_path, compile_commands_dir):
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
    args = list(commands[0].arguments)
    preprocessor_options = []
    for i, arg in enumerate(args):
        if arg.startswith('-I') or arg.startswith('-D') or arg.startswith('-U'):
            preprocessor_options.append(arg)
        elif arg in ['-isystem'] and i + 1 < len(args):
            preprocessor_options.append(arg)
            preprocessor_options.append(args[i + 1])
    clang_command = ['clang', '-E', '-P'] + preprocessor_options + [file_path]
    try:
        result = subprocess.run(clang_command, capture_output=True, text=True, check=True)
        return result.stdout
    except FileNotFoundError:
        print("Error: 'clang' command not found. Please ensure it is installed and in your PATH.", file=sys.stderr)
        return ""
    except subprocess.CalledProcessError as e:
        print(f"Error running clang -E -P:\n  Command: {' '.join(e.cmd)}\n  Exit Code: {e.returncode}\n  Stdout: {e.stdout}\n  Stderr: {e.stderr}", file=sys.stderr)
        return ""

# --- Function from find_entrypoints.py ---
def find_entrypoints(preprocessed_file_path, function_names):
    if not os.path.exists(preprocessed_file_path):
        return set()
    index = clang.cindex.Index.create()
    tu = index.parse(preprocessed_file_path)
    if not tu:
        return set()
    callees = set()
    for cursor in tu.cursor.walk_preorder():
        if cursor.kind == clang.cindex.CursorKind.FUNCTION_DECL and cursor.is_definition():
            caller_name = cursor.spelling
            if caller_name in function_names:
                for child in cursor.walk_preorder():
                    if child.kind == clang.cindex.CursorKind.CALL_EXPR:
                        callee_name = child.spelling
                        if callee_name in function_names:
                            callees.add(callee_name)
    return set(function_names) - callees

# --- Function from generate_driver.py ---
def generate_driver(c_file_name, preprocessed_file_path, entrypoints):
    if not os.path.exists(preprocessed_file_path):
        return ""
    driver_code = [f'#include "{c_file_name}"\n', "void make_unknown(void *data, unsigned long size);\n", "#define max(a,b) (((a) > (b)) ? (a) : (b))\n", "int main() {"]
    index = clang.cindex.Index.create()
    tu = index.parse(preprocessed_file_path)
    if not tu:
        return ""
    function_decls = {c.spelling: c for c in tu.cursor.walk_preorder() if c.kind == clang.cindex.CursorKind.FUNCTION_DECL and c.is_definition()}
    for entrypoint in entrypoints:
        if entrypoint not in function_decls:
            driver_code.append(f"    // Warning: Could not find definition for entrypoint '{entrypoint}'. Skipping.")
            continue
        driver_code.append("    {")
        func_cursor = function_decls[entrypoint]
        arg_names = []
        params = [c for c in func_cursor.get_children() if c.kind == clang.cindex.CursorKind.PARM_DECL]
        for param in params:
            arg_name = param.spelling or f"arg_{len(arg_names)}"
            arg_type = param.type.spelling
            arg_names.append(arg_name)
            driver_code.append(f"        {arg_type} {arg_name};")
            if param.type.kind == clang.cindex.TypeKind.POINTER:
                driver_code.append(f"        make_unknown(&{arg_name}, max(16, sizeof(*{arg_name})));")
            else:
                driver_code.append(f"        make_unknown(&{arg_name}, sizeof({arg_name}));")
        driver_code.append(f"        {entrypoint}({', '.join(arg_names)});")
        driver_code.append("    }")
    driver_code.extend(["    return 0;", "}"])
    return "\n".join(driver_code)

if __name__ == '__main__':
    if len(sys.argv) != 2:
        print(f"Usage: python3 {sys.argv[0]} <c_file_path>")
        sys.exit(1)

    compile_commands_dir = os.path.abspath(".") # Assume compile_commands.json is in the current directory
    compile_commands_path = os.path.join(compile_commands_dir, "compile_commands.json")
    if not os.path.exists(compile_commands_path):
        print(f"Error: compile_commands.json not found at {compile_commands_path}.")
        print("Please run the script from the directory containing compile_commands.json.")
        sys.exit(1)

    c_file_path = os.path.abspath(sys.argv[1])

    # 1. Extract function names
    print("--- (1/4) Extracting function names ---")
    all_functions = extract_functions_from_c(c_file_path)
    print(f"Found {len(all_functions)} functions: {all_functions}")

    # 2. Preprocess the file
    print("\n--- (2/4) Preprocessing file ---")
    preprocessed_code = preprocess_c_file(c_file_path, compile_commands_dir)
    if not preprocessed_code:
        sys.exit(1)
    # Create a temporary file for the preprocessed code
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.c') as tmp_file:
        tmp_file.write(preprocessed_code)
        preprocessed_file_path = tmp_file.name
    print(f"Preprocessed file written to: {preprocessed_file_path}")

    # 3. Find entrypoints
    print("\n--- (3/4) Finding entrypoints ---")
    entrypoints = find_entrypoints(preprocessed_file_path, all_functions)
    print(f"Found {len(entrypoints)} entrypoints: {sorted(list(entrypoints))}")

    # 4. Generate the driver
    print("\n--- (4/4) Generating driver ---")
    driver_code = generate_driver(os.path.basename(c_file_path), preprocessed_file_path, sorted(list(entrypoints)))
    if driver_code:
        print("\n--- Generated Driver ---")
        print(driver_code)
        print("--- End Generated Driver ---")

    # Clean up the temporary file
    os.remove(preprocessed_file_path)
