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
from docx import Document
from docx.shared import Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH

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
                        mime="application/json",
                        key=f"sidebar_download_{selected_report}"
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

# Load OpenAI API key from Streamlit secrets (for deployment) or local config
try:
    # First try Streamlit secrets (for deployment)
    if hasattr(st, 'secrets') and st.secrets:
        OPENAI_API_KEY = st.secrets["openai"]["api_key"]
    else:
        # Fallback to local config files for development
        config_paths = [
            "config.toml",
            "../config.toml",
            ".streamlit/secrets.toml",
            os.path.join(os.path.dirname(__file__), "..", "config.toml"),
            os.path.join(os.getcwd(), "config.toml")
        ]
        
        config = None
        for path in config_paths:
            try:
                config = toml.load(path)
                break
            except FileNotFoundError:
                continue
        
        if config is None:
            st.error(f"🚨 No configuration found! Please set up Streamlit secrets or create config.toml")
            st.stop()
        
        OPENAI_API_KEY = config["openai"]["api_key"]
        
except (KeyError, Exception) as e:
    st.error(f"🚨 Error loading API key: {e}")
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

def regenerate_ocr_for_question(question_num, custom_prompt, answer_images, test_id, student_id):
    """Regenerate OCR for a specific question using custom prompt"""
    try:
        # Check if API key is available
        if not OPENAI_API_KEY:
            return None, "OpenAI API key not found"
        
        # Validate inputs
        if not answer_images:
            return None, "No answer images provided"
        # Find images that contain this question
        relevant_images = []
        for answer in answer_images:
            if answer.get('extracted_text'):
                if f"{question_num}." in answer['extracted_text'] or f"{question_num})" in answer['extracted_text']:
                    relevant_images.append(answer)
        
        if not relevant_images:
            return None, "No relevant images found for this question"
        
        # Use the custom prompt or default
        ocr_prompt = custom_prompt if custom_prompt else st.session_state.ocr_prompt
        
        # Get the original images from session state
        original_images = st.session_state.get(f"original_images_{test_id}_{student_id}", [])
        
        if not original_images:
            return None, "Original images not found in session state"
        
        # Call GPT for each relevant image
        new_extractions = []
        for answer in relevant_images:
            image_index = answer["image_number"] - 1  # Convert to 0-based index
            
            if image_index < len(original_images):
                # Get the original image
                original_image = original_images[image_index]
                
                # Convert image to base64 for OpenAI API
                import base64
                img_buffer = io.BytesIO()
                original_image.save(img_buffer, format='PNG')
                img_str = base64.b64encode(img_buffer.getvalue()).decode()
                
                # Call GPT with the image
                from openai import OpenAI
                client = OpenAI(api_key=OPENAI_API_KEY)
                
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
                
                new_extracted_text = response.choices[0].message.content.strip()
                
                new_extraction = {
                    "image_number": answer["image_number"],
                    "extracted_text": new_extracted_text,
                    "character_count": len(new_extracted_text) if new_extracted_text else 0
                }
                new_extractions.append(new_extraction)
            else:
                # If original image not found, keep the existing extraction
                new_extractions.append(answer)
        
        return new_extractions, "OCR regenerated successfully"
    except Exception as e:
        error_msg = f"Error regenerating OCR: {str(e)}"
        if st.session_state.get('debug_mode', False):
            st.error(f"Debug: {error_msg}")
            import traceback
            st.write(f"Debug: Full traceback: {traceback.format_exc()}")
        return None, error_msg

def regenerate_analysis_for_question(question_num, custom_prompt, question_text, student_answer, rubric, test_id, student_id):
    """Regenerate analysis for a specific question using custom prompt"""
    try:
        # Check if API key is available
        if not OPENAI_API_KEY:
            return None, "OpenAI API key not found"
        
        # Validate inputs
        if not question_text or not student_answer:
            return None, "Missing question text or student answer"
        # Create a focused prompt for this specific question
        if custom_prompt:
            analysis_prompt = custom_prompt
        else:
            analysis_prompt = f"""Analyze the student's work for Question {question_num}.

Question: {question_text}
Student's Answer: {student_answer}
Rubric: {rubric}

Provide a detailed analysis including:
1. Score (0 to max score)
2. Status (Excellent/Good/Fair/Poor/Not Attempted)
3. Detailed feedback
4. Work summary
5. Mathematical quality assessment
6. Completion status

Return as JSON:
{{
    "score": <score>,
    "max_score": <max_score>,
    "status": "<status>",
    "feedback": "<detailed feedback>",
    "extracted_work": "<work summary>",
    "mathematical_quality": "<quality assessment>",
    "completion_status": "<completion status>"
}}"""

        # Debug: Print the prompt being sent
        if st.session_state.get('debug_mode', False):
            st.write(f"Debug: Sending analysis prompt to GPT:")
            st.text_area("Analysis Prompt", analysis_prompt, height=200, disabled=True)

        # Call GPT for analysis
        from openai import OpenAI
        client = OpenAI(api_key=OPENAI_API_KEY)
        
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "user", "content": analysis_prompt}
            ],
            temperature=0.2,
            response_format={"type": "json_object"}
        )
        
        # Debug: Print the raw response
        if st.session_state.get('debug_mode', False):
            st.write(f"Debug: GPT Response received:")
            st.write(f"Debug: Response content: {response.choices[0].message.content}")
        
        result = json.loads(response.choices[0].message.content)
        
        # Debug: Print the parsed result
        if st.session_state.get('debug_mode', False):
            st.write(f"Debug: Parsed JSON result: {result}")
        
        return result, "Analysis regenerated successfully"
    except json.JSONDecodeError as e:
        error_msg = f"JSON parsing error: {str(e)}. Raw response: {response.choices[0].message.content if 'response' in locals() else 'No response'}"
        if st.session_state.get('debug_mode', False):
            st.error(f"Debug: {error_msg}")
        return None, error_msg
    except Exception as e:
        error_msg = f"Error regenerating analysis: {str(e)}"
        if st.session_state.get('debug_mode', False):
            st.error(f"Debug: {error_msg}")
            import traceback
            st.write(f"Debug: Full traceback: {traceback.format_exc()}")
        return None, error_msg

