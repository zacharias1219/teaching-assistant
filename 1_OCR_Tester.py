import io
import os
import re
import json
from typing import List, Dict, Any

import streamlit as st
from PIL import Image
from PIL import ImageEnhance, ImageFilter


try:
    import fitz  # PyMuPDF
except Exception:  # pragma: no cover - optional at runtime
    fitz = None

try:
    from openai import OpenAI
except Exception:  # pragma: no cover - optional at runtime
    OpenAI = None

# Load environment variables from a local .env if present (development convenience)
try:
    from dotenv import load_dotenv  # type: ignore
    try:
        load_dotenv()  # Loads from .env in CWD or parents
    except Exception:
        pass
except Exception:
    load_dotenv = None

try:
    import pytesseract  # type: ignore
except Exception:  # pragma: no cover - optional at runtime
    pytesseract = None


# --------------
# Config / Defaults
# --------------
# Try to mirror Start Grading page behavior: prefer Streamlit secrets, then config.toml, then env
OPENAI_API_KEY = None
try:
    if hasattr(st, 'secrets') and st.secrets and "openai" in st.secrets:
        OPENAI_API_KEY = st.secrets["openai"]["api_key"]
except Exception:
    pass
if not OPENAI_API_KEY:
    try:
        import toml  # type: ignore
        config_paths = [
            "config.toml",
            "../config.toml",
            ".streamlit/secrets.toml",
            os.path.join(os.path.dirname(__file__), "..", "config.toml"),
            os.path.join(os.getcwd(), "config.toml"),
        ]
        for path in config_paths:
            try:
                cfg = toml.load(path)
                OPENAI_API_KEY = cfg.get("openai", {}).get("api_key")
                if OPENAI_API_KEY:
                    break
            except Exception:
                continue
    except Exception:
        pass
if not OPENAI_API_KEY:
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

DEFAULT_ANSWER_OCR_PROMPT = (
    "You are an elite OCR agent for handwritten exam answers. \n"
    "Extract the COMPLETE student answer text as readable plain text.\n\n"
    "Rules:\n"
    "- Preserve all math faithfully: ∫, √, Σ, Π, |x|, d/dx, lim; keep trig/log names.\n"
    "- Convert LaTeX-like tokens to readable forms: \\frac{dy}{dx} -> d/dx; \\sqrt{x} -> √x; x^{2} -> x^2; x_{0} -> x_0.\n"
    "- Keep original line breaks and steps; do not summarize.\n"
    "- If unreadable, write [illegible]. Output plain text only."
)


# --------------
# Helpers
# --------------
def resolve_openai_api_key() -> str:
    """Resolve the OpenAI API key from (priority): sidebar input → st.secrets → env.

    The global OPENAI_API_KEY is kept for backwards compatibility as the env fallback.
    """
    try:
        # Sidebar input stored in session_state (if present)
        from streamlit.runtime.scriptrunner import add_script_run_ctx  # type: ignore
        # Import above ensures we're in a Streamlit context; ignore otherwise
    except Exception:
        pass
    try:
        val = st.session_state.get("openai_api_key")
        if isinstance(val, str) and val.strip():
            return val.strip()
    except Exception:
        pass
    try:
        if "OPENAI_API_KEY" in st.secrets:
            val = st.secrets["OPENAI_API_KEY"]
            if isinstance(val, str) and val.strip():
                return val.strip()
    except Exception:
        pass
    return (OPENAI_API_KEY or "").strip()


def _mask_sensitive(text: str) -> str:
    """Mask API keys in error messages (e.g., sk-... → sk-****)."""
    try:
        return re.sub(r"sk-[a-zA-Z0-9_-]+", "sk-****", text)
    except Exception:
        return "[redacted]"


