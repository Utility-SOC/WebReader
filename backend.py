import io
import os
import shutil
import base64
import logging
import zipfile
import re
import xml.etree.ElementTree as ET
from typing import List, Optional, Dict, Any, Tuple
import requests
from fastapi import FastAPI, UploadFile, File, HTTPException, Body
from fastapi.responses import JSONResponse, HTMLResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from bs4 import BeautifulSoup

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("SpeedReaderAPI")

# Document parsers
import pdfplumber
import docx
from ebooklib import epub
import pytesseract
from pytesseract import Output

# Configure Tesseract
# Configure Tesseract
# Try to find tesseract in PATH or common locations
TESSERACT_CMD = os.getenv("TESSERACT_CMD")

if not TESSERACT_CMD:
    # Check PATH
    from shutil import which
    tess_in_path = which("tesseract")
    if tess_in_path:
        TESSERACT_CMD = tess_in_path
    else:
        # Check common Windows paths
        common_paths = [
            r"C:\Program Files\Tesseract-OCR\tesseract.exe",
            r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
            os.path.expanduser(r"~\AppData\Local\Programs\Tesseract-OCR\tesseract.exe")
        ]
        for p in common_paths:
            if os.path.exists(p):
                TESSERACT_CMD = p
                break

if TESSERACT_CMD and os.path.exists(TESSERACT_CMD):
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD
    logger.info(f"Tesseract found at: {TESSERACT_CMD}")
else:
    logger.warning("Tesseract executable not found in PATH or common headers. OCR features will fail.")

# Image handling
from PIL import Image

app = FastAPI()

# Allow CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Temp storage for PDF flows
TEMP_DIR = "temp_uploads"
os.makedirs(TEMP_DIR, exist_ok=True)

# Layout Persistence Storage
LAYOUTS_DIR = "layouts"
os.makedirs(LAYOUTS_DIR, exist_ok=True)
import json

def get_layout_path(filename: str) -> str:
    # Sanitize to ensure we don't have path traversal, though filename should be safe from upload
    safe = os.path.basename(filename) + ".json"
    return os.path.join(LAYOUTS_DIR, safe)

def save_layout(filename: str, boxes: Dict[str, Any]):
    try:
        path = get_layout_path(filename)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(boxes, f)
        logger.info(f"Saved layout for {filename}")
    except Exception as e:
        logger.error(f"Failed to save layout: {e}")

def load_layout(filename: str) -> Optional[Dict[str, Any]]:
    try:
        path = get_layout_path(filename)
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load layout: {e}")
    return None

# ----------------------------------------------------------------------------
# LOGIC
# ----------------------------------------------------------------------------

def extract_text_with_ocr(image: Image.Image) -> str:
    """Run OCR on a PIL Image and return text."""
    try:
        # Convert to RGB if needed (handles RGBA, P, etc)
        if image.mode != 'RGB':
            image = image.convert('RGB')
        return pytesseract.image_to_string(image)
    except Exception as e:
        logger.error(f"OCR Error: {e}")
        return ""

def process_text(text: str) -> List[str]:
    """Process text into a list of words, preserving paragraphs."""
    text = text.replace("\r", "\n")
    words = []
    parts = re.split(r'(\n\n)', text)
    for part in parts:
        if part == "\n\n":
            words.append("\n\n")
        else:
            cleaned = part.strip()
            if cleaned:
                words.extend(cleaned.split())
    return words

