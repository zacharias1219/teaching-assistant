# 2_Start_Grading.py (FIXED: Text wrapping for remarks)

import streamlit as st
import fitz
import json
import openai
from PIL import Image
import io
import re
import math
import pytesseract
import os
from datetime import datetime
import toml

st.set_page_config(page_title="Start Grading", layout="wide")

# Initialize session state for prompts
if "grading_prompt" not in st.session_state:
    st.session_state.grading_prompt = """You are an expert mathematics professor grading multiple questions. Analyze the student's work for ALL questions below.

**QUESTIONS TO GRADE:**
{questions_text}

**GRADING CRITERIA:**
- **IGNORE crossed-out content** - only grade final, uncrossed work
- **Check completion** - penalize incomplete solutions (e.g., "100x-50x" without "=50x")
- **EXCELLENT (90-100%)**: Complete, correct, proper notation, clear reasoning
- **GOOD (70-89%)**: Mostly correct, minor errors, nearly complete
- **FAIR (50-69%)**: Partial understanding, significant errors, incomplete
- **POOR (20-49%)**: Major errors, wrong approach, abandoned work
- **NOT ATTEMPTED (0%)**: No relevant work

**TASK:** Grade each question by finding the relevant work in the images and evaluating according to the criteria above.

**REQUIRED JSON OUTPUT:**
{{
    "question_analysis": [
        {{
            "question_number": <question_number>,
            "status": "<'Excellent'|'Good'|'Fair'|'Poor'|'Not Attempted'>",
            "score": <integer between 0 and max_score>,
            "max_score": <max_score>,
            "feedback": "<brief feedback covering: strengths, errors, completion status, and improvement suggestions>",
            "extracted_work": "<description of work found for this question>",
            "mathematical_quality": "<assessment of rigor and notation>",
            "completion_status": "<'Complete'|'Nearly Complete'|'Partially Complete'|'Incomplete'|'Abandoned'>"
        }}
    ]
}}"""

if "summary_prompt" not in st.session_state:
    st.session_state.summary_prompt = """You are a senior mathematics education specialist with expertise in curriculum development and student assessment. You are creating a comprehensive academic evaluation report for a student's mathematical performance.

**STUDENT'S DETAILED TEST RESULTS:**
{full_analysis}

**CURRICULUM STANDARDS & RUBRIC:**
"{rubric}"

**ACADEMIC EVALUATION REQUIREMENTS:**

**1. OVERALL PERFORMANCE ASSESSMENT:**
Create a comprehensive academic summary (3-4 sentences) that includes:
- **Performance Level**: Overall grade/performance classification
- **Academic Strengths**: Specific mathematical competencies demonstrated
- **Learning Gaps**: Identified areas of conceptual weakness
- **Growth Indicators**: Evidence of mathematical thinking development
- **Strategic Recommendations**: Specific, actionable study and practice suggestions

**2. CONCEPTUAL MASTERY ANALYSIS:**
For each core mathematical concept, provide:
- **Concept Identification**: Clear definition of the mathematical concept
- **Performance Assessment**: Detailed evaluation of understanding level
- **Evidence-Based Analysis**: Specific examples from student work
- **Learning Progression**: Where the student stands in concept mastery
- **Next Steps**: Specific recommendations for concept development

**3. MATHEMATICAL THINKING EVALUATION:**
Assess the student's mathematical reasoning abilities:
- **Problem-Solving Approach**: How they tackle mathematical challenges
- **Logical Reasoning**: Quality of mathematical argumentation
- **Notational Proficiency**: Command of mathematical language
- **Computational Accuracy**: Precision in calculations
- **Conceptual Connections**: Ability to link related mathematical ideas

**4. EDUCATIONAL RECOMMENDATIONS:**
Provide specific, actionable guidance for:
- **Immediate Focus Areas**: What to study next
- **Practice Strategies**: How to improve specific skills
- **Concept Reinforcement**: Ways to strengthen understanding
- **Advanced Preparation**: Preparation for next level mathematics

**REQUIRED JSON OUTPUT:**
{{
    "overall_remarks": "<comprehensive academic summary covering performance level, strengths, gaps, and strategic recommendations>",
    "rubric_analysis": [
        {{
            "concept": "<specific mathematical concept from rubric>",
            "performance": "<'Mastery'|'Proficient'|'Developing'|'Emerging'|'Not Demonstrated'>",
            "evidence": "<detailed evidence from student work with specific examples and mathematical reasoning>",
            "recommendations": "<specific, actionable recommendations for this concept>"
        }}
    ],
    "mathematical_thinking": "<assessment of problem-solving approach, logical reasoning, and mathematical communication>",
    "learning_recommendations": "<comprehensive study and practice recommendations for continued mathematical development>"
}}"""