def _describe_openai_error(exc: Exception) -> str:
    msg = str(exc)
    lower = msg.lower()
    if "401" in lower or "invalid_api_key" in lower or "incorrect api key" in lower:
        return "[OCR error: Invalid OpenAI API key. Update it in the sidebar or set OPENAI_API_KEY.]"
    if "429" in lower or "rate" in lower:
        return "[OCR error: Rate limited. Please retry later.]"
    if "timeout" in lower:
        return "[OCR error: Request timed out. Please retry.]"
    return f"[OCR error: {_mask_sensitive(msg)}]"


def get_masked_key_preview(key: str) -> str:
    if not key:
        return "(none)"
    trimmed = key.strip()
    if len(trimmed) <= 10:
        return "sk-****"
    return f"{trimmed[:4]}...{trimmed[-4:]} (len {len(trimmed)})"


def validate_openai_key_once() -> str:
    """Return a human message about key validity by calling a lightweight endpoint."""
    key = resolve_openai_api_key()
    if not key:
        return "No key set."
    if OpenAI is None:
        return "OpenAI library not available."
    try:
        client = OpenAI(api_key=key)
        # Lightweight call; should not consume significant quota
        _ = client.models.list()
        return "Valid key."
    except Exception as exc:  # pragma: no cover
        return _describe_openai_error(exc)
def convert_pdf_to_images(uploaded_file) -> List[Image.Image]:
    """Convert a PDF (Streamlit UploadedFile) into list of PIL Images at 300 DPI."""
    if fitz is None:
        st.error("PyMuPDF (fitz) not available. Please install PyMuPDF.")
        return []
    try:
        data = uploaded_file.getvalue()
        doc = fitz.open(stream=data, filetype="pdf")
        images: List[Image.Image] = []
        for page in doc:
            pix = page.get_pixmap(dpi=300)
            img_bytes = pix.tobytes("png")
            images.append(Image.open(io.BytesIO(img_bytes)))
        doc.close()
        return images
    except Exception as exc:  # pragma: no cover
        st.error(f"Error converting PDF to images: {exc}")
        return []


def process_uploaded_files(uploaded_files: List[Any]) -> List[Image.Image]:
    """Return list of PIL Images from a mix of PDFs and image files."""
    images: List[Image.Image] = []
    for f in uploaded_files or []:
        try:
            file_name = getattr(f, "name", "") or ""
            file_type = getattr(f, "type", "") or ""
            if file_type == "application/pdf" or file_name.lower().endswith(".pdf"):
                images.extend(convert_pdf_to_images(f))
            else:
                images.append(Image.open(f))
        except Exception as exc:  # pragma: no cover
            st.warning(f"Skipping file due to error: {file_name} ({exc})")
    return images


def extract_text_from_image(image: Image.Image, ocr_prompt: str) -> str:
    """OCR a single image using GPT-4o with the given prompt."""
    resolved_key = resolve_openai_api_key()
    if OpenAI is None or not resolved_key:
        return "[OCR disabled: Missing OpenAI API key. Set it in the sidebar or env OPENAI_API_KEY.]"
    try:
        import base64

        img_buffer = io.BytesIO()
        image.save(img_buffer, format="PNG")
        img_b64 = base64.b64encode(img_buffer.getvalue()).decode()

        client = OpenAI(api_key=resolved_key)
        resp = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": ocr_prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}"}},
                    ],
                }
            ],
            temperature=0.0,
        )
        return (resp.choices[0].message.content or "").strip()
    except Exception as exc:  # pragma: no cover
        # Do not leak raw keys in UI
        return _describe_openai_error(exc)


def extract_text_tesseract(image: Image.Image) -> str:
    """OCR a single image using Tesseract as a local fallback."""
    if pytesseract is None:
        return "[OCR error: Tesseract not available. Install pytesseract and Tesseract OCR.]"
    try:
        # Use a configuration suitable for dense handwriting
        config = "--oem 3 --psm 6"
        text = pytesseract.image_to_string(image, lang="eng", config=config)
        return (text or "").strip()
    except Exception as exc:  # pragma: no cover
        return f"[OCR error: {exc}]"


def _image_to_b64(image: Image.Image) -> str:
    import base64
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode()