def extract_text_from_pdf_range(
    path: str, 
    start_page: int, 
    end_page: Optional[int] = None, 
    manual_boxes: Dict[str, Any] = None,
    force_ocr: bool = False
) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Extract text and images from a range of pages in a PDF.
    Returns (extracted_text, extracted_images)
    """
    extracted_text = ""
    extracted_images = []
    
    if manual_boxes is None:
        manual_boxes = {}
        
    try:
        with pdfplumber.open(path) as pdf:
            total_pages = len(pdf.pages)
            if end_page is None or end_page > total_pages:
                end_page = total_pages
                
            for i in range(start_page - 1, end_page):
                page = pdf.pages[i]
                
                boxes = manual_boxes.get(str(i)) # keys are strings in JSON
                
                if not boxes:
                    # AUTOMATIC MODE
                    txt = ""
                    if not force_ocr:
                        txt = page.extract_text(layout=True)
                    
                    if txt and txt.strip():
                        extracted_text += txt + "\n"
                    else:
                        # Fallback/Force OCR
                        logger.info(f"Running OCR on page {i+1}...")
                        try:
                            im = page.to_image(resolution=300).original
                            ocr_txt = extract_text_with_ocr(im)
                            if ocr_txt.strip():
                                extracted_text += ocr_txt + "\n"
                        except Exception as e:
                            logger.error(f"OCR failed for page {i+1}: {e}")
                else:
                    # MANUAL MODE
                    for box in boxes:
                        b_type = box.get('type', 'text')
                        x = float(box['x'])
                        y = float(box['y'])
                        w = float(box['w'])
                        h = float(box['h'])
                        
                        # Calculate PDF coordinates
                        if box.get('relative'):
                             # Relative (0.0 - 1.0)
                            x0 = x * page.width
                            top = y * page.height
                            x1 = (x + w) * page.width
                            bottom = (y + h) * page.height
                        else:
                            # Legacy 100 DPI
                            scale = 0.72
                            x0 = x * scale
                            top = y * scale
                            x1 = (x + w) * scale
                            bottom = (y + h) * scale
                        
                        # Clamp to page dimensions (Snap to edge)
                        x0 = max(0, min(float(page.width), x0))
                        top = max(0, min(float(page.height), top))
                        x1 = max(0, min(float(page.width), x1))
                        bottom = max(0, min(float(page.height), bottom))

                        if x1 <= x0 or bottom <= top: continue
                        crop_box = (x0, top, x1, bottom)
                        
                        try:
                            cropped = page.crop(crop_box)
                            if b_type == 'text':
                                txt = ""
                                if not force_ocr:
                                    txt = cropped.extract_text(layout=True)
                                
                                if txt and txt.strip():
                                    extracted_text += txt + "\n"
                                else:
                                    # OCR on crop
                                    p_img = cropped.to_image(resolution=300).original
                                    ocr_txt = extract_text_with_ocr(p_img)
                                    if ocr_txt.strip():
                                        extracted_text += ocr_txt + "\n"
                                
                            elif b_type == 'image':
                                p_img = cropped.to_image(resolution=150).original
                                img_name = f"Page_{i+1}_Image_{int(x)}_{int(y)}"
                                buff = io.BytesIO()
                                p_img.save(buff, format="PNG")
                                b64 = base64.b64encode(buff.getvalue()).decode("utf-8")
                                extracted_images.append({
                                    "name": img_name,
                                    "src": f"data:image/png;base64,{b64}"
                                })
                                extracted_text += f"\n[FIGURE: {img_name}]\n"
                                
                        except Exception as inner_e:
                            logger.error(f"Box process error on page {i}: {inner_e}")
                            
    except Exception as e:
        logger.error(f"Extraction failed: {e}")
        raise e
        
    return extracted_text, extracted_images

def load_epub_manual(path: str) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Manually unzip and extract text from EPUB, preserving chapter structure.
    Returns (all_text, chapters_metadata)
    """
    try:
        with zipfile.ZipFile(path, 'r') as epub_zip:
            # 1. Find rootfile (OPF)
            # Try standard path first, then search
            container_path = 'META-INF/container.xml'
            if container_path in epub_zip.namelist():
                container_xml = epub_zip.read(container_path).decode('utf-8')
                root = ET.fromstring(container_xml)
                rootfile = root.find(".//{urn:oasis:names:tc:opendocument:xmlns:container}rootfile")
                if rootfile is not None:
                    rootfile_path = rootfile.attrib['full-path']
                else:
                    return "", []
            else:
                 return "", []
            
            # 2. Parse OPF
            opf_content = epub_zip.read(rootfile_path).decode('utf-8')
            opf_root = ET.fromstring(opf_content)
            
            # Namespaces
            ns = {'opf': 'http://www.idpf.org/2007/opf', 'dc': 'http://purl.org/dc/elements/1.1/'}
            # Handle potential different namespaces or absence
            if opf_root.tag.startswith("{"):
                 uri = opf_root.tag.split("}")[0].strip("{")
                 ns['opf'] = uri

            # Manifest (ID -> Href)
            manifest = {}
            m = opf_root.find('opf:manifest', ns)
            if m is None: m = opf_root.find('manifest') # Try without NS
            
            if m is not None:
                for item in m.findall("opf:item", ns) or m.findall("item"):
                    manifest[item.get('id')] = item.get('href')
                
            # Spine (IDREF order)
            spine = opf_root.find('opf:spine', ns)
            if spine is None: spine = opf_root.find('spine')
            
            spine_ids = []
            if spine is not None:
                for item in spine.findall("opf:itemref", ns) or spine.findall("itemref"):
                    spine_ids.append(item.get('idref'))
            
            # Reading Order Paths
            base_dir = os.path.dirname(rootfile_path)
            reading_order = [manifest[idref] for idref in spine_ids if idref in manifest]
            
            all_text = ""
            chapters = []
            import re
            
            for index, item in enumerate(reading_order):
                # Construct path
                full_path = f"{base_dir}/{item}" if base_dir else item
                full_path = full_path.replace("\\", "/") # Zip uses forward slashes
                
                if full_path in epub_zip.namelist():
                    html = epub_zip.read(full_path).decode("utf-8", errors="ignore")
                    soup = BeautifulSoup(html, "html.parser")
                    # Remove scripts/styles
                    for tag in soup(["script", "style"]): tag.decompose()
                    
                    # Extract text
                    chapter_text = soup.get_text(separator=' ', strip=True) + "\n\n"
                    
                    if not chapter_text.strip(): continue

                    # Compute word count for this chapter
                    words_in_chapter = len(re.findall(r'\S+', chapter_text))
                    
                    # Store Metadata
                    current_word_count = len(re.findall(r'\S+', all_text))
                    chapters.append({
                        "title": f"Section {index + 1}", # Potentially parse title from TOC/NCX later
                        "start_index": current_word_count,
                        "word_count": words_in_chapter
                    })
                    
                    all_text += chapter_text
                    
            return all_text, chapters
    except Exception as e:
        logger.error(f"EPUB Error: {e}")
        return "", []

