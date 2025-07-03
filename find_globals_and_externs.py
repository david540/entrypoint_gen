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
                       referenced.semantic_parent.kind == clang.cindex.CursorKind.TRANSLATION_UNIT and \
                       not referenced.type.is_const_qualified():
                        global_vars.add(referenced.spelling)
                        
                    # Check for external functions
                    elif referenced.kind == clang.cindex.CursorKind.FUNCTION_DECL and \
                         not referenced.is_definition() and \
                         referenced.spelling not in function_names_set:
                        external_funcs.add(referenced.spelling)

    return {'global_vars': global_vars, 'external_funcs': external_funcs}

if __name__ == '__main__':
    # Create a dummy preprocessed C file for testing.
    preprocessed_c_code = """
int global_var = 10;
int another_global = 5;
int const const_global = 15;

// Declaration of an external function
void external_func();

void bar() {
    global_var = const_global;
}

void foo() {
    bar();
    external_func();
}

void main() {
    foo();
    another_global = global_var;
}
"""
    file_path = "preprocessed_test_globals.c"
    with open(file_path, "w") as f:
        f.write(preprocessed_c_code)

    function_names = ["main", "foo", "bar"]

    print(f"--- Analyzing functions in {file_path} ---")
    results = find_globals_and_externs(file_path, function_names)

    if results:
        print("\n--- Used Global Variables ---")
        for var in sorted(list(results['global_vars'])):
            print(f"  - {var}")
        print("--- End Global Variables ---")

        print("\n--- Used External Functions ---")
        for func in sorted(list(results['external_funcs'])):
            print(f"  - {func}")
        print("--- End External Functions ---")

    # Clean up the dummy file.
    os.remove(file_path)