def extract_text_from_slices_gpt(slices: List[Image.Image], ocr_prompt: str) -> str:
    """Single GPT request with multiple image slices to reduce latency and costs."""
    resolved_key = resolve_openai_api_key()
    if OpenAI is None or not resolved_key:
        return "[OCR disabled: Missing OpenAI API key. Set it in the sidebar or env OPENAI_API_KEY.]"
    try:
        client = OpenAI(api_key=resolved_key)
        try:
            client = client.with_options(timeout=60.0)
        except Exception:
            pass
        content: List[Dict[str, Any]] = [{"type": "text", "text": ocr_prompt}]
        for img in slices:
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{_image_to_b64(img)}"}
            })
        resp = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": content}],
            temperature=0.0,
        )
        return (resp.choices[0].message.content or "").strip()
    except Exception as exc:  # pragma: no cover
        return _describe_openai_error(exc)


def preprocess_and_slice(image: Image.Image, settings: Dict[str, Any]) -> List[Image.Image]:
    """Apply optional preprocessing and split tall images into slices.

    settings keys (with example defaults):
    - grayscale: bool
    - contrast: float (1.0 = no change)
    - sharpen: bool
    - binarize: bool
    - binarize_threshold: int (0-255)
    - scale_to_max_dim: int (e.g., 2200)
    - slice_tall: bool
    - max_slice_height: int (e.g., 1600)
    - slice_overlap: int (e.g., 80)
    """
    img = image.copy()

    try:
        if settings.get("grayscale"):
            img = img.convert("L")

        contrast_factor = float(settings.get("contrast", 1.0) or 1.0)
        if contrast_factor and abs(contrast_factor - 1.0) > 1e-3:
            img = ImageEnhance.Contrast(img).enhance(contrast_factor)

        if settings.get("sharpen"):
            # Unsharp mask is often better for handwriting
            img = img.filter(ImageFilter.UnsharpMask(radius=2, percent=150, threshold=3))

        if settings.get("binarize"):
            # Ensure grayscale for binarization
            if img.mode != "L":
                img = img.convert("L")
            thr = int(settings.get("binarize_threshold", 180) or 180)
            img = img.point(lambda p: 255 if p >= thr else 0, mode="1").convert("L")

        # Upscale if too small
        max_dim_target = int(settings.get("scale_to_max_dim", 2200) or 2200)
        w, h = img.size
        if max(w, h) < max_dim_target:
            scale = max_dim_target / float(max(w, h))
            new_size = (int(w * scale), int(h * scale))
            img = img.resize(new_size, resample=Image.BICUBIC)

    except Exception:
        # If any preprocessing fails, fall back to original image
        img = image.copy()

    # Slice tall images if requested
    if settings.get("slice_tall"):
        max_h = int(settings.get("max_slice_height", 1600) or 1600)
        overlap = int(settings.get("slice_overlap", 80) or 80)
        slices: List[Image.Image] = []
        top = 0
        height = img.size[1]
        if height > max_h:
            while top < height:
                bottom = min(top + max_h, height)
                crop = img.crop((0, top, img.size[0], bottom))
                slices.append(crop)
                if bottom >= height:
                    break
                top = bottom - overlap
            return slices
    return [img]


def perform_ocr_on_slices(slices: List[Image.Image], ocr_prompt: str, engine: str, settings: Dict[str, Any]) -> str:
    """Dispatch OCR to the selected engine over the full set of slices with minimal requests."""
    engine_low = (engine or "GPT-4o").lower()

    if engine_low.startswith("tesseract"):
        texts = [extract_text_tesseract(s) for s in slices]
        return "\n\n".join(texts).strip()

    if engine_low.startswith("hybrid"):
        baseline_texts = [extract_text_tesseract(s) for s in slices]
        baseline = "\n\n".join([t for t in baseline_texts if t]).strip()
        refined_prompt = (
            ocr_prompt
            + "\n\nBaseline OCR (may contain mistakes). Correct and rewrite as clean text, preserving math and layout:\n"
            + (baseline or "[no baseline]")
        )
        return extract_text_from_slices_gpt(slices, refined_prompt)

    # Default: GPT-4o
    return extract_text_from_slices_gpt(slices, ocr_prompt)