def extract_question_answer(extracted_answers, question_num):
    """Intelligently extract the answer for a specific question from all extracted text"""
    if not extracted_answers:
        return ""
    
    # Combine all extracted text
    all_text = ""
    for answer in extracted_answers:
        if answer.get('extracted_text'):
            all_text += f"\n{answer['extracted_text']}\n"
    
    # Define patterns to find question boundaries
    question_patterns = [
        rf"{question_num}\.\s*",  # "1. "
        rf"{question_num}\)\s*",  # "1) "
        rf"Question\s*{question_num}\s*",  # "Question 1"
        rf"Q{question_num}\s*",  # "Q1"
    ]
    
    # Find the start of the target question
    start_pos = -1
    for pattern in question_patterns:
        match = re.search(pattern, all_text, re.IGNORECASE)
        if match:
            start_pos = match.start()
            break
    
    if start_pos == -1:
        return ""
    
    # Find the end of this question (start of next question or end of text)
    end_pos = len(all_text)
    next_question_patterns = [
        rf"{question_num + 1}\.\s*",  # "2. "
        rf"{question_num + 1}\)\s*",  # "2) "
        rf"Question\s*{question_num + 1}\s*",  # "Question 2"
        rf"Q{question_num + 1}\s*",  # "Q2"
    ]
    
    for pattern in next_question_patterns:
        match = re.search(pattern, all_text[start_pos:], re.IGNORECASE)
        if match:
            end_pos = start_pos + match.start()
            break
    
    # Extract the question answer
    question_answer = all_text[start_pos:end_pos].strip()
    
    # Clean up the answer
    lines = question_answer.split('\n')
    cleaned_lines = []
    for line in lines:
        line = line.strip()
        if line:
            cleaned_lines.append(line)
    
    return '\n'.join(cleaned_lines)

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

