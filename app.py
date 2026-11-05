import streamlit as st
from pathlib import Path
import subprocess
import sys
import json


# ============================================================
# PATHS
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent
SUBMISSIONS_DIR = PROJECT_ROOT / "submissions"
REPORTS_DIR = PROJECT_ROOT / "reports"

MAIN_SCRIPT = PROJECT_ROOT / "main.py"

JSON_REPORT = REPORTS_DIR / "grading_report.json"
TEXT_REPORT = REPORTS_DIR / "grading_report.txt"


# ============================================================
# PAGE CONFIG
# ============================================================

st.set_page_config(
    page_title="C AutoGrader",
    page_icon="⚙️",
    layout="wide",
    initial_sidebar_state="expanded"
)


# ============================================================
# SESSION STATE
# ============================================================

if "result_output" not in st.session_state:
    st.session_state.result_output = None

if "selected_submission" not in st.session_state:
    st.session_state.selected_submission = None

if "evaluation_done" not in st.session_state:
    st.session_state.evaluation_done = False


# ============================================================
# CUSTOM CSS
# ============================================================

st.markdown(
    """
    <style>

    .main-title {
        font-size: 46px;
        font-weight: 800;
        margin-bottom: 5px;
    }

    .subtitle {
        font-size: 18px;
        color: #9ca3af;
        margin-bottom: 30px;
    }

    .metric-card {
        padding: 18px;
        border-radius: 12px;
        background-color: #171923;
        border: 1px solid #2a2d3a;
        text-align: center;
    }

    .metric-title {
        font-size: 14px;
        color: #9ca3af;
    }

    .metric-value {
        font-size: 28px;
        font-weight: 700;
    }

    </style>
    """,
    unsafe_allow_html=True
)


# ============================================================
# SIDEBAR
# ============================================================

st.sidebar.title("AutoGrader")

st.sidebar.subheader("Select Mode")

mode = st.sidebar.radio(
    "Mode",
    [
        "Evaluate Submission",
        "View Reports"
    ],
    label_visibility="collapsed"
)


# ============================================================
# GET C PROGRAMS
# ============================================================

def get_c_programs():
    if not SUBMISSIONS_DIR.exists():
        return []

    return sorted(
        [
            f.name
            for f in SUBMISSIONS_DIR.glob("*.c")
            if f.is_file()
        ]
    )


# ============================================================
# RUN AUTOGRADER
# ============================================================

def run_autograder(filename):

    source_path = SUBMISSIONS_DIR / filename

    if not source_path.exists():
        return f"ERROR: Submission file not found: {filename}"

    if not MAIN_SCRIPT.exists():
        return (
            "ERROR: main1.py was not found.\n\n"
            f"Expected location:\n{MAIN_SCRIPT}"
        )

    try:

        # Directly execute main1.py.
        # This avoids the "No module named main1" problem.
        result = subprocess.run(
            [
                sys.executable,
                str(MAIN_SCRIPT),
                str(source_path)
            ],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=300
        )

        output = result.stdout

        if result.stderr:
            output += "\n\n" + result.stderr

        return output

    except subprocess.TimeoutExpired:

        return (
            "AUTOGRADER TIMEOUT\n\n"
            "The evaluation exceeded the 5-minute execution limit."
        )

    except Exception as exc:

        return (
            "ERROR WHILE RUNNING AUTOGRADER:\n\n"
            f"{exc}"
        )


# ============================================================
# DISPLAY REPORT
# ============================================================