def ocr_all_images(images: List[Image.Image], ocr_prompt: str, settings: Dict[str, Any]) -> List[Dict[str, Any]]:
    """OCR all images with preprocessing, slicing, and engine selection."""
    results: List[Dict[str, Any]] = []
    engine = settings.get("engine", "GPT-4o")
    for idx, img in enumerate(images, start=1):
        slices = preprocess_and_slice(img, settings)
        combined = perform_ocr_on_slices(slices, ocr_prompt, engine=engine, settings=settings)
        results.append({
            "image_number": idx,
            "extracted_text": combined,
            "character_count": len(combined or "")
        })
    return results


def build_line_anchored_pattern(question_number: int) -> str:
    """Anchored pattern for lines like: 1., 1), Q1, Question 1, (1), Q.1, etc."""
    return rf"(?mi)^(?:\s*(?:question\s*)?q?\s*{question_number}\s*(?:[\.)\]:-])?\s+)"


def extract_answer_for_question(extractions: List[Dict[str, Any]], question_number: int) -> str:
    """Slice combined OCR text from the start of the question number to the start of the next."""
    if not extractions:
        return ""
    all_text = "\n".join([x.get("extracted_text", "") for x in extractions])
    all_text = all_text.replace("\r\n", "\n").replace("\r", "\n")

    start_pat = build_line_anchored_pattern(question_number)
    start_match = re.search(start_pat, all_text)
    if not start_match:
        # relaxed fallbacks
        for pat in [
            rf"{question_number}\.\s*",
            rf"{question_number}\)\s*",
            rf"Question\s*{question_number}\s*",
            rf"Q{question_number}\s*",
            rf"\b{question_number}\b",
        ]:
            m = re.search(pat, all_text, re.IGNORECASE)
            if m:
                start_match = m
                break
    if not start_match:
        return ""

    start_pos = start_match.start()
    next_pat = build_line_anchored_pattern(question_number + 1)
    next_match = re.search(next_pat, all_text[start_pos:])
    end_pos = start_pos + next_match.start() if next_match else len(all_text)
    span = all_text[start_pos:end_pos]
    lines = [ln.rstrip() for ln in span.split("\n")]
    cleaned = [ln for ln in lines if ln.strip() != ""]
    return "\n".join(cleaned).strip()


def segment_all_answers(extractions: List[Dict[str, Any]], start_q: int, end_q: int) -> Dict[int, str]:
    segmented: Dict[int, str] = {}
    for q in range(start_q, end_q + 1):
        segmented[q] = extract_answer_for_question(extractions, q)
    return segmented


