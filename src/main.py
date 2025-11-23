import os
import itertools
from tqdm import tqdm
from preprocessor import crawl_directory, clean_code, normalize_hex
from detector import calculate_combined_similarity
from llm_analyzer import analyze_pair_with_llm
from reporter import generate_html_report
from c51_compiler import compile_and_extract_asm, find_keil_c51


def check_plagiarism(root_path, hex_threshold, src_threshold, lab_name="Lab", use_keil_compilation=False, keil_path=None):

    """
    Main function to check plagiarism.

    Args:
        root_path (str): Path to the root directory containing student submissions
        hex_threshold (float): Threshold for hex similarity
        src_threshold (float): Threshold for source code similarity
        lab_name (str): Name of the lab for report generation
        use_keil_compilation (bool): Whether to compile C files to assembly for deeper comparison
        keil_path (str, optional): Path to Keil C51 installation (required if use_keil_compilation=True)
    """
    print("Step 1: Crawling and preprocessing...")
    student_files = crawl_directory(root_path)
    student_data = {}

    # Preprocess all data
    for student, files in student_files.items():
        student_data[student] = {'source': "", 'hex': "", 'original_source': "", 'illegal_submission': False, 'illegal_reason': "", 'asm_source': ""}

        # Check for illegal submission (no source files or no hex files)
        if not files['source']:
            student_data[student]['illegal_submission'] = True
            if files['all_files']:
                # Found files but not valid source
                exts = set([os.path.splitext(f)[1] for f in files['all_files']])
                student_data[student]['illegal_reason'] = f"無效提交：找到 {', '.join(exts)} 檔案，但需要 .a51 或 .c 檔案"
            else:
                student_data[student]['illegal_reason'] = "未找到任何檔案"

        # Combine all source files
        full_source = ""
        full_asm_source = ""  # For compiled assembly from C files
        full_original_source = ""

        c_files_for_compilation = []  # Track C files to compile if needed
        asm_files_content = []  # Track regular assembly files

        for src_file in files['source']:
            try:
                ext = os.path.splitext(src_file)[1]

                with open(src_file, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()

                # Store original content with filename header for display
                filename = os.path.basename(src_file)
                full_original_source += f"--- {filename} ---\n{content}\n\n"

                if ext in ['.c']:
                    full_source += clean_code(content, ext) + " "
                    if use_keil_compilation:
                        c_files_for_compilation.append(src_file)  # Queue for compilation
                elif ext in ['.a51', '.asm']:
                    full_source += clean_code(content, ext) + " "
                    asm_files_content.append(content)  # Regular assembly files
            except Exception as e:
                print(f"Error reading {src_file}: {e}")

        # If we need to compile C to assembly
        if use_keil_compilation and c_files_for_compilation:
            print(f"Compiling C files to assembly for student {student}...")
            for c_file in c_files_for_compilation:
                success, asm_code, error = compile_and_extract_asm(c_file, keil_path)
                if success:
                    full_asm_source += asm_code + " "
                    print(f"  Successfully compiled {c_file} to assembly")
                else:
                    print(f"  Failed to compile {c_file}: {error}")

        # Add regular assembly files to asm_source as well
        for asm_content in asm_files_content:
            full_asm_source += clean_code(asm_content, '.a51') + " "

        student_data[student]['source'] = full_source.strip()
        student_data[student]['asm_source'] = full_asm_source.strip()  # Assembly from C compilation + regular asm
        student_data[student]['original_source'] = full_original_source.strip()

        # Combine all hex files
        full_hex = ""
        for hex_file in files['hex']:
            try:
                with open(hex_file, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                    full_hex += normalize_hex(content)

            except Exception as e:
                print(f"Error reading {hex_file}: {e}")

        student_data[student]['hex'] = full_hex


        # Check if hex is empty (illegal submission)
        if not full_hex or full_hex.strip() == "":
            student_data[student]['illegal_submission'] = True
            if student_data[student]['illegal_reason']:
                student_data[student]['illegal_reason'] += " | 未找到有效的 hex 檔案"
            else:
                student_data[student]['illegal_reason'] = "無效提交：未找到有效的 hex 檔案"


    print("Step 2: Pairwise comparison...")
    students = list(student_data.keys())
    pairs = list(itertools.combinations(students, 2))

    results = []

    for student1, student2 in tqdm(pairs, desc="Comparing pairs", unit="pair"):
        # Determine which source to use based on whether Keil compilation was used
        if use_keil_compilation:
            src1 = student_data[student1]['asm_source']  # Use compiled assembly + regular assembly
            src2 = student_data[student2]['asm_source']
        else:
            src1 = student_data[student1]['source']  # Use original cleaned source
            src2 = student_data[student2]['source']

        # Source comparison
        src_sim = {'jaccard': 0, 'cosine': 0, 'levenshtein': 0}

        if src1 and src2:
            src_sim = calculate_combined_similarity(src1, src2)


        # Hex comparison
        hex1 = student_data[student1]['hex']
        hex2 = student_data[student2]['hex']
        hex_sim = {'jaccard': 0, 'cosine': 0, 'levenshtein': 0}
        if hex1 and hex2:
            hex_sim = calculate_combined_similarity(hex1, hex2)

        # Calculate max scores (Composite scores removed)
        max_src_sim = max(src_sim.values()) if src_sim else 0
        max_hex_sim = max(hex_sim.values()) if hex_sim else 0
        current_max = max(max_src_sim, max_hex_sim)

        # Screening: Hex any metric > 0.7 OR Source any metric > 0.8
        if max_hex_sim > hex_threshold or max_src_sim > src_threshold:
            llm_result = None
            llm_triggered = False
            verdict = "未抄襲"
            verdict_reason = ""

            # Rule 1: Hex max score = 1.0 → Definite plagiarism, skip LLM
            if max_hex_sim == 1.0:
                verdict = "抄襲"
                verdict_reason = "Hex檔案完全相同 (100%)"
                llm_triggered = False

            # Rule 2: Trigger LLM for ALL suspicious pairs (except definite plagiarism)
            else:
                llm_triggered = True
                # Use the original source for LLM analysis (more meaningful than compiled asm)
                llm_src1 = student_data[student1]['source']
                llm_src2 = student_data[student2]['source']
                llm_result = analyze_pair_with_llm(llm_src1, llm_src2)

                # Rule 3: Use LLM result if available
                if llm_result and 'is_plagiarized' in llm_result:
                    verdict = "抄襲" if llm_result['is_plagiarized'] else "未抄襲"
                    verdict_reason = f"LLM分析: {llm_result.get('reasoning', 'N/A')}"
                else:
                    # LLM unavailable, fallback to algorithm
                    verdict = "抄襲" if current_max > 0.85 else "未抄襲"
                    verdict_reason = f"LLM分析不可用 - 演算法分析: Hex Max={max_hex_sim:.2f}, Source Max={max_src_sim:.2f}"


            # Check for illegal submission - but only override if NOT plagiarized
            if (student_data[student1]['illegal_submission'] or student_data[student2]['illegal_submission']) and verdict != "抄襲":
                verdict = "無效提交"
                illegal_names = []
                if student_data[student1]['illegal_submission']:
                    illegal_names.append(student1)
                if student_data[student2]['illegal_submission']:
                    illegal_names.append(student2)
                verdict_reason = f"無效提交: {', '.join(illegal_names)}"

            results.append({
                'student1': student1,
                'student2': student2,
                'source_similarity': src_sim,
                'hex_similarity': hex_sim,
                'max_hex_sim': max_hex_sim,
                'max_src_sim': max_src_sim,
                'max_score': current_max,
                'llm_analysis': llm_result,
                'llm_triggered': llm_triggered,
                'final_verdict': verdict,
                'verdict_reason': verdict_reason,
                'source_code1': student_data[student1]['source'],
                'source_code2': student_data[student2]['source'],
                'asm_source1': student_data[student1]['asm_source'],
                'asm_source2': student_data[student2]['asm_source'],
                'original_source1': student_data[student1]['original_source'],
                'original_source2': student_data[student2]['original_source'],
                'illegal_submission1': student_data[student1]['illegal_submission'],
                'illegal_reason1': student_data[student1]['illegal_reason'],
                'illegal_submission2': student_data[student2]['illegal_submission'],
                'illegal_reason2': student_data[student2]['illegal_reason'],
                'hex_code1': hex1,
                'hex_code2': hex2
            })


    # Identify illegal students
    illegal_students = []

    for student, data in student_data.items():
        if data['illegal_submission']:
            illegal_students.append({
                'student': student,
                'reason': data['illegal_reason'],
                'files': data.get('all_files', [])
            })

    # Sort by max score descending
    results.sort(key=lambda x: x['max_score'], reverse=True)

    # Generate Report
    generate_html_report(results, hex_threshold, src_threshold, illegal_students, lab_name, use_keil_compilation)

    return results


if __name__ == "__main__":
    # User can modify these directly
    lab_name = "Lab 5"
    hex_threshold = 0.7
    src_threshold = 0.8
    use_keil_compilation = False  # Set to True to use Keil C51 compilation for C->ASM
    keil_path = None  # Set to path if use_keil_compilation=True

    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
    root_path = os.path.join(repo_root, '1141_E930600-程式碼與hex-20251120')


    results = check_plagiarism(root_path, hex_threshold, src_threshold, lab_name, use_keil_compilation, keil_path)


    print(f"\nFound {len(results)} suspicious pairs.")
    # for res in results[:5]:
    #     print(f"{res['student1']} vs {res['student2']}")
    #     print(f"  Source: {res['source_similarity']}")
    #     print(f"  Hex: {res['hex_similarity']}")

