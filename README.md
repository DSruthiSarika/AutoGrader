# C AutoGrader

## Rule-Driven C Program Evaluation System

A rule-driven automated grading system for evaluating C programs using multiple static-analysis, dynamic-analysis, and behavioral metrics.

## Features

The AutoGrader evaluates C programs across 9 metrics:

1. **Correctness** – Runs predefined test cases and compares expected and actual output.
2. **Syntax** – Checks compilation and syntax-related issues.
3. **Structure** – Analyzes the overall program structure.
4. **Modularity** – Evaluates helper functions and function usage.
5. **Logical Behavior** – Tests configured edge cases and behavioral scenarios.
6. **Complexity** – Estimates algorithmic complexity using static analysis and runtime benchmarking where applicable.
7. **Memory Safety** – Uses AddressSanitizer (ASan) and UndefinedBehaviorSanitizer (UBSan).
8. **Readability** – Provides a heuristic readability assessment.
9. **Originality** – Provides a token-based code dissimilarity estimate.

Each metric contributes to the final weighted grade.

## Project Structure

```text
AUTOGRADER/
├── agent/
│   ├── compiler.py
│   └── execution.py
│
├── analyzers/
│   ├── correctness.py
│   ├── syntax.py
│   ├── structure.py
│   ├── modularity.py
│   ├── logical.py
│   ├── complexity.py
│   ├── memory_safety.py
│   ├── readability.py
│   └── originality.py
│
├── rules/
│   ├── problems/
│   └── rules.json
│
├── submissions/
│   └── *.c
│
├── tests/
│   ├── *_tests.json
│   └── test_*.py
│
├── reports/
├── app.py
├── main.py
├── requirements.txt
└── README.md
```

## Installation

### 1. Clone the repository

```bash
git clone <YOUR_GITHUB_REPOSITORY_URL>
cd AUTOGRADER
```

### 2. Install Python dependencies

```bash
python3 -m pip install -r requirements.txt
```

### 3. Install Docker

The AutoGrader uses Docker for isolated compilation and execution of C programs.

Make sure Docker is installed and running before evaluation.

## Running the AutoGrader

### Command-line interface

Evaluate a single C program:

```bash
python3 main.py submissions/bubble_sort.c
```

Evaluate all configured submissions:

```bash
python3 main.py --all
```

### Streamlit interface

Start the graphical interface:

```bash
python3 -m streamlit run app.py
```

Then open the local Streamlit URL shown in the terminal.

The interface allows the user to:

- Select a C submission
- Run the AutoGrader
- View evaluation results
- View detailed metric results
- Generate and download JSON and text reports

## Rule-Based Configuration

Each problem can have its own configuration under:

```text
rules/problems/
```

A problem configuration defines items such as:

- Problem name and description
- Correctness test file
- Logical behavior test cases
- Modularity requirements
- Complexity requirements
- Benchmark configuration

This allows different C problems to be evaluated using problem-specific rules.

## Testing

Run the project tests using:

```bash
pytest
```

or:

```bash
python3 -m pytest
```

## Reports

The AutoGrader generates:

```text
reports/grading_report.json
reports/grading_report.txt
```

The JSON report provides structured grading information, while the text report provides a human-readable evaluation summary.

## Supported Problems

The project currently includes configurations and test cases for problems such as:

- Addition
- Binary Search
- Bubble Sort
- Insertion Sort
- Linear Search
- Merge Sort
- Quick Sort
- Selection Sort

## Technologies Used

- Python
- C
- Streamlit
- Docker
- GCC
- pytest
- AddressSanitizer (ASan)
- UndefinedBehaviorSanitizer (UBSan)
- Static analysis
- Runtime benchmarking
- JSON-based rule configuration

## Evaluation Weights

| Metric | Weight |
|---|---:|
| Correctness | 20% |
| Syntax | 10% |
| Structure | 10% |
| Modularity | 10% |
| Logical Behavior | 10% |
| Complexity | 10% |
| Memory Safety | 10% |
| Readability | 10% |
| Originality | 10% |
| **Total** | **100%** |

## Notes

The originality metric is a token-based dissimilarity estimate and should not be interpreted as definitive proof of plagiarism or originality.

Complexity analysis is enabled only where the problem provides a meaningful scalable benchmark.

---

## Author

**Digumurthy Sruthi Sarika**

**Nithya R**

**Khushi Kumari**

**Shruti Verma**

