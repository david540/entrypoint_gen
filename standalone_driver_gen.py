import sys
import os
import argparse
import subprocess
import clang.cindex

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

def extract_c_functions(file_path):
    """
    Parses a C file and extracts the names of functions defined within it.

    This function uses libclang to parse the C file. It can extract function
    names even if the file contains syntax errors. It specifically identifies
    function definitions and ignores declarations (e.g., from header files).

    Args:
        file_path (str): The path to the C file.

    Returns:
        list: A list of strings, where each string is the name of a function
              defined in the C file.
    """
    if not os.path.exists(file_path):
        print(f"Error: File not found at {file_path}", file=sys.stderr)
        return []

    abs_file_path = os.path.abspath(file_path)

    try:
        index = clang.cindex.Index.create()
    except clang.cindex.LibclangError:
        print(f"Error: libclang library not found.", file=sys.stderr)
        print("Please install libclang or set the CLANG_LIBRARY_FILE environment variable to the full path of your libclang.so file.", file=sys.stderr)
        return []
    
    # Use options to make parsing more lenient to errors
    args = ['-Xclang', '-fsyntax-only', '-ferror-limit=0']
    # PARSE_DETAILED_PROCESSING_RECORD is required for is_definition() to work correctly
    tu = index.parse(abs_file_path, args=args, options=clang.cindex.TranslationUnit.PARSE_DETAILED_PROCESSING_RECORD)

    if not tu:
        print("Error: Could not parse the translation unit.", file=sys.stderr)
        return []

    functions = []
    for cursor in tu.cursor.walk_preorder():
        # We are looking for function definitions, not just declarations.
        # A function definition has a body.
        # We also check that the function is in the main file, not a header.
        if cursor.kind == clang.cindex.CursorKind.FUNCTION_DECL and cursor.is_definition():
            if cursor.location.file and cursor.location.file.name == abs_file_path:
                functions.append(cursor.spelling)

    return functions

def find_globals_and_externs(preprocessed_file_path, function_names):
    """
    Finds all used global variables and external functions within a given list of functions.

    Args:
        preprocessed_file_path (str): The path to the preprocessed C file.
        function_names (list): A list of function names to analyze.

    Returns:
        dict: A dictionary with two keys: 'global_vars' and 'external_funcs',
              containing sets of the corresponding names.
    """
    if not os.path.exists(preprocessed_file_path):
        print(f"Error: File not found at {preprocessed_file_path}", file=sys.stderr)
        return {'global_vars': set(), 'external_funcs': set()}

    index = clang.cindex.Index.create()
    tu = index.parse(preprocessed_file_path)

    if not tu:
        print("Error: Could not parse the translation unit.", file=sys.stderr)
        return {'global_vars': set(), 'external_funcs': set()}

    global_vars = set()
    external_funcs = set()
    function_names_set = set(function_names)

    for func_cursor in tu.cursor.walk_preorder():
        if func_cursor.kind == clang.cindex.CursorKind.FUNCTION_DECL and \
           func_cursor.is_definition() and func_cursor.spelling in function_names_set:
            
            for child in func_cursor.walk_preorder():
                if child.kind == clang.cindex.CursorKind.DECL_REF_EXPR:
                    referenced = child.referenced
                    
                    # Check for global variables
                    if referenced.kind == clang.cindex.CursorKind.VAR_DECL and \
                       referenced.semantic_parent.kind == clang.cindex.CursorKind.TRANSLATION_UNIT:
                        global_vars.add(referenced.spelling)
                        
                    # Check for external functions
                    elif referenced.kind == clang.cindex.CursorKind.FUNCTION_DECL and \
                         not referenced.is_definition() and \
                         referenced.spelling not in function_names_set:
                        external_funcs.add(referenced.spelling)

    return {'global_vars': global_vars, 'external_funcs': external_funcs}