if "ocr_prompt" not in st.session_state:
    st.session_state.ocr_prompt = """Extract all text from this image and convert it to human-readable format.

IMPORTANT FORMATTING RULES:
1. Convert all mathematical notation to readable text:
   - Fractions: Write as "numerator/denominator" (e.g., "dy/dx" not "\\frac{dy}{dx}")
   - Square roots: Write as "sqrt(expression)" (e.g., "sqrt(1-x^2)" not "\\sqrt{1-x^2}")
   - Powers: Write as "base^exponent" (e.g., "x^2" not "x^{2}")
   - Logarithms: Write as "log(expression)" (e.g., "log(x)" not "\\log(x)")
   - Trigonometric functions: Write as "sin(x)", "cos(x)", "tan(x)" etc.
   - Greek letters: Write as "alpha", "beta", "theta", "pi" etc.

2. Make the text flow naturally and be easy to read
3. Preserve the mathematical meaning but in plain text format
4. Use standard keyboard symbols instead of LaTeX notation

Return only the converted text content, no explanations."""

# Sidebar for prompt editing
with st.sidebar:
    st.header("⚙️ System Prompts Configuration")
    st.info("Edit these prompts to customize the AI's behavior. Changes take effect immediately.")
    
    # Grading prompt editor
    st.subheader("📝 Grading Prompt")
    st.caption("Controls how the AI grades individual questions")
    new_grading_prompt = st.text_area(
        "Grading System Prompt",
        value=st.session_state.grading_prompt,
        height=400,
        help="This prompt controls the AI's grading behavior for individual questions"
    )
    if new_grading_prompt != st.session_state.grading_prompt:
        st.session_state.grading_prompt = new_grading_prompt
        st.success("✅ Grading prompt updated!")
    
    # Summary prompt editor
    st.subheader("📊 Summary Prompt")
    st.caption("Controls how the AI generates overall summaries")
    new_summary_prompt = st.text_area(
        "Summary System Prompt",
        value=st.session_state.summary_prompt,
        height=300,
        help="This prompt controls the AI's summary generation behavior"
    )
    if new_summary_prompt != st.session_state.summary_prompt:
        st.session_state.summary_prompt = new_summary_prompt
        st.success("✅ Summary prompt updated!")
    
    # OCR prompt editor
    st.subheader("🔍 OCR Prompt")
    st.caption("Controls how the AI extracts text from images")
    new_ocr_prompt = st.text_area(
        "OCR System Prompt",
        value=st.session_state.ocr_prompt,
        height=200,
        help="This prompt controls how the AI converts mathematical notation to readable text"
    )
    if new_ocr_prompt != st.session_state.ocr_prompt:
        st.session_state.ocr_prompt = new_ocr_prompt
        st.success("✅ OCR prompt updated!")
    
    # Debug mode toggle
    st.divider()
    st.subheader("🔧 Debug Options")
    debug_mode = st.checkbox("Show Debug Information", value=st.session_state.get('debug_mode', False))
    if debug_mode != st.session_state.get('debug_mode', False):
        st.session_state.debug_mode = debug_mode
        st.success("✅ Debug mode updated!")
    
    # Reset buttons
    st.divider()
    if st.button("🔄 Reset All Prompts to Default"):
        st.session_state.grading_prompt = """You are an expert mathematics professor grading multiple questions. Analyze the student's work for ALL questions below.

**QUESTIONS TO GRADE:**
{questions_text}

**GRADING CRITERIA:**
- **IGNORE crossed-out content** - only grade final, uncrossed work
- **Check completion** - penalize incomplete solutions (e.g., "100x-50x" without "=50x")
- **EXCELLENT (90-100%)**: Complete, correct, proper notation, clear reasoning
- **GOOD (70-89%)**: Mostly correct, minor errors, nearly complete
- **FAIR (50-69%)**: Partial understanding, significant errors, incomplete
- **POOR (20-49%)**: Major errors, wrong approach, abandoned work
- **NOT ATTEMPTED (0%)**: No relevant work

**TASK:** Grade each question by finding the relevant work in the images and evaluating according to the criteria above.

**REQUIRED JSON OUTPUT:**
{{
    "question_analysis": [
        {{
            "question_number": <question_number>,
            "status": "<'Excellent'|'Good'|'Fair'|'Poor'|'Not Attempted'>",
            "score": <integer between 0 and max_score>,
            "max_score": <max_score>,
            "feedback": "<brief feedback covering: strengths, errors, completion status, and improvement suggestions>",
            "extracted_work": "<description of work found for this question>",
            "mathematical_quality": "<assessment of rigor and notation>",
            "completion_status": "<'Complete'|'Nearly Complete'|'Partially Complete'|'Incomplete'|'Abandoned'>"
        }}
    ]
}}"""
        st.session_state.summary_prompt = """You are a senior mathematics education specialist with expertise in curriculum development and student assessment. You are creating a comprehensive academic evaluation report for a student's mathematical performance.

**STUDENT'S DETAILED TEST RESULTS:**
{full_analysis}

**CURRICULUM STANDARDS & RUBRIC:**
"{rubric}"

**ACADEMIC EVALUATION REQUIREMENTS:**

**1. OVERALL PERFORMANCE ASSESSMENT:**
Create a comprehensive academic summary (3-4 sentences) that includes:
- **Performance Level**: Overall grade/performance classification
- **Academic Strengths**: Specific mathematical competencies demonstrated
- **Learning Gaps**: Identified areas of conceptual weakness
- **Growth Indicators**: Evidence of mathematical thinking development
- **Strategic Recommendations**: Specific, actionable study and practice suggestions

**2. CONCEPTUAL MASTERY ANALYSIS:**
For each core mathematical concept, provide:
- **Concept Identification**: Clear definition of the mathematical concept
- **Performance Assessment**: Detailed evaluation of understanding level
- **Evidence-Based Analysis**: Specific examples from student work
- **Learning Progression**: Where the student stands in concept mastery
- **Next Steps**: Specific recommendations for concept development

**3. MATHEMATICAL THINKING EVALUATION:**
Assess the student's mathematical reasoning abilities:
- **Problem-Solving Approach**: How they tackle mathematical challenges
- **Logical Reasoning**: Quality of mathematical argumentation
- **Notational Proficiency**: Command of mathematical language
- **Computational Accuracy**: Precision in calculations
- **Conceptual Connections**: Ability to link related mathematical ideas

**4. EDUCATIONAL RECOMMENDATIONS:**
Provide specific, actionable guidance for:
- **Immediate Focus Areas**: What to study next
- **Practice Strategies**: How to improve specific skills
- **Concept Reinforcement**: Ways to strengthen understanding
- **Advanced Preparation**: Preparation for next level mathematics

**REQUIRED JSON OUTPUT:**
{{
    "overall_remarks": "<comprehensive academic summary covering performance level, strengths, gaps, and strategic recommendations>",
    "rubric_analysis": [
        {{
            "concept": "<specific mathematical concept from rubric>",
            "performance": "<'Mastery'|'Proficient'|'Developing'|'Emerging'|'Not Demonstrated'>",
            "evidence": "<detailed evidence from student work with specific examples and mathematical reasoning>",
            "recommendations": "<specific, actionable recommendations for this concept>"
        }}
    ],
    "mathematical_thinking": "<assessment of problem-solving approach, logical reasoning, and mathematical communication>",
    "learning_recommendations": "<comprehensive study and practice recommendations for continued mathematical development>"
}}"""
        st.session_state.ocr_prompt = """Extract all text from this image and convert it to human-readable format.

IMPORTANT FORMATTING RULES:
1. Convert all mathematical notation to readable text:
   - Fractions: Write as "numerator/denominator" (e.g., "dy/dx" not "\\frac{dy}{dx}")
   - Square roots: Write as "sqrt(expression)" (e.g., "sqrt(1-x^2)" not "\\sqrt{1-x^2}")
   - Powers: Write as "base^exponent" (e.g., "x^2" not "x^{2}")
   - Logarithms: Write as "log(expression)" (e.g., "log(x)" not "\\log(x)")
   - Trigonometric functions: Write as "sin(x)", "cos(x)", "tan(x)" etc.
   - Greek letters: Write as "alpha", "beta", "theta", "pi" etc.

2. Make the text flow naturally and be easy to read
3. Preserve the mathematical meaning but in plain text format
4. Use standard keyboard symbols instead of LaTeX notation

Return only the converted text content, no explanations."""
        st.success("✅ All prompts reset to default!")
    
    # View saved reports section
    st.divider()
    st.subheader("📁 Saved Reports")
    st.caption("View and download previously saved grading reports")
    
    if os.path.exists("grading_reports"):
        report_files = [f for f in os.listdir("grading_reports") if f.endswith('.json')]
        if report_files:
            selected_report = st.selectbox(
                "Select a report to view:",
                report_files,
                help="Choose a previously saved grading report"
            )
            
            if selected_report:
                try:
                    with open(f"grading_reports/{selected_report}", 'r', encoding='utf-8') as f:
                        report_data = json.load(f)
                    
                    st.json(report_data)
                    
                    # Download button for selected report
                    with open(f"grading_reports/{selected_report}", 'r', encoding='utf-8') as f:
                        file_content = f.read()
                    
                    st.download_button(
                        label="📥 Download This Report",
                        data=file_content,
                        file_name=selected_report,
                        mime="application/json"
                    )
                except Exception as e:
                    st.error(f"Error loading report: {e}")
        else:
            st.info("No saved reports found.")
    else:
        st.info("No reports directory found.")

