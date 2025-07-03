import sys
import os
import argparse
from preprocess_c_file import preprocess_c_file
from extract_c_functions import extract_c_functions
from find_globals_and_externs import find_globals_and_externs
from find_entrypoints import find_entrypoints
from generate_driver import generate_driver
from generate_driver_2 import generate_driver_2

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