def segment_answers_auto(extractions: List[Dict[str, Any]]) -> Dict[int, str]:
    """Automatically segment combined OCR text into answers by detected question headers.

    Safer header detection that avoids math lines like "55 + 5t..." by requiring either
    an explicit "Q"/"Question" prefix OR punctuation right after the number (e.g., '1.' or '1)').

    Accepted header forms (line-anchored):
    - "Question 5" / "Question 5." / "Question-5" / "Q5" / "Q.5"
    - "5." , "5)" , "(5)" (optionally followed by a colon/dash and minimal whitespace)

    Returns a dict mapping question_number -> answer_text.
    If no headers are detected, returns {0: combined_text} where key 0 means "All Text" fallback.
    """
    if not extractions:
        return {0: ""}

    # Combine and normalize newlines across all images in-order
    all_text = "\n".join([x.get("extracted_text", "") for x in extractions])
    all_text = all_text.replace("\r\n", "\n").replace("\r", "\n")

    # Split into lines while tracking character offsets for slicing
    lines = all_text.split("\n")
    offsets: List[int] = []
    pos = 0
    for ln in lines:
        offsets.append(pos)
        pos += len(ln) + 1  # +1 for the newline that was split

    # Header detectors (ordered by specificity)
    re_question_prefix = re.compile(r"^\s*(?:question\s*\.?|q\s*\.?)\s*(\d+)\s*(?:[\.)\]:-])?\s*(?:\S.*)?$", re.IGNORECASE)
    # Accept '10) ' or '10.' followed by anything (question text)
    re_number_punct = re.compile(r"^\s*(\d+)\s*[\.)]\s+.+$")
    # Accept '(10) ' followed by anything
    re_paren_number = re.compile(r"^\s*\(\s*(\d+)\s*\)\s+.+$")

    headers: List[Dict[str, int]] = []
    for i, ln in enumerate(lines):
        stripped = ln.strip()
        if not stripped:
            continue

        m = re_question_prefix.match(stripped)
        if not m:
            m = re_number_punct.match(stripped)
        if not m:
            m = re_paren_number.match(stripped)

        if m:
            try:
                qnum = int(m.group(1))
            except Exception:
                continue
            # Heuristic: still avoid plain math equalities like '12 = 15' (no punct after number)
            if re.match(r"^\s*\d+\s*[=+\-×*/]", stripped):
                if not re_question_prefix.match(stripped):
                    continue
            headers.append({"q": qnum, "start": offsets[i]})

    if not headers:
        cleaned_lines = [ln.rstrip() for ln in lines]
        cleaned = "\n".join([ln for ln in cleaned_lines if ln.strip() != ""]).strip()
        return {0: cleaned}

    # Build spans between successive headers
    spans: Dict[int, str] = {}
    for idx, h in enumerate(headers):
        qnum = h["q"]
        start_pos = h["start"]
        end_pos = headers[idx + 1]["start"] if idx + 1 < len(headers) else len(all_text)
        span = all_text[start_pos:end_pos]
        cleaned = "\n".join([ln.rstrip() for ln in span.split("\n") if ln.strip() != ""]).strip()
        if qnum in spans and cleaned:
            spans[qnum] = (spans[qnum] + "\n\n" + cleaned).strip()
        elif cleaned:
            spans[qnum] = cleaned

    if not spans:
        cleaned_lines = [ln.rstrip() for ln in lines]
        cleaned = "\n".join([ln for ln in cleaned_lines if ln.strip() != ""]).strip()
        return {0: cleaned}

    # Preserve detection order
    ordered: Dict[int, str] = {}
    for h in headers:
        q = h["q"]
        if q in spans and q not in ordered:
            ordered[q] = spans[q]
    return ordered


# --------------
# UI
# --------------
st.set_page_config(page_title="OCR Tester", page_icon="🔍", layout="wide")
st.title("🔍 OCR Tester: Student Answers")
st.caption("Upload PDFs or images of answer scripts, run OCR, and segment text by question numbers.")

with st.sidebar:
    st.header("Settings")
    ocr_prompt = st.text_area(
        "Answer OCR Prompt",
        value=DEFAULT_ANSWER_OCR_PROMPT,
        height=220,
        help="This prompt is sent to GPT-4o for OCR of each image.",
    )
    st.text_input(
        "OpenAI API Key",
        type="password",
        key="openai_api_key",
        placeholder="sk-...",
        help="Used only in this session. Alternatively configure st.secrets or env OPENAI_API_KEY.",
    )
    with st.expander("API Key Status"):
        resolved = resolve_openai_api_key()
        st.caption(f"Resolved key: {get_masked_key_preview(resolved)}")
        if st.button("Validate API Key"):
            status = validate_openai_key_once()
            st.info(status)
    st.caption("Questions will be detected automatically from the OCR text.")
    st.divider()
    st.subheader("OCR Options")
    engine = st.selectbox(
        "OCR Engine",
        options=["GPT-4o", "Tesseract", "Hybrid (Tesseract + GPT-4o)"]
    )
    col1, col2 = st.columns(2)
    grayscale = col1.checkbox("Grayscale", value=True)
    sharpen = col2.checkbox("Sharpen", value=True)
    contrast = st.slider("Contrast", min_value=0.5, max_value=3.0, value=1.4, step=0.1)
    binarize = st.checkbox("Binarize", value=False)
    bin_thr = st.slider("Binarize Threshold", min_value=80, max_value=220, value=180, step=5, disabled=not binarize)
    st.caption("Long image handling")
    slice_tall = st.checkbox("Slice tall images", value=True)
    max_slice_h = st.number_input("Max slice height", min_value=600, max_value=4000, value=1600, step=100)
    slice_overlap = st.number_input("Slice overlap", min_value=0, max_value=400, value=80, step=10)
    scale_to = st.number_input("Scale up to max dimension", min_value=1000, max_value=4000, value=2200, step=100)
    show_previews = st.checkbox("Show image previews", value=False)
    show_raw_ocr = st.checkbox("Show per-image OCR text", value=False)