st.title("💯 Start Grading (Professional Engine)")
st.info("This version uses a multi-step, 'Divide & Conquer' process for maximum accuracy and consistency.")

st.info("🔍 **GPT-4o OCR Enabled:** This app now uses GPT-4o's built-in OCR capabilities to extract text from images. No additional software installation required!")

# Load configuration from TOML file
try:
    config = toml.load("config.toml")
    OPENAI_API_KEY = config["openai"]["api_key"]
except (FileNotFoundError, KeyError):
    st.error("🚨 config.toml file not found or missing OpenAI API key! Please create config.toml with your OpenAI API key.")
    st.stop()


# --- Initialize Session State ---
if "tests" not in st.session_state:
    st.session_state.tests = []
if "students" not in st.session_state:
    st.session_state.students = []
if "submissions" not in st.session_state:
    st.session_state.submissions = {}


# --- Helper and AI Functions (Unchanged) ---
def extract_text_from_pdf(file):
    try:
        doc = fitz.open(stream=file.read(), filetype="pdf")
        text = "".join(page.get_text() for page in doc)
        doc.close()
        return text
    except Exception as e:
        st.error(f"Error reading text PDF: {e}")
        return None

def convert_pdf_to_images(file):
    images = []
    try:
        doc = fitz.open(stream=file.read(), filetype="pdf")
        for page in doc:
            pix = page.get_pixmap(dpi=150)
            img_bytes = pix.tobytes("png")
            image = Image.open(io.BytesIO(img_bytes))
            images.append(image)
        doc.close()
        return images
    except Exception as e:
        st.error(f"Error converting PDF to images: {e}")
        return []

