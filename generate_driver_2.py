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
            if cursor.type.kind == clang.cindex.TypeKind.FUNCTIONPROTO and cursor.type.is_function_variadic():
                if param_decls:
                    param_decls.append("...")
                else:
                    param_decls.append("void, ...")

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

if __name__ == '__main__':
    # Create a dummy preprocessed C file for testing.
    preprocessed_c_code = """
#include <stddef.h>

int global_var1;
char global_var2;

void external_func1(int *p1, int a);
int* external_func2(void);
void external_func3();
char* external_func4(char *s);

int my_printf(char* fmt, int i, ...);
"""
    file_path = "preprocessed_test_driver2.c"
    with open(file_path, "w") as f:
        f.write(preprocessed_c_code)

    global_vars = ["global_var1", "global_var2"]
    external_funcs = ["external_func1", "external_func2", "external_func3", "external_func4", "my_printf"]

    print(f"--- Generating driver for {file_path} ---")
    driver_content = generate_driver_2(file_path, global_vars, external_funcs)

    if driver_content:
        print("\n--- Generated Driver ---")
        print(driver_content)
        print("--- End Generated Driver ---")

    # Clean up the dummy file.
    os.remove(file_path)
