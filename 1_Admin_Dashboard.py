# 1_Admin_Dashboard.py (FIXED: Latest tests now appear first)

import streamlit as st

st.set_page_config(page_title="Admin Dashboard", layout="centered")

st.title("👨‍💼 Admin Dashboard")

# --- Initialize Session State ---
if "students" not in st.session_state:
    st.session_state.students = [
        {"id": "s001", "name": "Alice Smith"},
        {"id": "s002", "name": "Bob Johnson"},
    ]
if "tests" not in st.session_state:
    st.session_state.tests = []
if "submissions" not in st.session_state:
    st.session_state.submissions = {}

# --- UI: Create New Student ---
with st.expander("➕ Create New Student"):
    with st.form("new_student_form", clear_on_submit=True):
        student_name = st.text_input("Student Name")
        submitted = st.form_submit_button("Add Student")
        if submitted and student_name:
            new_id = f"s{len(st.session_state.students) + 1:03d}"
            st.session_state.students.append({"id": new_id, "name": student_name})
            st.success(f"Added student: {student_name}")

st.divider()

# --- UI: Display All Students and Their Results ---
st.header("All Students and Their Scores")

if not st.session_state.students:
    st.warning("No students found. Please add a student to begin.")
else:
    for student in st.session_state.students:
        st.subheader(student['name'])

        student_submissions = []
        for key, submission in st.session_state.submissions.items():
            if key.endswith(student['id']):
                student_id_suffix = f"_{student['id']}"
                test_id = key.removeprefix("test_").removesuffix(student_id_suffix)
                
                test_title = "Unknown Test"
                # **FIX 1: Make sure to get the date for sorting**
                test_date = "1970-01-01" # Default date for sorting if test is somehow not found
                for t in st.session_state.tests:
                    if t['id'] == test_id:
                        test_title = t['title']
                        test_date = t['date']
                        break
                
                student_submissions.append({
                    "test_title": test_title,
                    "date": test_date,
                    "score": submission.get('total_score', 'N/A'),
                    "details": submission
                })

        if not student_submissions:
            st.caption("No results recorded for this student yet.")
        else:
            # --- FIX 2: SORT THE LIST BY DATE (LATEST FIRST) BEFORE DISPLAYING ---
            student_submissions.sort(key=lambda x: x['date'], reverse=True)
            # --- END OF FIX ---

            with st.container(border=True):
                for sub in student_submissions:
                    col1, col2 = st.columns([3, 1])
                    col1.write(f"**Test:** {sub['test_title']}")
                    
                    if 'error' in sub['details']:
                         col2.warning("Error")
                    elif sub['score'] != 'N/A':
                        col2.metric(label="Score", value=f"{sub['score']}/100")
                    
                    with st.popover("View Full Analysis"):
                        details = sub.get('details', {})
                        st.subheader("Detailed Analysis")
                        st.markdown("**Overall Remarks**")
                        st.info(details.get('overall_remarks', 'No summary provided.'))

                        st.markdown("**Question-by-Question Breakdown**")
                        question_analysis = details.get('question_analysis', [])
                        if question_analysis:
                            for qa in question_analysis:
                                with st.container(border=True):
                                    q_col1, q_col2 = st.columns([3,1])
                                    q_col1.write(f"**Question {qa.get('question_number', 'N/A')}**")
                                    q_col2.metric("Score", f"{qa.get('score', 0)}/{qa.get('max_score', 0)}")
                                    st.write(f"_{qa.get('feedback', 'No feedback available.')}_")
                        else:
                            st.caption("No question-specific analysis was generated.")

                        st.markdown("**Performance by Concept**")
                        rubric_analysis = details.get('rubric_analysis', [])
                        if rubric_analysis:
                            for ra in rubric_analysis:
                                with st.container(border=True):
                                    r_col1, r_col2 = st.columns([2,1])
                                    r_col1.write(f"**Concept:** {ra.get('concept', 'N/A')}")
                                    r_col2.write(f"**Performance:** {ra.get('performance', 'N/A')}")
                                    st.markdown(f"**Evidence:** {ra.get('evidence', 'No evidence provided.')}")
                        else:
                             st.caption("No rubric-based analysis was generated.")