def extract_text_from_image(image):
    """Extract text from image using GPT-4o OCR with human-readable formatting"""
    try:
        # Convert image to base64 for OpenAI API
        import base64
        img_buffer = io.BytesIO()
        image.save(img_buffer, format='PNG')
        img_str = base64.b64encode(img_buffer.getvalue()).decode()
        
        from openai import OpenAI
        client = OpenAI(api_key=OPENAI_API_KEY)
        
        # Use the session state OCR prompt
        ocr_prompt = st.session_state.ocr_prompt
        
        # Debug: Show the actual OCR prompt being used (optional)
        if st.session_state.get('debug_mode', False):
            st.subheader("🔍 Debug: OCR Prompt Being Used")
            st.text_area("OCR Prompt", ocr_prompt, height=150, disabled=True)
        
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "user", "content": [
                    {"type": "text", "text": ocr_prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_str}"}}
                ]}
            ],
            temperature=0.0
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"GPT-4o OCR failed: {str(e)}"

def save_extracted_content(test_title, student_name, question_text, rubric, answer_images, question_analysis, final_score):
    """Save all extracted content to a comprehensive file"""
    try:
        # Create reports directory if it doesn't exist
        os.makedirs("grading_reports", exist_ok=True)
        
        # Generate filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"grading_reports/{test_title}_{student_name}_{timestamp}.json"
        
        # Extract text from all answer images
        extracted_answers = []
        for i, img in enumerate(answer_images):
            extracted_text = extract_text_from_image(img)
            extracted_answers.append({
                "image_number": i + 1,
                "extracted_text": extracted_text,
                "character_count": len(extracted_text) if extracted_text else 0
            })
        
        # Create comprehensive report
        report_data = {
            "metadata": {
                "test_title": test_title,
                "student_name": student_name,
                "grading_date": datetime.now().isoformat(),
                "total_score": final_score,
                "total_questions": len(question_analysis)
            },
            "question_paper": {
                "extracted_text": question_text,
                "character_count": len(question_text) if question_text else 0
            },
            "rubric": {
                "extracted_text": rubric,
                "character_count": len(rubric) if rubric else 0
            },
            "answer_scripts": {
                "total_images": len(answer_images),
                "extracted_content": extracted_answers
            },
            "grading_results": {
                "question_analysis": question_analysis,
                "summary": {
                    "overall_remarks": question_analysis[0].get('overall_remarks', 'No summary available') if question_analysis else 'No summary available',
                    "rubric_analysis": question_analysis[0].get('rubric_analysis', []) if question_analysis else [],
                    "mathematical_thinking": question_analysis[0].get('mathematical_thinking', 'No analysis available') if question_analysis else 'No analysis available',
                    "learning_recommendations": question_analysis[0].get('learning_recommendations', 'No recommendations available') if question_analysis else 'No recommendations available'
                }
            }
        }
        
        # Save to JSON file
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(report_data, f, indent=2, ensure_ascii=False)
        
        return filename
    except Exception as e:
        st.error(f"Error saving extracted content: {e}")
        return None

