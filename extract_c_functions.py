

import clang.cindex
import sys
import os



def extract_functions_from_c(file_path):
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

if __name__ == '__main__':
    
    # Configure the clang index using the CLANG_LIBRARY_FILE environment variable if it is set.
    clang_library_path = os.getenv('CLANG_LIBRARY_FILE')
    if clang_library_path and os.path.exists(clang_library_path):
        try:
            clang.cindex.Config.set_library_file(clang_library_path)
        except Exception as e:
            print(f"Error setting libclang path: {e}", file=sys.stderr)
            sys.exit(1)
        
        
    # Create a dummy valid C file for testing
    with open("valid_test.c", "w") as f:
        f.write("""
#include <stdio.h>

// Function prototype
void anotherFunction(int a);

void helper_function(void) {
    // This is a helper
}

int main() {
    printf("Hello, World!\n");
    return 0;
}
""")

    # Create a dummy invalid C file for testing
    with open("invalid_test.c", "w") as f:
        f.write("""
#include <stdio.h>
#include "not_a_real_header.h"
very bad syntax here;

int function_with_error(int x) {
    return x + ; // Syntax error here
}

static char another_valid_function(char c)
{
    return c;
}

void
no_return_type() {
    // another syntax error
    printf("hi")
}
""")

    print("--- Testing with a valid C file (valid_test.c) ---")
    valid_functions = extract_functions_from_c("valid_test.c")
    print(f"Functions found: {valid_functions}")
    print("\n--- Testing with an invalid C file (invalid_test.c) ---")
    invalid_functions = extract_functions_from_c("invalid_test.c")
    print(f"Functions found: {invalid_functions}")

    # Clean up the dummy files
    os.remove("valid_test.c")
    os.remove("invalid_test.c")

