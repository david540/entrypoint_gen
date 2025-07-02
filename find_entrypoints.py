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

if __name__ == '__main__':
    # Create a dummy preprocessed C file for testing.
    preprocessed_c_code = """
void bar() {
    // Does nothing
}

void foo() {
    bar();
}

void main() {
    foo();
}

static void standalone() {
    // Not called by anyone in the list.
}

static void baz() {
    standalone();
}
"""
    file_path = "preprocessed_test.c"
    with open(file_path, "w") as f:
        f.write(preprocessed_c_code)

    function_names = ["main", "foo", "bar", "standalone", "baz"]

    print(f"--- Finding entrypoints in {file_path} ---")
    entrypoints = find_entrypoints(file_path, function_names)

    if entrypoints:
        print("\n--- Entrypoints Found ---")
        for entrypoint in sorted(list(entrypoints)):
            print(f"  - {entrypoint}")
        print("--- End Entrypoints ---")

    # Clean up the dummy file.
    os.remove(file_path)