def cleanup_temp():
    """Clean old files if needed. (Optional)"""
    pass

# ----------------------------------------------------------------------------
# API ENDPOINTS
# ----------------------------------------------------------------------------

@app.get("/")
def serve_index():
    if os.path.exists("index.html"):
        with open("index.html", "r", encoding="utf-8") as f:
            return HTMLResponse(f.read())
    return JSONResponse({"error": "index.html not found"}, status_code=404)

@app.get("/health")
def health():
    return {"status": "running"}

@app.post("/upload_temp")
async def upload_temp(file: UploadFile = File(...)):
    """
    Save file to temp storage and return metadata (page count for PDF).
    """
    try:
        # Sanitize filename
        safe_name = os.path.basename(file.filename)
        path = os.path.join(TEMP_DIR, safe_name)
        
        with open(path, "wb") as f:
            f.write(await file.read())
            
        info = {
            "filename": safe_name,
            "path": path,
            "type": "unknown",
            "page_count": 0
        }
        
        if safe_name.lower().endswith(".pdf"):
            info["type"] = "pdf"
            with pdfplumber.open(path) as pdf:
                info["page_count"] = len(pdf.pages)
            
            # Check for saved layout
            saved = load_layout(safe_name)
            if saved:
                info["saved_boxes"] = saved
                
        return info
    except Exception as e:
        logger.error(f"Upload failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/pdf/{filename}/page/{page_num}")