def process_uploaded_files(uploaded_files):
    """Process uploaded files (PDFs and images) and return a list of PIL Images"""
    images = []
    
    for uploaded_file in uploaded_files:
        try:
            file_type = uploaded_file.type.lower()
            
            if file_type == "application/pdf":
                # Handle PDF files
                pdf_images = convert_pdf_to_images(uploaded_file)
                images.extend(pdf_images)
            elif file_type.startswith("image/"):
                # Handle image files (jpg, png, jpeg, etc.)
                image = Image.open(uploaded_file)
                images.append(image)
            else:
                st.warning(f"Unsupported file type: {file_type}. Please upload PDF or image files.")
                
        except Exception as e:
            st.error(f"Error processing file {uploaded_file.name}: {e}")
    
    return images

def _grade_all_questions_with_gpt4o(questions, answer_images):
    # Create a concise questions list
    questions_text = ""
    for i, q in enumerate(questions):
        q_num, q_text, q_max_score = int(q[0]), q[1].strip(), int(q[2])
        # Truncate long question text to keep prompt manageable
        truncated_text = q_text[:200] + "..." if len(q_text) > 200 else q_text
        questions_text += f"Q{q_num} ({q_max_score}pts): {truncated_text}\n"
    
    # Use the session state prompt with the questions text
    prompt = st.session_state.grading_prompt.format(questions_text=questions_text)
    
    # Debug: Show the actual prompt being used (optional)
    if st.session_state.get('debug_mode', False):
        st.subheader("🔍 Debug: Grading Prompt Being Used")
        st.text_area("Grading Prompt", prompt, height=300, disabled=True)
    
    try:
        # Convert images to base64 for OpenAI API
        import base64
        image_contents = []
        for img in answer_images:
            img_buffer = io.BytesIO()
            img.save(img_buffer, format='PNG')
            img_str = base64.b64encode(img_buffer.getvalue()).decode()
            image_contents.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/png;base64,{img_str}"
                }
            })
        
        from openai import OpenAI
        client = OpenAI(api_key=OPENAI_API_KEY)
        
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "user", "content": [
                    {"type": "text", "text": prompt},
                    *image_contents
                ]}
            ],
            temperature=0.0,
            response_format={"type": "json_object"}
        )
        result = json.loads(response.choices[0].message.content)
        return result.get("question_analysis", [])
    except Exception as e:
        # Return error results for all questions
        error_results = []
        for q in questions:
            q_num, q_text, q_max_score = int(q[0]), q[1].strip(), int(q[2])
            error_results.append({
                "question_number": q_num, 
                "status": "Error", 
                "score": 0, 
                "max_score": q_max_score, 
                "feedback": f"API error: {e}"
            })
        return error_results

def _generate_summary_with_gpt4o(full_analysis, rubric):
    # Use the session state summary prompt
    prompt = st.session_state.summary_prompt.format(
        full_analysis=json.dumps(full_analysis, indent=2),
        rubric=rubric
    )
    
    # Debug: Show the actual summary prompt being used (optional)
    if st.session_state.get('debug_mode', False):
        st.subheader("🔍 Debug: Summary Prompt Being Used")
        st.text_area("Summary Prompt", prompt, height=200, disabled=True)
    try:
        from openai import OpenAI
        client = OpenAI(api_key=OPENAI_API_KEY)
        
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "user", "content": prompt}
            ],
            temperature=0.2,
            response_format={"type": "json_object"}
        )
        return json.loads(response.choices[0].message.content)
    except Exception:
        return {"overall_remarks": "Summary generation failed.", "rubric_analysis": []}