st.subheader("Upload Answer Scripts")
uploaded = st.file_uploader(
    "Upload PDFs or images",
    type=["pdf", "png", "jpg", "jpeg"],
    accept_multiple_files=True,
)

if uploaded:
    images = process_uploaded_files(uploaded)
    st.info(f"Processed {len(images)} image(s).")

    if show_previews:
        st.markdown("**Previews**")
        cols = st.columns(2)
        for i, img in enumerate(images):
            with cols[i % 2]:
                st.image(img, caption=f"Image {i+1}", use_container_width=True)

    run = st.button("🔄 Run OCR & Segment")
    if run:
        with st.spinner("Running OCR on images..."):
            settings = {
                "engine": engine,
                "grayscale": grayscale,
                "sharpen": sharpen,
                "contrast": float(contrast),
                "binarize": binarize,
                "binarize_threshold": int(bin_thr),
                "slice_tall": slice_tall,
                "max_slice_height": int(max_slice_h),
                "slice_overlap": int(slice_overlap),
                "scale_to_max_dim": int(scale_to),
            }
            extractions = ocr_all_images(images, ocr_prompt, settings)
        st.success("OCR complete.")

        # Summary table
        st.markdown("**Per-Image OCR Summary**")
        st.table([
            {
                "Image #": e["image_number"],
                "Chars": e["character_count"],
                "First 80 chars": (e["extracted_text"] or "")[:80].replace("\n", " ")
            }
            for e in extractions
        ])

        if show_raw_ocr:
            st.markdown("**Raw OCR (per image)**")
            for e in extractions:
                st.text_area(f"Image {e['image_number']} OCR", e.get("extracted_text", ""), height=160)

        # Segment by auto-detected question headers
        st.subheader("Segmented Answers (Auto-detected)")
        segmented = segment_answers_auto(extractions)

        # Display detected questions in order of keys; if 0 exists, treat as fallback "All Text"
        if 0 in segmented and len(segmented) == 1:
            # Only fallback text available
            with st.container(border=True):
                st.markdown("**All Text**")
                st.text_area(
                    "Answer All Text",
                    segmented.get(0, ""),
                    height=220,
                    key="seg_ans_all",
                )
        else:
            # Sort question numbers ascending
            ordered_keys = [k for k in segmented.keys() if k != 0]
            ordered_keys.sort(key=lambda x: int(x))
            if 0 in segmented:
                # Show unlabeled block last
                ordered_keys.append(0)
            for q_num in ordered_keys:
                label = "All Text" if q_num == 0 else f"Question {q_num}"
                with st.container(border=True):
                    st.markdown(f"**{label}**")
                    st.text_area(
                        f"Answer {label}",
                        segmented.get(q_num, ""),
                        height=200,
                        key=f"seg_ans_{q_num}",
                    )

        # Download
        results = {
            "settings": {
                "segmentation": "auto",
            },
            "per_image_ocr": extractions,
            "segmented_answers": segmented,
        }
        st.download_button(
            label="📥 Download JSON",
            data=json.dumps(results, ensure_ascii=False, indent=2),
            file_name="ocr_segmented_answers.json",
            mime="application/json",
        )
else:
    st.info("Upload PDF or image files to begin.")