def get_pdf_page_image(filename: str, page_num: int):
    """
    Render a specific PDF page as an image (100 DPI) for the frontend editor.
    """
    path = os.path.join(TEMP_DIR, filename)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="File not found")
        
    try:
        with pdfplumber.open(path) as pdf:
            if page_num < 1 or page_num > len(pdf.pages):
                raise HTTPException(status_code=400, detail="Invalid page number")
            
            page = pdf.pages[page_num - 1]
            # 100 DPI is the standard used in the desktop app
            im = page.to_image(resolution=100).original
            
            img_byte_arr = io.BytesIO()
            im.save(img_byte_arr, format='JPEG', quality=85)
            img_byte_arr = img_byte_arr.getvalue()
            
            return Response(content=img_byte_arr, media_type="image/jpeg")
            
    except Exception as e:
        logger.error(f"Render failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/process_pdf")
def process_pdf_manual(
    filename: str = Body(...),
    manual_boxes: Dict[str, Any] = Body(default={}), # page_idx (str) -> list of boxes
    extract_images: bool = Body(default=False),
    start_page: int = Body(default=1),
    force_ocr: bool = Body(default=False)
):
    """
    Process PDF with optional manual layout boxes.
    """
    path = os.path.join(TEMP_DIR, filename)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="File not found")
        
    try:
        # Persistence: Save the layout if provided
        if manual_boxes and len(manual_boxes) > 0:
            save_layout(filename, manual_boxes)

        extracted_text, extracted_images = extract_text_from_pdf_range(
            path, start_page, end_page=None, manual_boxes=manual_boxes, force_ocr=force_ocr
        )

        # Finalize
        words = process_text(extracted_text)
        return {
            "word_count": len(words),
            "words": words,
            "images": extracted_images
        }

    except Exception as e:
        logger.error(f"Process failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/fetch_url")
