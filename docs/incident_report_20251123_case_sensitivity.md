# Zero Similarity Score Bug - Case-Sensitivity Issue
**Date:** 2025-11-23  
**Subject:** Critical bug causing all source similarity scores to be 0.00 for files with uppercase extensions

## 1. Overview
A critical bug was discovered where the plagiarism detection system reported 0.00 source similarity scores for all student pairs in Lab 5, despite students having valid `.A51` assembly files. The root cause was a **case-sensitivity mismatch** in file extension handling between `preprocessor.py` and `main.py`.

## 2. Symptoms
- Source similarity scores were consistently 0.00 for real student files
- Hex similarity scores were calculated correctly (non-zero)
- Test files with lowercase extensions (`.c`) worked correctly
- The issue only affected files with uppercase extensions (`.A51`, `.ASM`)

### Example from User Report
| Rank | Student 1 | Student 2 | Hex Score | Source (Avg) | Verdict |
|------|-----------|-----------|-----------|--------------|---------|
| 2 | C44101175 | E94121070 | 1.00 | **0.00** | 抄襲 |
| 3 | C44101175 | E94121169 | 1.00 | **0.00** | 抄襲 |
| 5 | E94124052 | E94126282 | 1.00 | **0.00** | 抄襲 |

All three students (`E94121070`, `E94121169`, `E94124052`, `E94126282`) had valid `.A51` files, but source scores were 0.00.

## 3. Root Cause Analysis

### 3.1 The Bug
In `preprocessor.py`, the `crawl_directory` function correctly lowercases file extensions:
```python
# preprocessor.py - crawl_directory (CORRECT)
ext = os.path.splitext(file)[1].lower()  # ✓ Converts .A51 → .a51
if ext in ['.a51', '.asm', '.c']:
    student_files[student_id]['source'].append(full_path)
```

However, in `main.py`, the file processing loop did NOT lowercase extensions:
```python
# main.py - check_plagiarism (BUG)
ext = os.path.splitext(src_file)[1]  # ✗ Returns .A51 (uppercase)

if ext in ['.c']:
    # Process C files
    ...
elif ext in ['.a51', '.asm']:  # ✗ .A51 != .a51, so this never matches!
    # Process assembly files
    ...
```

### 3.2 Impact Chain
1. `crawl_directory` finds files with `.A51` extension → adds to `files['source']`
2. `main.py` iterates over `files['source']`
3. For each file, `ext = '.A51'` (uppercase)
4. Check `if ext in ['.a51', '.asm']` → **False** (case-sensitive comparison)
5. File is skipped, no code is added to `full_source`
6. `full_source` remains empty string `""`
7. Similarity calculation: `calculate_combined_similarity("", "")` → `0.00`

### 3.3 Why TestStudent Worked
The test files used lowercase extensions:
```
TestStudent_C/
├── main.c    ← Lowercase .c
└── main.hex
```

Since `.c` (lowercase) matched `['.c']`, test files were processed correctly.

## 4. Investigation Process

### 4.1 Initial Hypotheses (Incorrect)
1. **File encoding corruption** → Ruled out by adding `read_file_with_encoding` with UTF-8/CP950/Latin-1 support
2. **Missing source files** → Ruled out by finding 47 `.A51` files in Lab 5
3. **`.txt` files being ignored** → Partially correct, but not the root cause

### 4.2 Breakthrough
Created `debug_pair.py` to test a specific pair (`E94124052` vs `E94126282`):
```python
# Both students have .A51 files
file1 = r"...\E94124052_...\5-2.A51"
file2 = r"...\E94126282_...\EX1.A51"

# Explicitly passed lowercase extension to clean_code
cleaned1 = clean_code(content1, '.a51')  # ← Forced lowercase
cleaned2 = clean_code(content2, '.a51')

# Result: {'token_seq': 1.0, 'levenshtein': 1.0}  ✓ Works!
```

This proved the files were valid and the similarity algorithm worked. The bug was in the extension check.

## 5. Fix

### 5.1 Code Change
```diff
# src/main.py - Line 92
- ext = os.path.splitext(src_file)[1]
+ ext = os.path.splitext(src_file)[1].lower()  # Lowercase for case-insensitive comparison
```

### 5.2 Verification
After the fix, tested the same pair:
```
File 1: E94124052_...\5-2.A51
File 2: E94126282_...\EX1.A51
Similarity: {'token_seq': 1.0, 'levenshtein': 1.0}  ✓
```

## 6. Related Issues Fixed

### 6.1 `max_score` KeyError Crash
**Symptom:** `KeyError: 'max_score'` when `FILTER_MODE=threshold` and LLM analysis fails  
**Cause:** Fallback logic referenced non-existent `comp['max_score']`  
**Fix:** Changed to `comp['avg_score']`

```diff
# src/main.py - Line 293
- verdict = "抄襲" if comp['max_score'] > 0.85 else "未抄襲"
+ verdict = "抄襲" if comp['avg_score'] > 0.85 else "未抄襲"
```

### 6.2 File Encoding Robustness
Added `read_file_with_encoding` function to try multiple encodings:
```python
def read_file_with_encoding(file_path):
    encodings = ['utf-8', 'cp950', 'latin-1']
    for enc in encodings:
        try:
            with open(file_path, 'r', encoding=enc) as f:
                return f.read()
        except UnicodeDecodeError:
            continue
    return ""
```

## 7. Lessons Learned

### 7.1 Platform Differences
- Windows file systems are case-insensitive (`.A51` and `.a51` refer to the same file)
- Python string comparisons are case-sensitive (`.A51` != `.a51`)
- Always normalize case when comparing file extensions

### 7.2 Consistency is Critical
- `preprocessor.py` lowercased extensions → files were found
- `main.py` didn't lowercase → files were skipped
- **Lesson:** Ensure consistent handling across modules

### 7.3 Debug Strategy
1. Test with known-good data (TestStudent worked)
2. Isolate the problem (created debug scripts)
3. Compare working vs. non-working cases (`.c` vs `.A51`)
4. Trace the data flow (crawl → process → compare)

## 8. Prevention Measures

### 8.1 Code Review Checklist
- [ ] File extension comparisons use `.lower()`
- [ ] Consistent encoding handling across modules
- [ ] Test with both uppercase and lowercase extensions

### 8.2 Test Coverage
Add test cases for:
- Uppercase extensions (`.A51`, `.ASM`, `.C`)
- Mixed case extensions (`.A51`, `.a51`)
- Files with no extension
- Non-ASCII filenames

### 8.3 Documentation
Update README to note:
- System is case-insensitive for file extensions
- Supported extensions: `.a51`, `.asm`, `.c` (case-insensitive)
- `.txt` files are treated as invalid submissions

## 9. Files Modified
- `src/main.py` - Added `.lower()` to extension check (Line 92)
- `src/main.py` - Fixed `max_score` → `avg_score` (Line 293)
- `src/main.py` - Added `read_file_with_encoding` function
- `src/preprocessor.py` - Reverted `.txt` support (per user request)

## 10. Verification Status
✅ **Resolved** - Verified with real student files showing correct similarity scores