def find_entrypoints(preprocessed_file_path, function_names):
    """
    Finds the minimum subset of function names required to reach all other functions in the list.

    Args:
        preprocessed_file_path (str): The path to the preprocessed C file.
        function_names (list): A list of function names to analyze.

    Returns:
        set: A set of function names that are the entrypoints.
    """
    if not os.path.exists(preprocessed_file_path):
        print(f"Error: File not found at {preprocessed_file_path}", file=sys.stderr)
        return set()

    index = clang.cindex.Index.create()
    tu = index.parse(preprocessed_file_path)

    if not tu:
        print("Error: Could not parse the translation unit.", file=sys.stderr)
        return set()

    # A set of all functions that are called by other functions in the list.
    callees = set()

    # Iterate through all function definitions in the file.
    for cursor in tu.cursor.walk_preorder():
        if cursor.kind == clang.cindex.CursorKind.FUNCTION_DECL and cursor.is_definition():
            caller_name = cursor.spelling
            # Only consider callers that are in our input list.
            if caller_name in function_names:
                # Walk the AST of the function body to find function calls.
                for child in cursor.walk_preorder():
                    if child.kind == clang.cindex.CursorKind.CALL_EXPR:
                        callee_name = child.spelling
                        # If the called function is also in our list, add it to the set of callees.
                        if callee_name in function_names:
                            callees.add(callee_name)

    # The entrypoints are the functions in our list that are never called by other functions in the list.
    entrypoints = set(function_names) - callees
    return entrypoints

def generate_driver(c_file_name, preprocessed_file_path, entrypoints):
    """
    Generates a C driver file to call a list of entrypoint functions.

    Args:
        c_file_name (str): The name of the original C file to be included.
        preprocessed_file_path (str): The path to the preprocessed C file for parsing.
        entrypoints (list): A list of function names to be called in the driver.

    Returns:
        str: The content of the generated C driver file.
    """
    if not os.path.exists(preprocessed_file_path):
        print(f"Error: File not found at {preprocessed_file_path}", file=sys.stderr)
        return ""

    driver_code = []
    driver_code.append(f'#include "{c_file_name}"\n')
    driver_code.append("// Forward declaration for the function to create unknown values.")
    driver_code.append("void make_unknown(void *data, unsigned long size);\n")
    driver_code.append("// A simple max macro.")
    driver_code.append("#define max(a,b) (((a) > (b)) ? (a) : (b))\n")

    driver_code.append("int main() {")

    index = clang.cindex.Index.create()
    tu = index.parse(preprocessed_file_path)

    if not tu:
        print("Error: Could not parse the translation unit.", file=sys.stderr)
        return ""

    # Create a map of function names to their AST cursors for easy access.
    function_decls = {}
    for cursor in tu.cursor.walk_preorder():
        if cursor.kind == clang.cindex.CursorKind.FUNCTION_DECL and cursor.is_definition():
            function_decls[cursor.spelling] = cursor

    for entrypoint in entrypoints:
        if entrypoint not in function_decls:
            driver_code.append(f"    // Warning: Could not find definition for entrypoint '{entrypoint}'. Skipping.")
            continue

        driver_code.append("    {")
        func_cursor = function_decls[entrypoint]
        arg_names = []

        # Get function parameters.
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

    driver_code.append("    return 0;")
    driver_code.append("}")

    return "\n".join(driver_code)