async def fetch_url(item: Dict[str, str] = Body(...)):
    """Fetch file from URL and save to temp."""
    url = item.get("url")
    if not url: raise HTTPException(400, "No URL provided")
    
    try:
        # Download (follow redirects to get final URL/headers)
        resp = requests.get(url, stream=True, allow_redirects=True)
        resp.raise_for_status()
        
        # 1. Try filename from Content-Disposition
        filename = ""
        cd = resp.headers.get("Content-Disposition", "")
        if cd:
            # Simple regex to extract filename="..."
            m = re.search(r'filename="?([^";]+)"?', cd)
            if m: filename = m.group(1)
            
        # 2. If no CD, use final URL path
        if not filename:
            from urllib.parse import urlparse
            path = urlparse(resp.url).path
            filename = os.path.basename(path)
            
        if not filename: filename = "downloaded_file"

        # Sanitize
        filename = re.sub(r'[^\w\-_.]', '_', filename)
        
        # 3. Detect Extension / Type
        lower_name = filename.lower()
        content_type = resp.headers.get("Content-Type", "").lower()
        
        ext = ""
        if ".pdf" in lower_name or "application/pdf" in content_type:
            ext = ".pdf"
        elif ".epub" in lower_name or "application/epub" in content_type:
            ext = ".epub"
        elif ".docx" in lower_name or "wordprocessing" in content_type:
            ext = ".docx"
        else:
            ext = ".txt" # Default
            
        # Append extension if missing
        if not lower_name.endswith(ext):
            filename += ext

        path = os.path.join(TEMP_DIR, filename)
        with open(path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
                
        info = {
            "filename": filename,
            "path": path,
            "type": "unknown",
            "page_count": 0,
            "chapters": []
        }
        
        if filename.lower().endswith(".pdf"):
            info["type"] = "pdf"
            with pdfplumber.open(path) as pdf:
                info["page_count"] = len(pdf.pages)
        elif filename.lower().endswith(".epub"):
             info["type"] = "epub"
             # Pre-load to get chapters?
             text, chapters = load_epub_manual(path)
             info["chapters"] = chapters
             info["words"] = process_text(text)
             info["word_count"] = len(info["words"])
                
        return info
        
    except Exception as e:
        logger.error(f"Fetch failed: {e}")
        raise HTTPException(500, str(e))

@app.post("/upload")
async def legacy_upload(file: UploadFile = File(...), force_ocr: bool = False):
    """
    Legacy endpoint for direct text extraction.
    Supports force_ocr param for PDFs.
    """
    content = await file.read()
    filename = file.filename.lower()
    text = ""
    chapters = []
    
    try:
        if filename.endswith(".pdf"):
            with pdfplumber.open(io.BytesIO(content)) as pdf:
                for i, page in enumerate(pdf.pages):
                    t = ""
                    if not force_ocr:
                        t = page.extract_text(layout=True)
                    
                    if t and t.strip():
                        text += t + "\n"
                    else:
                        # Fallback/Force OCR
                        logger.info(f"Running OCR on upload page {i+1}")
                        try:
                            # Render page to image 
                            im = page.to_image(resolution=300).original
                            ocr_txt = extract_text_with_ocr(im)
                            text += ocr_txt + "\n"
                        except Exception as e:
                            logger.error(f"OCR Error page {i}: {e}")
                            
        elif filename.endswith(".txt"):
            text = content.decode("utf-8", errors="ignore")
        elif filename.endswith(".docx"):
            doc = docx.Document(io.BytesIO(content))
            text = "\n".join([p.text for p in doc.paragraphs])
        elif filename.endswith(".epub"):
            # Save temp for epub manual
            tpath = os.path.join(TEMP_DIR, "temp.epub")
            with open(tpath, "wb") as f: f.write(content)
            text, chapters = load_epub_manual(tpath)
        elif filename.endswith((".png", ".jpg", ".jpeg", ".bmp", ".tiff")):
             # Image support
             try:
                 image = Image.open(io.BytesIO(content))
                 text = extract_text_with_ocr(image)
             except Exception as e:
                 logger.error(f"Image OCR failed: {e}")
    
        words = process_text(text)
        return {"words": words, "word_count": len(words), "filename": file.filename, "chapters": chapters}
    
    except Exception as e:
        logger.error(f"Upload processing failed: {e}")
        raise HTTPException(500, f"Processing failed: {str(e)}")

# ----------------------------------------------------------------------------
# TTS
# ----------------------------------------------------------------------------
import subprocess
import shutil
import uuid
import platform

def cleanup_text_for_tts(text: str) -> str:
    """
    Clean text for TTS to improve flow.
    - Replaces single newlines (PDF line wraps) with spaces.
    - Preserves double newlines (paragraph breaks).
    - Insert pauses for paragraphs if needed (engine specific, but \n\n usually works).
    """
    # 1. Normalize line endings
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    
    # 1b. Remove PDF artifacts (cid:12), [FIGURE...], and excessive weird symbols
    text = re.sub(r'\(cid:\d+\)', ' ', text)
    text = re.sub(r'\[FIGURE:.*?\]', ' ', text) # Skip reading figure tags
    
    # 2. Replace single newlines with space (unwrap lines)
    # We use regex to find newlines that are NOT followed by another newline, and NOT preceded by one
    # But simpler: split by \n\n to get paragraphs, then join lines in each paragraph
    paragraphs = text.split("\n\n")
    cleaned_paragraphs = []
    for p in paragraphs:
        # Replace newlines within paragraph with space
        cleaned = p.replace("\n", " ")
        # Collapse multiple spaces
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        if cleaned:
            cleaned_paragraphs.append(cleaned)
            
    # 3. Join paragraphs with hard break chars for TTS (e.g. pipe or period if raw)
    # Windows TTS often treats newline as pause, but let's ensure it's a distinct break.
    # We'll return them joined by double newline.
    return "\n\n".join(cleaned_paragraphs)

def generate_tts_cli(text: str, output_path: str, voice_id: Optional[str] = None):
    """
    Generate TTS using system CLI tools.
    Windows: PowerShell System.Speech
    Linux: espeak / espeak-ng
    """
    # Clean text first
    text = cleanup_text_for_tts(text)
    
    system = platform.system().lower()
    
    if "windows" in system:
        # PowerShell script to generate WAV
        # Escape single quotes in text for PowerShell
        # Escape single quotes in text for PowerShell
        safe_text = text.replace("'", "''")
        
        # Use absolute path and escape specific chars for PowerShell syntax if needed
        # Actually, best to use forward slashes for cross-compatibility or double backslashes
        safe_output_path = os.path.abspath(output_path)
        
        ps_script = f"""
Add-Type -AssemblyName System.Speech
$speak = New-Object System.Speech.Synthesis.SpeechSynthesizer
$outPath = '{safe_output_path}'
$speak.SetOutputToWaveFile($outPath)
# Select voice if provided (basic matching)
if ('{voice_id}' -ne 'None' -and '{voice_id}' -ne '') {{
    try {{ $speak.SelectVoice('{voice_id}') }} catch {{ Write-Host "Voice selection failed: $_" }}
}}
$speak.Speak('{safe_text}')
$speak.Dispose()
"""
        script_path = output_path + ".ps1"
        try:
            # Use utf-8-sig (BOM) so PowerShell 5.1+ reads the encoding correctly
            with open(script_path, "w", encoding="utf-8-sig") as f:
                f.write(ps_script)
            
            # Run it
            process = subprocess.run(
                ["powershell", "-ExecutionPolicy", "Bypass", "-File", script_path], 
                check=True, 
                capture_output=True, 
                text=True
            )
        except subprocess.CalledProcessError as e:
            logger.error(f"TTS Generation failed. Stdout: {e.stdout} \nStderr: {e.stderr}")
            raise Exception(f"TTS Backend Error: {e.stderr}")
        finally:
            if os.path.exists(script_path):
                os.remove(script_path)
                
    elif "linux" in system:
        # Use espeak
        cmd = ["espeak", "-w", output_path, text]
        if voice_id:
            cmd.extend(["-v", voice_id])
        subprocess.run(cmd, check=True)
    else:
        raise Exception("Unsupported OS for CLI TTS")

@app.post("/tts")
def generate_tts(
    text: str = Body(..., embed=True),
    voice_id: Optional[str] = Body(default=None, embed=True)
):
    """
    Generate TTS audio for the given text.
    Returns a WAV audio file.
    """
    if not text:
        raise HTTPException(400, "Text is required")
        
    output_filename = f"tts_{uuid.uuid4()}.wav"
    output_path = os.path.join(TEMP_DIR, output_filename)
    
    try:
        # Run CLI generation
        # This is blocking safely because it's in a subprocess
        generate_tts_cli(text, output_path, voice_id)
            
        if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
             raise Exception("TTS file was not created or empty.")
             
        # Read back and return
        with open(output_path, "rb") as f:
            audio_data = f.read()
            
        # Cleanup
        try:
             os.remove(output_path)
        except:
             pass
             
        return Response(content=audio_data, media_type="audio/wav")
        
    except Exception as e:
        logger.error(f"TTS Generation failed: {e}")
        # Cleanup output if failed
        if os.path.exists(output_path):
            try: os.remove(output_path)
            except: pass
        raise HTTPException(500, f"TTS Failed: {e}")

@app.get("/tts/voices")
def get_voices():
    """List available system voices (Best effort)."""
    voices_list = []
    system = platform.system().lower()
    
    try:
        if "windows" in system:
             # Use PowerShell to list voices
             # We write to a temp file to avoid command-line quoting issues
             script_name = f"list_voices_{uuid.uuid4()}.ps1"
             script_path = os.path.join(TEMP_DIR, script_name)
             
             ps_script = """
Add-Type -AssemblyName System.Speech
$speak = New-Object System.Speech.Synthesis.SpeechSynthesizer
$speak.GetInstalledVoices() | ForEach-Object {
    $v = $_.VoiceInfo
    Write-Output "$($v.Name)|$($v.Id)|$($v.Culture)"
}
"""
             try:
                 with open(script_path, "w", encoding="utf-8") as f:
                     f.write(ps_script)
                 
                 res = subprocess.run(
                     ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", script_path], 
                     capture_output=True, 
                     text=True
                 )
                 
                 if res.stderr:
                     logger.warning(f"PowerShell stderr: {res.stderr}")
                     
                 lines = res.stdout.strip().split("\n")
                 for line in lines:
                     parts = line.strip().split("|")
                     if len(parts) >= 2:
                         voices_list.append({
                             "name": parts[0],
                             "id": parts[0],
                             "lang": parts[2] if len(parts) > 2 else ""
                         })
             finally:
                 if os.path.exists(script_path):
                     os.remove(script_path)
                     
        elif "linux" in system:
             # espeak --voices
             # Pty Language Age/Gender VoiceName File Other Langs
             try:
                 res = subprocess.run(["espeak", "--voices"], capture_output=True, text=True)
                 lines = res.stdout.strip().split("\n")
                 # Skip header
                 if len(lines) > 1:
                     for line in lines[1:]:
                         parts = line.split()
                         if len(parts) >= 4:
                             # This is rough parsing, but usually works for espeak
                             # parts[1] is lang, parts[3] is name
                             name = parts[3]
                             lang = parts[1]
                             voices_list.append({
                                 "name": f"espeak {name}",
                                 "id": name,
                                 "lang": lang
                             })
             except FileNotFoundError:
                 pass # espeak might not be installed

        # Ensure at least one option exists
        if not voices_list:
            voices_list.append({"name": "System Default", "id": "", "lang": "en"})
        else:
            # prepend Default option
            voices_list.insert(0, {"name": "System Default", "id": "", "lang": "en"})

        return {"voices": voices_list}
    except Exception as e:
         return {"error": str(e), "voices": []}

@app.post("/tts/download")
def download_tts(
    filename: str = Body(...),
    start_page: int = Body(1),
    end_page: Optional[int] = Body(None),
    voice_id: Optional[str] = Body(None),
    manual_boxes: Optional[Dict[str, Any]] = Body(None),
    force_ocr: bool = Body(False)
):
    """
    Generate audio for a PDF page range and return as a downloadable file.
    """
    path = os.path.join(TEMP_DIR, filename)
    if not os.path.exists(path):
        raise HTTPException(404, "File not found")
        
    try:
        # Extract text using the shared helper
        text, _ = extract_text_from_pdf_range(
            path, 
            start_page=start_page, 
            end_page=end_page, 
            manual_boxes=manual_boxes,
            force_ocr=force_ocr
        )
        
        if not text.strip():
            raise HTTPException(400, "No text extracted from the specified range.")
            
        # Generate Audio
        output_filename = f"tts_download_{uuid.uuid4()}.wav"
        output_path = os.path.join(TEMP_DIR, output_filename)
        
        generate_tts_cli(text, output_path, voice_id)
        
        if not os.path.exists(output_path):
             raise Exception("Audio generation failed.")
             
        # Use FileResponse for direct download with filename
        from fastapi.responses import FileResponse
        return FileResponse(
            output_path, 
            media_type="audio/wav", 
            filename=f"{filename}_pg{start_page}-{end_page or 'end'}.wav",
            background=None # We could add a background task to delete it, but temp cleanup is separate
        )
        
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"TTS Download failed: {e}")
        raise HTTPException(500, f"Failed: {e}")


@app.get("/pdf/{filename}/layout")
def get_pdf_layout(filename: str):
    """Retrieve saved layout if exists."""
    layout = load_layout(filename)
    if layout:
        return {"layout": layout}
    return {"layout": None}