def grade_handwritten_submission_with_gpt4o(question_text, answer_images, rubric, test_title, progress_bar):
    questions = re.findall(r'(\d+)[).]\s(.*?)(?:\[(\d+)\])', question_text, re.DOTALL)
    if not questions:
        st.error("Could not parse questions from the question paper.")
        return {"error": "Failed to parse questions."}
    
    # Display parsing results
    st.subheader("🔍 Question Parsing Results:")
    st.info(f"✅ Successfully parsed {len(questions)} questions from question paper")
    
    with st.expander("📋 Parsed Questions", expanded=False):
        for i, q in enumerate(questions):
            q_num, q_text, q_max_score = int(q[0]), q[1].strip(), int(q[2])
            st.write(f"**Question {q_num}** (Max Score: {q_max_score})")
            st.text_area(f"Question {q_num} Text", q_text, height=80, disabled=True)
            st.divider()
    
    # Show all prompts in debug mode
    if st.session_state.get('debug_mode', False):
        st.subheader("🔍 Debug: All System Prompts")
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.markdown("**📝 Grading Prompt:**")
            st.text_area("Grading", st.session_state.grading_prompt, height=200, disabled=True)
        
        with col2:
            st.markdown("**📊 Summary Prompt:**")
            st.text_area("Summary", st.session_state.summary_prompt, height=200, disabled=True)
        
        with col3:
            st.markdown("**🔍 OCR Prompt:**")
            st.text_area("OCR", st.session_state.ocr_prompt, height=200, disabled=True)
    
    # Grade all questions at once
    progress_bar.progress(0.3, text="Preparing comprehensive analysis...")
    question_analysis = _grade_all_questions_with_gpt4o(questions, answer_images)
    
    # Calculate final scores
    total_raw_score = sum(q.get('score', 0) for q in question_analysis)
    total_possible_score = sum(q.get('max_score', 0) for q in question_analysis)
    final_percentage = math.ceil((total_raw_score / total_possible_score) * 100) if total_possible_score > 0 else 0
    final_analysis = {"total_score": final_percentage, "question_analysis": question_analysis}

    progress_bar.progress(0.8, text="Generating comprehensive analysis...")
    summary_data = _generate_summary_with_gpt4o(final_analysis, rubric)
    final_analysis.update(summary_data)
    
    # Save extracted content to file
    progress_bar.progress(0.9, text="Saving extracted content...")
    saved_file = save_extracted_content(
        test_title=test_title,
        student_name="Student",  # This will be updated when we have student info
        question_text=question_text,
        rubric=rubric,
        answer_images=answer_images,
        question_analysis=question_analysis,
        final_score=final_percentage
    )
    
    if saved_file:
        final_analysis["saved_file"] = saved_file
    
    progress_bar.progress(1.0, text="Grading completed!")
    return final_analysis