def generate_driver_2(preprocessed_file_path, global_vars, external_funcs):
    """
    Generates a C driver file with randomized global variables and mock external functions.

    Args:
        preprocessed_file_path (str): The path to the preprocessed C file for parsing.
        global_vars (list): A list of global variable names.
        external_funcs (list): A list of external function names.

    Returns:
        str: The content of the generated C driver file.
    """
    if not os.path.exists(preprocessed_file_path):
        print(f"Error: File not found at {preprocessed_file_path}", file=sys.stderr)
        return ""

    driver_code = []
    driver_code.append("// Forward declarations for utility functions.")
    driver_code.append("void make_unknown(void *data, unsigned long size);")
    driver_code.append("void *alloc_safe(unsigned long size);")
    driver_code.append("void _check_initialized(void *data, unsigned long size);")
    driver_code.append("#define check_initialized(x) _check_initialized(&(x), sizeof(x))\n")


    index = clang.cindex.Index.create()
    tu = index.parse(preprocessed_file_path)

    if not tu:
        print("Error: Could not parse the translation unit.", file=sys.stderr)
        return ""

    # Generate randomize_all_global_vars function
    driver_code.append("void randomize_all_global_vars() {")
    for var_name in global_vars:
        found = False
        for cursor in tu.cursor.walk_preorder():
            if cursor.kind == clang.cindex.CursorKind.VAR_DECL and cursor.spelling == var_name:
                driver_code.append(f"    make_unknown(&{var_name}, sizeof({var_name}));")
                found = True
                break
        if not found:
            print(f"Warning: Could not find global variable '{var_name}' in the TU.", file=sys.stderr)

    driver_code.append("}\n")

    # Generate definitions for external functions
    for cursor in tu.cursor.walk_preorder():
        if cursor.kind == clang.cindex.CursorKind.FUNCTION_DECL and cursor.spelling in external_funcs and not cursor.is_definition():
            func_name = cursor.spelling
            return_type = cursor.result_type.spelling
            
            param_decls = []
            param_names = []
            i = 0
            for param in cursor.get_children():
                if param.kind == clang.cindex.CursorKind.PARM_DECL:
                    param_name = param.spelling or f"arg{i}"
                    param_type = param.type.spelling
                    param_decls.append(f"{param_type} {param_name}")
                    param_names.append(param_name)
                    i += 1

            driver_code.append(f"{return_type} {func_name}({', '.join(param_decls)}) {{")
            driver_code.append("    randomize_all_global_vars();")

            i = 0
            for param in cursor.get_children():
                if param.kind == clang.cindex.CursorKind.PARM_DECL:
                    param_name = param.spelling or f"arg{i}"
                    driver_code.append(f"    check_initialized({param_name});")
                    if param.type.kind == clang.cindex.TypeKind.POINTER:
                        driver_code.append(f"    check_initialized(*{param_name});")
                        pointee_type = param.type.get_pointee()
                        if not pointee_type.is_const_qualified():
                            driver_code.append(f"    make_unknown({param_name}, sizeof(*{param_name}));")
                    i += 1
            
            if cursor.result_type.kind != clang.cindex.TypeKind.VOID:
                if cursor.result_type.kind == clang.cindex.TypeKind.POINTER:
                    pointee_type = cursor.result_type.get_pointee()
                    driver_code.append(f"    {return_type} out = ({return_type})alloc_safe(sizeof({pointee_type.spelling}));")
                    driver_code.append("    make_unknown(out, sizeof(*out));")
                else:
                    driver_code.append(f"    {return_type} out;")
                    driver_code.append("    make_unknown(&out, sizeof(out));")
                driver_code.append("    return out;")

            driver_code.append("}\n")

    return "\n".join(driver_code)

def main():
    parser = argparse.ArgumentParser(description='Generate a C driver for a given C file.')
    parser.add_argument('c_file', help='The input C file.')
    parser.add_argument('--output', '-o', default='driver.c', help='The output driver file.')
    parser.add_argument('--compile-commands-dir', default='.', help='The directory containing compile_commands.json.')

    args = parser.parse_args()

    c_file_path = os.path.abspath(args.c_file)
    compile_commands_dir = os.path.abspath(args.compile_commands_dir)
    output_file_path = os.path.abspath(args.output)

    # 1. Get all function names
    print("--- Extracting all function names ---")
    all_function_names = extract_c_functions(c_file_path)
    if not all_function_names:
        print("No functions found in the preprocessed file.")
        os.remove(preprocessed_file_path)
        sys.exit(1)

    # 2. Preprocess the C file
    print(f"--- Preprocessing {c_file_path} ---")
    preprocessed_code = preprocess_c_file(c_file_path, compile_commands_dir)
    if not preprocessed_code:
        sys.exit(1)

    preprocessed_file_path = "preprocessed_temp.c"
    with open(preprocessed_file_path, "w") as f:
        f.write(preprocessed_code)

    # 3. Find used global variables and external functions
    print("--- Finding used global variables and external functions ---")
    results = find_globals_and_externs(preprocessed_file_path, all_function_names)
    global_vars = results['global_vars']
    external_funcs = results['external_funcs']

    # 4. Find the minimal set of entrypoints
    print("--- Finding the minimal set of entrypoints ---")
    entrypoints = find_entrypoints(preprocessed_file_path, all_function_names)

    # 5. Generate the driver file
    print(f"--- Generating driver file: {output_file_path} ---")
    driver_part1 = generate_driver_2(preprocessed_file_path, global_vars, external_funcs)
    driver_part2 = generate_driver(os.path.basename(c_file_path), preprocessed_file_path, entrypoints)

    # Combine the two parts
    final_driver_code = f'#include "{os.path.basename(c_file_path)}"\n'
    final_driver_code += driver_part1
    
    # Extract the main function from driver_part2 and append it
    main_func_body = driver_part2.split("int main() {")[1]
    final_driver_code += "\nint main() {\n"
    final_driver_code += "    randomize_all_global_vars();\n"
    final_driver_code += main_func_body

    with open(output_file_path, "w") as f:
        f.write(final_driver_code)

    print(f"--- Driver generated successfully: {output_file_path} ---")

    # Clean up the temporary preprocessed file
    #os.remove(preprocessed_file_path)

if __name__ == '__main__':
    main()
