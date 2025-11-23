"""Preprocessor utilities (moved to src root)."""
import os
import re

def crawl_directory(root_path):
    """
    Recursively finds relevant files (.a51, .c, .hex) in the directory.
    Returns a dictionary where keys are student IDs (folder names) and values are lists of file paths.
    Also tracks 'all_files' to help identify illegal submissions.
    .a51 and .c files are considered valid source code.
    """
    student_files = {}

    # Walk through the directory
    for root, dirs, files in os.walk(root_path):
        # Assuming the immediate subdirectories of root_path are student folders
        # We need to identify which folder belongs to which student
        # The structure seems to be: root_path / student_folder / files...

        rel_path = os.path.relpath(root, root_path)
        if rel_path == '.':
            continue

        # Extract student ID from the first level folder
        path_parts = rel_path.split(os.sep)
        student_id = path_parts[0]

        if student_id not in student_files:
            student_files[student_id] = {'source': [], 'hex': [], 'all_files': []}

        for file in files:
            ext = os.path.splitext(file)[1].lower()
            full_path = os.path.join(root, file)

            student_files[student_id]['all_files'].append(full_path)

            if ext in ['.a51', '.c']:  # .a51 and .c files are valid source code
                student_files[student_id]['source'].append(full_path)
            elif ext == '.hex':
                student_files[student_id]['hex'].append(full_path)

    return student_files

def clean_code(content, file_extension):
    """
    Removes comments and normalizes whitespace based on file extension.
    """
    if file_extension in ['.a51', '.asm']:
        return clean_asm_code(content)
    elif file_extension in ['.c', '.txt']: # Assuming txt is C-like or mixed
        return clean_c_code(content)
    else:
        # Default cleaning for unknown extensions
        # Remove C comments // and /* */ as a safe default
        content = re.sub(r'//.*', '', content)
        content = re.sub(r'/\*.*?\*/', '', content, flags=re.DOTALL)

        # Normalize whitespace
        content = re.sub(r'\s+', ' ', content)

        # Convert to lowercase for case-insensitive comparison
        content = content.lower()

        return content.strip()


def clean_c_code(content):
    """
    Specifically cleans C code by removing preprocessor directives, common keywords, and focusing on logic.
    """
    # Remove C preprocessor directives (#include, #define, etc.)
    content = re.sub(r'^\s*#.*$', '', content, flags=re.MULTILINE)

    # Remove C comments // and /* */
    content = re.sub(r'//.*', '', content)
    content = re.sub(r'/\*.*?\*/', '', content, flags=re.DOTALL)

    # Remove common C keywords that don't affect logic (to focus on actual algorithm)
    # This is optional - we might want to keep these for more accurate comparison
    # content = re.sub(r'\b(int|char|float|double|void|long|short|signed|unsigned)\b', '', content)
    # content = re.sub(r'\b(if|else|for|while|do|switch|case|default|break|continue|return|goto)\b', '', content)

    # Normalize whitespace
    content = re.sub(r'\s+', ' ', content)

    # Convert to lowercase for case-insensitive comparison
    content = content.lower()

    return content.strip()


def clean_asm_code(content):
    """
    Specifically cleans assembly code by removing comments and normalizing.
    """
    # Assembly comments start with ;
    content = re.sub(r';.*', '', content)

    # Remove common assembly directives (optional, might be important for 8051)
    # content = re.sub(r'^\s*\..*$', '', content, flags=re.MULTILINE)  # General directive removal

    # Normalize whitespace
    content = re.sub(r'\s+', ' ', content)

    # Convert to lowercase for case-insensitive comparison
    content = content.lower()

    return content.strip()

def normalize_hex(content):
    """
    Parses Intel HEX format, extracts data payload.
    Ignores checksums, addresses, and record types to focus on data.
    """
    data_payload = ""
    lines = content.splitlines()

    for line in lines:
        line = line.strip()
        if not line.startswith(':'):
            continue

        # Intel HEX format: :LLAAAATT[DD...]CC
        # LL = Length (2 hex chars)
        # AAAA = Address (4 hex chars)
        # TT = Type (2 hex chars)
        # DD = Data (LL * 2 hex chars)
        # CC = Checksum (2 hex chars)

        try:
            byte_count = int(line[1:3], 16)
            record_type = int(line[7:9], 16)

            # Record Type 00 is Data
            if record_type == 0:
                data_start = 9
                data_end = 9 + (byte_count * 2)
                data = line[data_start:data_end]
                data_payload += data
        except ValueError:
            continue

    return data_payload.lower()