# --- UI Sections ---
with st.expander("➕ Add a New Test", expanded=True):
    with st.form("new_test_form", clear_on_submit=True):
        st.write("Define the test details, rubric, and upload the question paper.")
        test_title = st.text_input("Test Title", "Differentiation Test 2")
        test_date = st.date_input("Test Date")
        rubric_option = st.radio("Rubric Source:", ("Enter Text Manually", "Upload PDF Lesson Plan"))
        if rubric_option == "Enter Text Manually":
            test_rubric = st.text_area("Topics / Grading Rubric", "Parametric Equations, Second-Order Derivatives, Implicit Differentiation, Chain Rule")
        else:
            rubric_files = st.file_uploader("Upload Rubric", type=["pdf", "png", "jpg", "jpeg"], key="rubric_uploader", help="Upload PDF or image files containing the rubric")
            if rubric_files:
                # Handle single file upload (rubric_files is a single UploadedFile, not a list)
                if rubric_files.type == "application/pdf":
                    test_rubric = extract_text_from_pdf(rubric_files)
                elif rubric_files.type.startswith("image/"):
                    # For single image, extract text using GPT-4o OCR
                    image = Image.open(rubric_files)
                    test_rubric = extract_text_from_image(image)
                    if not test_rubric or test_rubric.startswith("GPT-4o OCR failed"):
                        test_rubric = "Rubric uploaded as image. Please ensure the rubric is clearly visible in the image."
                else:
                    test_rubric = ""
            else:
                test_rubric = ""
        question_paper_files = st.file_uploader("Upload Question Paper", type=["pdf", "png", "jpg", "jpeg"], key="question_uploader", help="Upload PDF or image files containing the question paper")
        submitted = st.form_submit_button("Create Test")
        if submitted and all([test_title, test_date, test_rubric, question_paper_files]):
            # Handle single file upload (question_paper_files is a single UploadedFile, not a list)
            if question_paper_files.type == "application/pdf":
                question_text = extract_text_from_pdf(question_paper_files)
            elif question_paper_files.type.startswith("image/"):
                # For single image, extract text using GPT-4o OCR
                image = Image.open(question_paper_files)
                question_text = extract_text_from_image(image)
                if not question_text or question_text.startswith("GPT-4o OCR failed"):
                    question_text = "Question paper uploaded as image. Please ensure all questions are clearly visible in the image."
            else:
                question_text = ""
            

            # Display extracted question text
            if question_text:
                st.subheader("📄 Extracted Question Paper Text:")
                st.text_area("Question Content", question_text, height=200, disabled=True)
                st.info(f"✅ Successfully extracted {len(question_text)} characters from question paper")
            else:
                st.error("❌ Failed to extract text from question paper")
            
            # Display extracted rubric text
            if test_rubric:
                st.subheader("📋 Extracted Rubric Text:")
                st.text_area("Rubric Content", test_rubric, height=150, disabled=True)
                st.info(f"✅ Successfully extracted {len(test_rubric)} characters from rubric")
            else:
                st.error("❌ Failed to extract text from rubric")
            
            if question_text and test_rubric:
                new_test = {"id": f"test_{len(st.session_state.tests) + 1}", "title": test_title, "date": str(test_date), "rubric": test_rubric, "question_text": question_text}
                st.session_state.tests.append(new_test)
                st.success(f"Test '{test_title}' created!")
        elif submitted:
            st.warning("Please fill out all fields and upload required files.")

st.divider()

if not st.session_state.tests:
    st.info("No tests created yet. Add a new test to get started.")