def save_extracted_content(test_title, student_name, question_text, rubric, answer_images, question_analysis, final_score, summary_data=None):
    """Save all extracted content to a comprehensive DOC file"""
    try:
        # Create reports directory if it doesn't exist
        os.makedirs("grading_reports", exist_ok=True)
        
        # Generate filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        doc_filename = f"grading_reports/{test_title}_{student_name}_{timestamp}.docx"
        
        # Extract text from all answer images
        extracted_answers = []
        for i, img in enumerate(answer_images):
            extracted_text = extract_text_from_image(img)
            extracted_answers.append({
                "image_number": i + 1,
                "extracted_text": extracted_text,
                "character_count": len(extracted_text) if extracted_text else 0
            })
        
        # Create DOC document
        doc = Document()
        
        # Title
        title = doc.add_heading(f'Grading Report: {test_title}', 0)
        title.alignment = WD_ALIGN_PARAGRAPH.CENTER
        
        # Metadata
        doc.add_heading('Report Information', level=1)
        doc.add_paragraph(f'Student: {student_name}')
        doc.add_paragraph(f'Test: {test_title}')
        doc.add_paragraph(f'Date: {datetime.now().strftime("%B %d, %Y")}')
        doc.add_paragraph(f'Total Score: {final_score}/100')
        doc.add_paragraph(f'Total Questions: {len(question_analysis)}')
        
        # Question Paper
        doc.add_heading('Question Paper', level=1)
        if question_text:
            # Format question text properly while preserving structure
            lines = question_text.split('\n')
            current_section = None
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                
                # Check if it's a section header
                if line.upper().startswith('SECTION'):
                    current_section = line
                    doc.add_heading(line, level=2)
                
                # Check if it's a question number (1), 2), etc.)
                elif re.match(r'^\d+[\)\.]', line):
                    # Extract question number and text
                    question_match = re.match(r'^(\d+)[\)\.]\s*(.*)', line)
                    if question_match:
                        q_num = question_match.group(1)
                        q_text = question_match.group(2)
                        
                        # Format question with proper spacing
                        question_heading = f"{q_num}) {q_text}"
                        doc.add_heading(question_heading, level=3)
                    else:
                        doc.add_heading(line, level=3)
                
                # Check if it's header information
                elif any(keyword in line.upper() for keyword in ['CLASS', 'TIME', 'MARKS', 'CAS CLASSES', 'DIFFERENTIATION TEST']):
                    # Format header information
                    if 'CAS CLASSES' in line.upper():
                        # Split CAS CLASSES line into multiple lines for better formatting
                        parts = line.split('CAS CLASSES')
                        if len(parts) > 1:
                            doc.add_paragraph('CAS CLASSES', style='Heading 4')
                            doc.add_paragraph(parts[1].strip())
                        else:
                            doc.add_paragraph(line, style='Heading 4')
                    elif 'CLASS 12' in line.upper():
                        doc.add_heading(line, level=4)
                    elif 'TIME ALLOWED' in line.upper() or 'MAXIMUM MARKS' in line.upper():
                        doc.add_paragraph(line, style='Heading 4')
                    else:
                        doc.add_paragraph(line, style='Heading 4')
                
                # Regular question text (continuation of questions)
                else:
                    # Check if this is continuation of a question
                    if current_section and not line.startswith('[') and not line.startswith('Time') and not line.startswith('Maximum'):
                        doc.add_paragraph(line)
                    elif line.startswith('[') and line.endswith(']'):
                        # This is a marks indicator, add it to the previous paragraph
                        continue
                    else:
                        doc.add_paragraph(line)
        else:
            doc.add_paragraph("No question text available")
        
        # Rubric
        doc.add_heading('Grading Rubric', level=1)
        if rubric:
            # Format rubric text properly
            rubric_lines = rubric.split('\n')
            for line in rubric_lines:
                line = line.strip()
                if line:
                    # Check if it's a main topic (starts with capital letter and contains comma)
                    if ',' in line and line[0].isupper():
                        # Split by commas and format as bullet points
                        topics = [topic.strip() for topic in line.split(',')]
                        for topic in topics:
                            if topic:
                                doc.add_paragraph(f"• {topic}", style='List Bullet')
                    else:
                        doc.add_paragraph(line)
        else:
            doc.add_paragraph("No rubric available")
        
        # Extracted Answers
        doc.add_heading('Student Answers (Extracted from Images)', level=1)
        for answer in extracted_answers:
            doc.add_heading(f'Image {answer["image_number"]}', level=2)
            if answer.get('extracted_text'):
                # Clean and format extracted text
                clean_text = answer['extracted_text'].replace('\n\n', '\n').strip()
                if clean_text:
                    doc.add_paragraph(clean_text)
                else:
                    doc.add_paragraph("No text extracted from this image")
            else:
                doc.add_paragraph("No text extracted from this image")
        
        # Question Analysis
        doc.add_heading('Question-by-Question Analysis', level=1)
        for qa in question_analysis:
            doc.add_heading(f'Question {qa.get("question_number", "N/A")}', level=2)
            doc.add_paragraph(f'Score: {qa.get("score", 0)}/{qa.get("max_score", 0)}')
            doc.add_paragraph(f'Status: {qa.get("status", "Unknown")}')
            
            # Clean and format feedback
            feedback = qa.get("feedback", "No feedback available")
            if feedback:
                clean_feedback = feedback.replace('\n', ' ').strip()
                doc.add_paragraph(f'Feedback: {clean_feedback}')
            
            if qa.get('extracted_work'):
                clean_work = qa.get('extracted_work').replace('\n', ' ').strip()
                doc.add_paragraph(f'Work Found: {clean_work}')
            
            if qa.get('mathematical_quality'):
                clean_quality = qa.get('mathematical_quality').replace('\n', ' ').strip()
                doc.add_paragraph(f'Mathematical Quality: {clean_quality}')
            
            if qa.get('completion_status'):
                doc.add_paragraph(f'Completion Status: {qa.get("completion_status")}')
        
        # Overall Summary
        doc.add_heading('Overall Summary', level=1)
        
        # Check for summary data passed as parameter
        summary_found = False
        if summary_data:
            if summary_data.get('overall_remarks'):
                clean_remarks = summary_data.get('overall_remarks').replace('\n', ' ').strip()
                doc.add_paragraph(clean_remarks)
                summary_found = True
            
            if summary_data.get('mathematical_thinking'):
                doc.add_heading('Mathematical Thinking Assessment', level=2)
                clean_thinking = summary_data.get('mathematical_thinking').replace('\n', ' ').strip()
                doc.add_paragraph(clean_thinking)
                summary_found = True
            
            if summary_data.get('learning_recommendations'):
                doc.add_heading('Learning Recommendations', level=2)
                clean_recommendations = summary_data.get('learning_recommendations').replace('\n', ' ').strip()
                doc.add_paragraph(clean_recommendations)
                summary_found = True
        
        # If no summary found, create a basic summary from scores
        if not summary_found:
            total_score = sum(qa.get('score', 0) for qa in question_analysis)
            max_score = sum(qa.get('max_score', 0) for qa in question_analysis)
            percentage = (total_score / max_score * 100) if max_score > 0 else 0
            
            # Count performance levels
            excellent_count = sum(1 for qa in question_analysis if qa.get('status') == 'Excellent')
            good_count = sum(1 for qa in question_analysis if qa.get('status') == 'Good')
            fair_count = sum(1 for qa in question_analysis if qa.get('status') == 'Fair')
            poor_count = sum(1 for qa in question_analysis if qa.get('status') == 'Poor')
            not_attempted = sum(1 for qa in question_analysis if qa.get('status') == 'Not Attempted')
            
            # Generate summary
            summary_text = f"Student achieved a total score of {total_score}/{max_score} ({percentage:.1f}%). "
            summary_text += f"Performance breakdown: {excellent_count} excellent, {good_count} good, {fair_count} fair, {poor_count} poor, and {not_attempted} not attempted questions. "
            
            if percentage >= 90:
                summary_text += "Overall performance is excellent with strong understanding of the concepts."
            elif percentage >= 80:
                summary_text += "Overall performance is very good with minor areas for improvement."
            elif percentage >= 70:
                summary_text += "Overall performance is good with some areas needing attention."
            elif percentage >= 60:
                summary_text += "Overall performance is satisfactory but requires significant improvement."
            else:
                summary_text += "Overall performance needs substantial improvement and additional practice."
            
            doc.add_paragraph(summary_text)
            
            # Add recommendations based on performance
            doc.add_heading('Recommendations', level=2)
            if poor_count > 0 or not_attempted > 0:
                doc.add_paragraph("Focus on reviewing fundamental concepts and practicing basic differentiation techniques.")
            if fair_count > 0:
                doc.add_paragraph("Work on improving accuracy and understanding of intermediate-level problems.")
            if excellent_count < len(question_analysis) * 0.5:
                doc.add_paragraph("Continue practicing advanced problems to strengthen overall mathematical skills.")
        
        # Save DOC file
        doc.save(doc_filename)
        
        return doc_filename
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
    
    # Extract full text from all answer images
    extracted_answers = []
    for i, img in enumerate(answer_images):
        extracted_text = extract_text_from_image(img)
        extracted_answers.append({
            "image_number": i + 1,
            "extracted_text": extracted_text,
            "character_count": len(extracted_text) if extracted_text else 0
        })
    
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
        final_score=final_percentage,
        summary_data=summary_data
    )
    
    if saved_file:
        final_analysis["saved_file"] = saved_file
    
    # Add extracted answers to the final analysis
    final_analysis["extracted_answers"] = extracted_answers
    
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

                        # Display Questions and Student Answers
                        st.markdown("**📋 Questions and Student Answers**")
                        
                        # Parse questions from the test
                        questions = re.findall(r'(\d+)[).]\s(.*?)(?:\[(\d+)\])', test['question_text'], re.DOTALL)
                        
                        if questions:
                            for i, q in enumerate(questions):
                                q_num, q_text, q_max_score = int(q[0]), q[1].strip(), int(q[2])
                                
                                with st.container(border=True):
                                    st.markdown(f"**Question {q_num}** (Max Score: {q_max_score})")
                                    
                                    # Question text with edit capability
                                    col1, col2 = st.columns([4, 1])
                                    with col1:
                                        st.text_area(f"Question {q_num} Text", q_text, height=80, disabled=True, key=f"question_text_{test['id']}_{student['id']}_{q_num}")
                                    with col2:
                                        if st.button("✏️ Edit Question", key=f"edit_question_{test['id']}_{student['id']}_{q_num}"):
                                            st.session_state[f"editing_question_{test['id']}_{student['id']}_{q_num}"] = True
                                    
                                    # Edit question text
                                    if st.session_state.get(f"editing_question_{test['id']}_{student['id']}_{q_num}", False):
                                        edited_question = st.text_area("Edit Question Text", q_text, height=100, key=f"edit_question_text_{test['id']}_{student['id']}_{q_num}")
                                        col1, col2 = st.columns(2)
                                        if col1.button("✅ Save", key=f"save_question_{test['id']}_{student['id']}_{q_num}"):
                                            st.success("Question updated!")
                                            st.session_state[f"editing_question_{test['id']}_{student['id']}_{q_num}"] = False
                                            st.rerun()
                                        if col2.button("❌ Cancel", key=f"cancel_question_{test['id']}_{student['id']}_{q_num}"):
                                            st.session_state[f"editing_question_{test['id']}_{student['id']}_{q_num}"] = False
                                            st.rerun()
                                    
                                    # Find corresponding question analysis
                                    qa = next((qa for qa in submission.get('question_analysis', []) if qa.get('question_number') == q_num), None)
                                    
                                    if qa:
                                        # Show complete extracted answer for this question
                                        extracted_answers = submission.get('extracted_answers', [])
                                        if extracted_answers:
                                            st.markdown("**Complete Student Answer (Extracted from Images):**")
                                            
                                            # Intelligent question answer extraction
                                            relevant_text = extract_question_answer(extracted_answers, q_num)
                                            
                                            if relevant_text.strip():
                                                col1, col2 = st.columns([4, 1])
                                                with col1:
                                                    st.text_area(f"Complete Answer for Q{q_num}", relevant_text.strip(), height=300, disabled=True, key=f"complete_answer_{test['id']}_{student['id']}_{q_num}")
                                                with col2:
                                                    if st.button("✏️ Edit Answer", key=f"edit_answer_{test['id']}_{student['id']}_{q_num}"):
                                                        st.session_state[f"editing_answer_{test['id']}_{student['id']}_{q_num}"] = True
                                                
                                                # Regenerate OCR for this question
                                                if st.button("🔄 Regenerate OCR", key=f"regenerate_ocr_{test['id']}_{student['id']}_{q_num}"):
                                                    st.session_state[f"regenerating_ocr_{test['id']}_{student['id']}_{q_num}"] = True
                                                
                                                # OCR regeneration interface
                                                if st.session_state.get(f"regenerating_ocr_{test['id']}_{student['id']}_{q_num}", False):
                                                    st.markdown("**🔄 Regenerate OCR for Question {q_num}**")
                                                    
                                                    # Custom OCR prompt for this question
                                                    custom_ocr_prompt = st.text_area(
                                                        f"Custom OCR Prompt for Q{q_num}",
                                                        value=f"Extract and format the student's answer for Question {q_num} from this image. Focus on mathematical notation and ensure accuracy.",
                                                        height=100,
                                                        key=f"ocr_prompt_{test['id']}_{student['id']}_{q_num}"
                                                    )
                                                    
                                                    # Show original images for this question
                                                    st.markdown("**Original Images:**")
                                                    for answer in extracted_answers:
                                                        if answer.get('extracted_text'):
                                                            # Check if this image contains the question
                                                            if f"{q_num}." in answer['extracted_text'] or f"{q_num})" in answer['extracted_text']:
                                                                st.markdown(f"**Image {answer['image_number']}:**")
                                                                # Here you would show the actual image
                                                                st.text_area(f"Current OCR for Image {answer['image_number']}", answer['extracted_text'], height=150, disabled=True)
                                                    
                                                    col1, col2, col3 = st.columns(3)
                                                    if col1.button("🔄 Regenerate with Custom Prompt", key=f"execute_ocr_{test['id']}_{student['id']}_{q_num}"):
                                                        with st.spinner("🔄 Regenerating OCR with custom prompt..."):
                                                            # Get the custom prompt
                                                            custom_prompt = st.session_state.get(f"ocr_prompt_{test['id']}_{student['id']}_{q_num}", "")
                                                            
                                                            # Debug information
                                                            if st.session_state.get('debug_mode', False):
                                                                st.write(f"Debug: Custom prompt: {custom_prompt}")
                                                                st.write(f"Debug: Question number: {q_num}")
                                                                st.write(f"Debug: Test ID: {test['id']}, Student ID: {student['id']}")
                                                                session_key = f'original_images_{test["id"]}_{student["id"]}'
                                                                st.write(f"Debug: Original images in session: {session_key in st.session_state}")
                                                                if session_key in st.session_state:
                                                                    st.write(f"Debug: Number of original images: {len(st.session_state[session_key])}")
                                                            
                                                            # Call the regeneration function
                                                            new_extractions, message = regenerate_ocr_for_question(
                                                                q_num, custom_prompt, extracted_answers, test['id'], student['id']
                                                            )
                                                            
                                                            if new_extractions:
                                                                # Update the submission with new OCR data
                                                                submission['extracted_answers'] = new_extractions
                                                                st.success(f"OCR regenerated successfully! {message}")
                                                                
                                                                # Debug: Show new extractions
                                                                if st.session_state.get('debug_mode', False):
                                                                    st.write("Debug: New extractions:")
                                                                    for ext in new_extractions:
                                                                        st.write(f"  Image {ext['image_number']}: {ext['extracted_text'][:100]}...")
                                                            else:
                                                                st.error(f"Failed to regenerate OCR: {message}")
                                                            
                                                            st.session_state[f"regenerating_ocr_{test['id']}_{student['id']}_{q_num}"] = False
                                                            st.rerun()
                                                    if col2.button("✅ Use Default Prompt", key=f"default_ocr_{test['id']}_{student['id']}_{q_num}"):
                                                        with st.spinner("🔄 Regenerating OCR with default prompt..."):
                                                            # Call the regeneration function with default prompt
                                                            new_extractions, message = regenerate_ocr_for_question(
                                                                q_num, "", extracted_answers, test['id'], student['id']
                                                            )
                                                            
                                                            if new_extractions:
                                                                # Update the submission with new OCR data
                                                                submission['extracted_answers'] = new_extractions
                                                                st.success(f"OCR regenerated with default prompt! {message}")
                                                            else:
                                                                st.error(f"Failed to regenerate OCR: {message}")
                                                            
                                                            st.session_state[f"regenerating_ocr_{test['id']}_{student['id']}_{q_num}"] = False
                                                            st.rerun()
                                                    if col3.button("❌ Cancel OCR", key=f"cancel_ocr_{test['id']}_{student['id']}_{q_num}"):
                                                        st.session_state[f"regenerating_ocr_{test['id']}_{student['id']}_{q_num}"] = False
                                                        st.rerun()
                                                
                                                # Edit answer text
                                                if st.session_state.get(f"editing_answer_{test['id']}_{student['id']}_{q_num}", False):
                                                    edited_answer = st.text_area("Edit Student Answer", relevant_text.strip(), height=300, key=f"edit_answer_text_{test['id']}_{student['id']}_{q_num}")
                                                    col1, col2 = st.columns(2)
                                                    if col1.button("✅ Save Answer", key=f"save_answer_{test['id']}_{student['id']}_{q_num}"):
                                                        st.success("Answer updated!")
                                                        st.session_state[f"editing_answer_{test['id']}_{student['id']}_{q_num}"] = False
                                                        st.rerun()
                                                    if col2.button("❌ Cancel Answer", key=f"cancel_answer_{test['id']}_{student['id']}_{q_num}"):
                                                        st.session_state[f"editing_answer_{test['id']}_{student['id']}_{q_num}"] = False
                                                        st.rerun()
                                            else:
                                                st.warning(f"No specific answer found for Question {q_num}")
                                        else:
                                            st.warning("No extracted answers available.")
                                        
                                        # Show AI's work summary with edit capability
                                        if qa.get('extracted_work'):
                                            st.markdown("**AI's Work Summary:**")
                                            col1, col2 = st.columns([4, 1])
                                            with col1:
                                                st.info(qa.get('extracted_work'))
                                            with col2:
                                                if st.button("✏️ Edit Summary", key=f"edit_summary_{test['id']}_{student['id']}_{q_num}"):
                                                    st.session_state[f"editing_summary_{test['id']}_{student['id']}_{q_num}"] = True
                                            
                                            # Edit work summary
                                            if st.session_state.get(f"editing_summary_{test['id']}_{student['id']}_{q_num}", False):
                                                edited_summary = st.text_area("Edit Work Summary", qa.get('extracted_work', ''), height=100, key=f"edit_summary_text_{test['id']}_{student['id']}_{q_num}")
                                                col1, col2 = st.columns(2)
                                                if col1.button("✅ Save Summary", key=f"save_summary_{test['id']}_{student['id']}_{q_num}"):
                                                    st.success("Work summary updated!")
                                                    st.session_state[f"editing_summary_{test['id']}_{student['id']}_{q_num}"] = False
                                                    st.rerun()
                                                if col2.button("❌ Cancel Summary", key=f"cancel_summary_{test['id']}_{student['id']}_{q_num}"):
                                                    st.session_state[f"editing_summary_{test['id']}_{student['id']}_{q_num}"] = False
                                                    st.rerun()
                                        
                                        # Show score and status with edit capability
                                        col1, col2, col3 = st.columns([2, 1, 1])
                                        with col1:
                                            score = qa.get('score', 0)
                                            max_score = qa.get('max_score', 0)
                                            st.metric("Score", f"{score}/{max_score}")
                                        with col2:
                                            if st.button("✏️ Edit Score", key=f"edit_score_{test['id']}_{student['id']}_{q_num}"):
                                                st.session_state[f"editing_score_{test['id']}_{student['id']}_{q_num}"] = True
                                        with col3:
                                            status = qa.get('status', 'Unknown')
                                            status_color = {
                                                'Excellent': 'success',
                                                'Good': 'info', 
                                                'Fair': 'warning',
                                                'Poor': 'error',
                                                'Not Attempted': 'error'
                                            }.get(status, 'secondary')
                                            st.write(f"**Status:** :{status_color}[{status}]")
                                        
                                        # Edit score
                                        if st.session_state.get(f"editing_score_{test['id']}_{student['id']}_{q_num}", False):
                                            col1, col2 = st.columns(2)
                                            with col1:
                                                new_score = st.number_input("New Score", min_value=0, max_value=max_score, value=score, key=f"new_score_{test['id']}_{student['id']}_{q_num}")
                                            with col2:
                                                new_status = st.selectbox("New Status", ['Excellent', 'Good', 'Fair', 'Poor', 'Not Attempted'], index=['Excellent', 'Good', 'Fair', 'Poor', 'Not Attempted'].index(status) if status in ['Excellent', 'Good', 'Fair', 'Poor', 'Not Attempted'] else 0, key=f"new_status_{test['id']}_{student['id']}_{q_num}")
                                            
                                            col1, col2 = st.columns(2)
                                            if col1.button("✅ Save Score", key=f"save_score_{test['id']}_{student['id']}_{q_num}"):
                                                st.success("Score and status updated!")
                                                st.session_state[f"editing_score_{test['id']}_{student['id']}_{q_num}"] = False
                                                st.rerun()
                                            if col2.button("❌ Cancel Score", key=f"cancel_score_{test['id']}_{student['id']}_{q_num}"):
                                                st.session_state[f"editing_score_{test['id']}_{student['id']}_{q_num}"] = False
                                                st.rerun()
                                        
                                        # Show feedback with edit capability
                                        st.markdown("**Feedback:**")
                                        col1, col2 = st.columns([4, 1])
                                        with col1:
                                            st.write(qa.get('feedback', 'No feedback available.'))
                                        with col2:
                                            if st.button("✏️ Edit Feedback", key=f"edit_feedback_{test['id']}_{student['id']}_{q_num}"):
                                                st.session_state[f"editing_feedback_{test['id']}_{student['id']}_{q_num}"] = True
                                        
                                        # Edit feedback
                                        if st.session_state.get(f"editing_feedback_{test['id']}_{student['id']}_{q_num}", False):
                                            edited_feedback = st.text_area("Edit Feedback", qa.get('feedback', 'No feedback available.'), height=100, key=f"edit_feedback_text_{test['id']}_{student['id']}_{q_num}")
                                            col1, col2 = st.columns(2)
                                            if col1.button("✅ Save Feedback", key=f"save_feedback_{test['id']}_{student['id']}_{q_num}"):
                                                st.success("Feedback updated!")
                                                st.session_state[f"editing_feedback_{test['id']}_{student['id']}_{q_num}"] = False
                                                st.rerun()
                                            if col2.button("❌ Cancel Feedback", key=f"cancel_feedback_{test['id']}_{student['id']}_{q_num}"):
                                                st.session_state[f"editing_feedback_{test['id']}_{student['id']}_{q_num}"] = False
                                                st.rerun()
                                        
                                        # Regenerate Analysis for this question
                                        if st.button("🔄 Regenerate Analysis", key=f"regenerate_analysis_{test['id']}_{student['id']}_{q_num}"):
                                            st.session_state[f"regenerating_analysis_{test['id']}_{student['id']}_{q_num}"] = True
                                        
                                        # Analysis regeneration interface
                                        if st.session_state.get(f"regenerating_analysis_{test['id']}_{student['id']}_{q_num}", False):
                                            st.markdown("**🔄 Regenerate Analysis for Question {q_num}**")
                                            
                                            # Custom analysis prompt for this question
                                            custom_analysis_prompt = st.text_area(
                                                f"Custom Analysis Prompt for Q{q_num}",
                                                value=f"Analyze the student's work for Question {q_num}. Provide detailed feedback on mathematical accuracy, completeness, and areas for improvement.",
                                                height=100,
                                                key=f"analysis_prompt_{test['id']}_{student['id']}_{q_num}"
                                            )
                                            
                                            # Show current analysis
                                            st.markdown("**Current Analysis:**")
                                            st.info(f"**Score:** {qa.get('score', 0)}/{qa.get('max_score', 0)}")
                                            st.info(f"**Status:** {qa.get('status', 'Unknown')}")
                                            st.info(f"**Feedback:** {qa.get('feedback', 'No feedback available.')}")
                                            if qa.get('extracted_work'):
                                                st.info(f"**Work Summary:** {qa.get('extracted_work')}")
                                            
                                            col1, col2, col3 = st.columns(3)
                                            if col1.button("🔄 Regenerate with Custom Prompt", key=f"execute_analysis_{test['id']}_{student['id']}_{q_num}"):
                                                with st.spinner("🔄 Regenerating analysis with custom prompt..."):
                                                    # Get the custom prompt
                                                    custom_prompt = st.session_state.get(f"analysis_prompt_{test['id']}_{student['id']}_{q_num}", "")
                                                    
                                                    # Debug information
                                                    if st.session_state.get('debug_mode', False):
                                                        st.write(f"Debug: Custom analysis prompt: {custom_prompt}")
                                                        st.write(f"Debug: Question number: {q_num}")
                                                        st.write(f"Debug: Question text: {q_text[:100]}...")
                                                    
                                                    # Get current student answer
                                                    student_answer = extract_question_answer(extracted_answers, q_num)
                                                    
                                                    if st.session_state.get('debug_mode', False):
                                                        st.write(f"Debug: Student answer: {student_answer[:100]}...")
                                                    
                                                    # Call the regeneration function
                                                    new_analysis, message = regenerate_analysis_for_question(
                                                        q_num, custom_prompt, q_text, student_answer, test['rubric'], test['id'], student['id']
                                                    )
                                                    
                                                    if new_analysis:
                                                        if st.session_state.get('debug_mode', False):
                                                            st.write(f"Debug: New analysis received: {new_analysis}")
                                                        
                                                        # Update the question analysis in the session state
                                                        submission_key = f"test_{test['id']}_{student['id']}"
                                                        if submission_key in st.session_state.submissions:
                                                            # Find and update the specific question analysis
                                                            for i, qa_item in enumerate(st.session_state.submissions[submission_key].get('question_analysis', [])):
                                                                if qa_item.get('question_number') == q_num:
                                                                    st.session_state.submissions[submission_key]['question_analysis'][i].update(new_analysis)
                                                                    if st.session_state.get('debug_mode', False):
                                                                        st.write(f"Debug: Updated question {q_num} in session state")
                                                                    break
                                                        
                                                        st.success(f"Analysis regenerated successfully! {message}")
                                                    else:
                                                        st.error(f"Failed to regenerate analysis: {message}")
                                                    
                                                    st.session_state[f"regenerating_analysis_{test['id']}_{student['id']}_{q_num}"] = False
                                                    st.rerun()
                                            if col2.button("✅ Use Default Prompt", key=f"default_analysis_{test['id']}_{student['id']}_{q_num}"):
                                                with st.spinner("🔄 Regenerating analysis with default prompt..."):
                                                    # Get current student answer
                                                    student_answer = extract_question_answer(extracted_answers, q_num)
                                                    
                                                    # Call the regeneration function with default prompt
                                                    new_analysis, message = regenerate_analysis_for_question(
                                                        q_num, "", q_text, student_answer, test['rubric'], test['id'], student['id']
                                                    )
                                                    
                                                    if new_analysis:
                                                        # Update the question analysis in the session state
                                                        submission_key = f"test_{test['id']}_{student['id']}"
                                                        if submission_key in st.session_state.submissions:
                                                            # Find and update the specific question analysis
                                                            for i, qa_item in enumerate(st.session_state.submissions[submission_key].get('question_analysis', [])):
                                                                if qa_item.get('question_number') == q_num:
                                                                    st.session_state.submissions[submission_key]['question_analysis'][i].update(new_analysis)
                                                                    break
                                                        
                                                        st.success(f"Analysis regenerated with default prompt! {message}")
                                                    else:
                                                        st.error(f"Failed to regenerate analysis: {message}")
                                                    
                                                    st.session_state[f"regenerating_analysis_{test['id']}_{student['id']}_{q_num}"] = False
                                                    st.rerun()
                                            if col3.button("❌ Cancel Analysis", key=f"cancel_analysis_{test['id']}_{student['id']}_{q_num}"):
                                                st.session_state[f"regenerating_analysis_{test['id']}_{student['id']}_{q_num}"] = False
                                                st.rerun()
                                        
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
                                        st.warning("No analysis available for this question.")
                                    
                                    st.divider()
                        else:
                            st.warning("Could not parse questions from the test.")

                        st.markdown("**📊 Detailed Question Analysis**")
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
                                with open(submission.get('saved_file'), 'rb') as f:
                                    file_content = f.read()
                                
                                st.download_button(
                                    label="📥 Download Complete Report (DOC)",
                                    data=file_content,
                                    file_name=f"grading_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.docx",
                                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                                    help="Download the complete grading report as a DOC file with all extracted content",
                                    key=f"download_doc_{test['id']}_{student['id']}"
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
                            
                            # Store original images in session state for regeneration
                            st.session_state[f"original_images_{test['id']}_{student['id']}"] = answer_images
                            
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
                            
                            # Debug: Check if extracted answers are in result
                            if st.session_state.get('debug_mode', False):
                                st.subheader("🔍 Debug: Result Contents")
                                st.write("Result keys:", list(result.keys()) if isinstance(result, dict) else "Not a dict")
                                if isinstance(result, dict) and 'extracted_answers' in result:
                                    st.write("Extracted answers found:", len(result['extracted_answers']))
                                else:
                                    st.write("No extracted_answers in result")
                            
                            st.session_state.submissions[submission_key] = {"status": "error" if "error" in result else "graded", **result}
                            st.rerun()
                        else:
                            st.error("No valid files could be processed. Please check your uploads.")