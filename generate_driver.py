

import clang.cindex
import sys
import os

# Configure the clang index using the CLANG_LIBRARY_FILE environment variable if it is set.
clang_library_path = os.getenv('CLANG_LIBRARY_FILE')
if clang_library_path and os.path.exists(clang_library_path):
    try:
        clang.cindex.Config.set_library_file(clang_library_path)
    except Exception as e:
        print(f"Error setting libclang path: {e}", file=sys.stderr)
        sys.exit(1)

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

if __name__ == '__main__':
    # Create a dummy preprocessed C file for testing.
    preprocessed_c_code = """
void takes_ptr(int *a, char *b) {}
void takes_value(int x) {}
void no_args(void) {}
"""
    file_path = "preprocessed_test.c"
    with open(file_path, "w") as f:
        f.write(preprocessed_c_code)

    c_file_name = "my_app.c"
    entrypoints = ["takes_ptr", "takes_value", "no_args", "non_existent_func"]

    print(f"--- Generating driver for {c_file_name} ---")
    driver_content = generate_driver(c_file_name, file_path, entrypoints)

    if driver_content:
        print("\n--- Generated Driver ---")
        print(driver_content)
        print("--- End Generated Driver ---")

    # Clean up the dummy file.
    os.remove(file_path)