else:
    for test in reversed(st.session_state.tests):
        with st.container(border=True):
            st.header(f"📝 Test: {test['title']}")
            st.caption(f"Date: {test['date']}")
            for student in st.session_state.students:
                submission_key = f"test_{test['id']}_{student['id']}"
                submission = st.session_state.submissions.get(submission_key)
                cols = st.columns([2, 1, 3])
                cols[0].write(f"**Student:** {student['name']}")
                if submission:
                    score = submission.get("total_score", "N/A")
                    if 'error' in submission:
                        cols[1].error("Error")
                    else:
                        cols[1].success(f"Graded: {score}/100")
                    with cols[2].popover("View Full Analysis"):
                        st.subheader("Detailed Analysis")
                        
                        # --- UI FIX IS HERE ---
                        st.markdown("**Overall Remarks**")
                        remarks = submission.get('overall_remarks', 'No summary provided.')
                        st.markdown(f"> {remarks}") # Using markdown for better text flow
                        # --- END OF UI FIX ---

                        st.markdown("**Question-by-Question Breakdown**")
                        question_analysis = submission.get('question_analysis', [])
                        if question_analysis:
                            for qa in question_analysis:
                                with st.container(border=True):
                                    q_col1, q_col2 = st.columns([3,1])
                                    q_col1.write(f"**Question {qa.get('question_number', 'N/A')}**")
                                    q_col2.metric("Score", f"{qa.get('score', 0)}/{qa.get('max_score', 0)}")
                                    
                                    # Show extracted work if available
                                    if qa.get('extracted_work'):
                                        st.info(f"**Work Found:** {qa.get('extracted_work')}")
                                    
                                    # Show status and feedback
                                    status = qa.get('status', 'Unknown')
                                    status_color = {
                                        'Excellent': 'success',
                                        'Good': 'info', 
                                        'Fair': 'warning',
                                        'Poor': 'error',
                                        'Not Attempted': 'error'
                                    }.get(status, 'secondary')
                                    
                                    st.write(f"**Status:** :{status_color}[{status}]")
                                    st.write(f"**Feedback:** {qa.get('feedback', 'No feedback available.')}")
                                    
                                    # Show mathematical quality assessment if available
                                    if qa.get('mathematical_quality'):
                                        st.info(f"**Mathematical Quality:** {qa.get('mathematical_quality')}")
                                    
                                    # Show completion status if available
                                    if qa.get('completion_status'):
                                        completion_status = qa.get('completion_status')
                                        completion_color = {
                                            'Complete': 'success',
                                            'Nearly Complete': 'info',
                                            'Partially Complete': 'warning',
                                            'Incomplete': 'error',
                                            'Abandoned': 'error'
                                        }.get(completion_status, 'secondary')
                                        st.write(f"**Completion:** :{completion_color}[{completion_status}]")
                        else:
                            st.caption("No question-specific analysis was generated.")
                        st.markdown("**Performance by Concept**")
                        rubric_analysis = submission.get('rubric_analysis', [])
                        if rubric_analysis:
                            for ra in rubric_analysis:
                                with st.container(border=True):
                                    r_col1, r_col2 = st.columns([2,1])
                                    r_col1.write(f"**Concept:** {ra.get('concept', 'N/A')}")
                                    r_col2.write(f"**Performance:** {ra.get('performance', 'N/A')}")
                                    st.markdown(f"**Evidence:** {ra.get('evidence', 'No evidence provided.')}")
                                    if ra.get('recommendations'):
                                        st.info(f"**Recommendations:** {ra.get('recommendations')}")
                        else:
                             st.caption("No rubric-based analysis was generated.")
                        
                        # Show additional analysis if available
                        if submission.get('mathematical_thinking'):
                            st.markdown("**Mathematical Thinking Assessment**")
                            st.info(submission.get('mathematical_thinking'))
                        
                        if submission.get('learning_recommendations'):
                            st.markdown("**Learning Recommendations**")
                            st.success(submission.get('learning_recommendations'))
                        
                        # Show saved file information
                        if submission.get('saved_file'):
                            st.divider()
                            st.markdown("**📁 Extracted Content Saved**")
                            st.info(f"All extracted content has been saved to: `{submission.get('saved_file')}`")
                            
                            # Provide download button for the saved file
                            try:
                                with open(submission.get('saved_file'), 'r', encoding='utf-8') as f:
                                    file_content = f.read()
                                
                                st.download_button(
                                    label="📥 Download Complete Report",
                                    data=file_content,
                                    file_name=f"grading_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                                    mime="application/json",
                                    help="Download the complete grading report with all extracted content"
                                )
                            except Exception as e:
                                st.warning(f"Could not prepare download: {e}")
                else:
                    cols[1].info("Pending")
                    uploaded_files = cols[2].file_uploader(
                        "Upload Handwritten Answers", 
                        type=["pdf", "png", "jpg", "jpeg"], 
                        accept_multiple_files=True,
                        key=f"uploader_{submission_key}",
                        help="Upload PDF files or image files (PNG, JPG, JPEG). You can upload multiple files."
                    )
                    if uploaded_files:
                        progress_bar = cols[2].progress(0, text="Processing files...")
                        answer_images = process_uploaded_files(uploaded_files)
                        
                        # Display processing information
                        st.subheader("📸 Answer Script Processing:")
                        st.info(f"📁 Processing {len(uploaded_files)} uploaded file(s)")
                        
                        if answer_images:
                            st.success(f"✅ Successfully converted {len(answer_images)} image(s) for analysis")
                            
                            # Show preview of processed images
                            with st.expander("👁️ Preview Processed Answer Images", expanded=False):
                                for i, img in enumerate(answer_images):
                                    st.write(f"**Image {i+1}:**")
                                    st.image(img, caption=f"Answer Image {i+1}", use_container_width=True)
                                    
                                    # Extract and display text from each image
                                    extracted_text = extract_text_from_image(img)
                                    if extracted_text and not extracted_text.startswith("GPT-4o OCR failed"):
                                        st.text_area(f"Extracted Text from Image {i+1}", extracted_text, height=100, disabled=True)
                                        st.info(f"✅ GPT-4o extracted {len(extracted_text)} characters from Image {i+1}")
                                    else:
                                        st.warning(f"⚠️ {extracted_text}")
                                        st.info("💡 **Note:** The AI grading will still work using image analysis, even without text extraction.")
                                    st.divider()
                            
                            progress_bar.progress(0.1, text="Starting evaluation...")
                            result = grade_handwritten_submission_with_gpt4o(test['question_text'], answer_images, test['rubric'], test['title'], progress_bar)
                            st.session_state.submissions[submission_key] = {"status": "error" if "error" in result else "graded", **result}
                            st.rerun()
                        else:
                            st.error("No valid files could be processed. Please check your uploads.")