def display_report():

    if not JSON_REPORT.exists():
        st.warning("No grading report has been generated yet.")
        return

    try:

        with JSON_REPORT.open("r", encoding="utf-8") as f:
            report = json.load(f)

        submissions = report.get("submissions", {})

        if not submissions:
            st.warning("No submission data found in the report.")
            return

        # ----------------------------------------------------
        # SELECT SUBMISSION
        # ----------------------------------------------------

        filename = st.session_state.selected_submission

        if filename not in submissions:
            filename = list(submissions.keys())[-1]

        data = submissions[filename]

        grade = data.get("grade", {})
        final_score = grade.get("final_marks")

        if final_score is not None:
            score_text = f"{float(final_score):.2f}/100"
        else:
            score_text = "N/A"

        execution = data.get("execution", {})

        compiled = execution.get("compiled", False)
        smoke = execution.get("smoke_test_passed", False)

        # ====================================================
        # HEADER
        # ====================================================

        st.success("Evaluation completed")

        col1, col2, col3 = st.columns(3)

        with col1:

            st.markdown(
                f"""
                <div class="metric-card">
                    <div class="metric-title">Final Score</div>
                    <div class="metric-value">{score_text}</div>
                </div>
                """,
                unsafe_allow_html=True
            )

        with col2:

            st.markdown(
                f"""
                <div class="metric-card">
                    <div class="metric-title">Submission</div>
                    <div class="metric-value"
                         style="font-size:20px;">
                        {filename}
                    </div>
                </div>
                """,
                unsafe_allow_html=True
            )

        with col3:

            status = "PASS" if compiled and smoke else "REVIEW"

            st.markdown(
                f"""
                <div class="metric-card">
                    <div class="metric-title">Status</div>
                    <div class="metric-value">{status}</div>
                </div>
                """,
                unsafe_allow_html=True
            )

        st.divider()

        # ====================================================
        # METRICS
        # ====================================================

        st.subheader("Evaluation Results")

        metrics = data.get("metrics", {})

        metric_names = [
            "correctness",
            "syntax",
            "structure",
            "modularity",
            "logical_behavior",
            "complexity",
            "memory_safety",
            "readability",
            "originality"
        ]

        cols = st.columns(3)

        for index, metric in enumerate(metric_names):

            metric_data = metrics.get(metric, {})

            score = metric_data.get("score")

            if score is None:
                score_display = "N/A"
            else:
                score_display = f"{float(score):.2f}/100"

            status = metric_data.get("status", "UNKNOWN")

            with cols[index % 3]:

                metric_title = metric.replace(
                    "_", " "
                ).title()

                if status in (
                    "PASS",
                    "ASSESSED",
                    "NO_ISSUE_DETECTED",
                    "AGREEMENT"
                ):

                    st.success(
                        f"**{metric_title}**\n\n"
                        f"{score_display}"
                    )

                elif status in (
                    "FAIL",
                    "REVIEW"
                ):

                    st.warning(
                        f"**{metric_title}**\n\n"
                        f"{score_display}"
                    )

                else:

                    st.info(
                        f"**{metric_title}**\n\n"
                        f"{score_display}"
                    )

        # ====================================================
        # DETAILED EVALUATION
        # ====================================================

        if st.session_state.result_output:

            st.divider()

            st.subheader("Detailed Evaluation")

            # Output stays inside Streamlit.
            # It does not open a text file.
            st.code(
                st.session_state.result_output,
                language="text"
            )

        # ====================================================
        # REPORT GENERATION
        # ====================================================

        st.divider()

        st.subheader("Report Generation")

        st.success("Reports generated successfully.")

        download_col1, download_col2 = st.columns(2)

        # ----------------------------------------------------
        # JSON DOWNLOAD
        # ----------------------------------------------------

        if JSON_REPORT.exists():

            with JSON_REPORT.open("rb") as f:
                json_data = f.read()

            with download_col1:

                st.download_button(
                    label="⬇️ Download JSON Report",
                    data=json_data,
                    file_name="grading_report.json",
                    mime="application/json",
                    use_container_width=True
                )

        # ----------------------------------------------------
        # TEXT DOWNLOAD
        # ----------------------------------------------------

        if TEXT_REPORT.exists():

            with TEXT_REPORT.open("rb") as f:
                text_data = f.read()

            with download_col2:

                st.download_button(
                    label="⬇️ Download Text Report",
                    data=text_data,
                    file_name="grading_report.txt",
                    mime="text/plain",
                    use_container_width=True
                )

    except Exception as exc:

        st.error(
            f"Could not display report: {exc}"
        )


# ============================================================
# EVALUATE SUBMISSION
# ============================================================

if mode == "Evaluate Submission":

    st.markdown(
        '<div class="main-title">🔍 C AutoGrader</div>',
        unsafe_allow_html=True
    )

    st.markdown(
        '<div class="subtitle">'
        'Rule-Driven C Program Evaluation System'
        '</div>',
        unsafe_allow_html=True
    )

    programs = get_c_programs()

    if not programs:

        st.error(
            "No C programs found in the submissions folder."
        )

    else:

        selected = st.sidebar.selectbox(
            "Select C Program",
            programs
        )

        st.session_state.selected_submission = selected

        if st.sidebar.button(
            "🚀 Run AutoGrader",
            use_container_width=True
        ):

            with st.spinner("Running AutoGrader..."):

                output = run_autograder(selected)

                st.session_state.result_output = output
                st.session_state.evaluation_done = True

        # ----------------------------------------------------
        # AFTER EVALUATION
        # ----------------------------------------------------

        if st.session_state.evaluation_done:

            display_report()

        else:

            st.info(
                "Select a C program from the sidebar and click "
                "**🚀 Run AutoGrader** to begin evaluation."
            )


# ============================================================
# VIEW REPORTS
# ============================================================

else:

    st.markdown(
        '<div class="main-title">📊 Grading Reports</div>',
        unsafe_allow_html=True
    )

    st.markdown(
        '<div class="subtitle">'
        'View previously generated AutoGrader reports'
        '</div>',
        unsafe_allow_html=True
    )

    if JSON_REPORT.exists():

        try:

            with JSON_REPORT.open(
                "r",
                encoding="utf-8"
            ) as f:

                report = json.load(f)

            submissions = report.get(
                "submissions",
                {}
            )

            if submissions:

                report_files = list(
                    submissions.keys()
                )

                selected_report = st.selectbox(
                    "Select Submission",
                    report_files
                )

                st.session_state.selected_submission = (
                    selected_report
                )

                selected_data = submissions[
                    selected_report
                ]

                grade = selected_data.get(
                    "grade",
                    {}
                )

                score = grade.get(
                    "final_marks"
                )

                if score is not None:

                    st.success(
                        f"{selected_report} — "
                        f"Final Score: "
                        f"{float(score):.2f}/100"
                    )

                # Display the saved report
                display_report()

            else:

                st.warning(
                    "No submissions found in the report."
                )

        except Exception as exc:

            st.error(
                f"Could not read grading report: {exc}"
            )

    else:

        st.info(
            "No report available yet. "
            "Run the AutoGrader first."
        )