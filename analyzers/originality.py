
import re
from difflib import SequenceMatcher
from pathlib import Path


def normalize_c_code(source):
    """
    Remove comments and tokenize C code.

    Returns a list of tokens so operators such as + and -
    remain distinct during similarity comparison.
    """

    # Remove comments while preserving string and character literals.
    token_pattern = re.compile(
        r'"(?:\\.|[^"\\])*"'          # String literals
        r"|\'(?:\\.|[^\'\\])*\'"      # Character literals
        r"|/\*.*?\*/"                 # Block comments
        r"|//[^\r\n]*"                # Line comments
        r"|[A-Za-z_]\w*"              # Identifiers and keywords
        r"|\d+(?:\.\d+)?(?:[eE][+-]?\d+)?"
        r"|->|\+\+|--|==|!=|<=|>=|&&|\|\||<<|>>"
        r"|[^\s]",                    # Other operators and punctuation
        re.DOTALL,
    )

    tokens = []

    for match in token_pattern.finditer(source):
        token = match.group(0)

        # Ignore comments, but keep string and character literals.
        if token.startswith("/*") or token.startswith("//"):
            continue

        tokens.append(token)

    return tokens


def check_originality(source_file, comparison_files, threshold=0.85):
    """
    Compare a C submission against other C submissions.

    Similarity is a review signal, not proof of plagiarism.
    """

    source_path = Path(source_file)

    result = {
        "metric": "originality",
        "source_file": str(source_path),
        "score": None,
        "status": "NOT_EVALUATED",
        "comparisons": [],
        "findings": [],
    }

    if not 0 <= threshold <= 1:
        result["status"] = "ERROR"
        result["message"] = "Threshold must be between 0 and 1."
        return result

    if not source_path.is_file():
        result["status"] = "ERROR"
        result["message"] = f"Source file not found: {source_path}"
        return result

    try:
        source_text = source_path.read_text(
            encoding="utf-8",
            errors="replace",
        )
        source_code = normalize_c_code(source_text)
    except OSError as exc:
        result["status"] = "ERROR"
        result["message"] = f"Could not read source file: {exc}"
        return result

    if not source_code:
        result["status"] = "ERROR"
        result["message"] = "Source file contains no code tokens."
        return result

    if comparison_files is None:
        result["message"] = (
            "No comparison files supplied; originality cannot be assessed."
        )
        return result

    valid_comparisons = 0
    highest_similarity = 0.0

    for comparison_file in comparison_files:
        comparison_path = Path(comparison_file)

        if not comparison_path.is_file():
            result["findings"].append(
                f"Comparison file not found: {comparison_path}"
            )
            continue

        try:
            if comparison_path.resolve() == source_path.resolve():
                continue

            other_text = comparison_path.read_text(
                encoding="utf-8",
                errors="replace",
            )
            other_code = normalize_c_code(other_text)

        except OSError as exc:
            result["findings"].append(
                f"Could not read {comparison_path}: {exc}"
            )
            continue

        if not other_code:
            continue

        similarity = SequenceMatcher(
            None,
            source_code,
            other_code,
            autojunk=False,
        ).ratio()

        valid_comparisons += 1
        highest_similarity = max(highest_similarity, similarity)

        similarity_percent = round(similarity * 100, 2)

        result["comparisons"].append({
            "file": str(comparison_path),
            "similarity_percent": similarity_percent,
        })

        if similarity >= threshold:
            result["findings"].append({
                "file": str(comparison_path),
                "similarity_percent": similarity_percent,
                "message": (
                    "High code similarity; manual review recommended."
                ),
            })

    if valid_comparisons == 0:
        result["message"] = (
            "No valid comparison files were available."
        )
        return result

    # This is a preliminary similarity-based score, not proof
    # of the student's originality or plagiarism.
    result["score"] = round(
        (1 - highest_similarity) * 100,
        2,
    )
    result["highest_similarity_percent"] = round(
        highest_similarity * 100,
        2,
    )
    result["status"] = (
        "REVIEW"
        if highest_similarity >= threshold
        else "ASSESSED"
    )
    result["message"] = (
        "Token-based similarity estimate only; "
        "similarity does not prove plagiarism."
    )

    return result
