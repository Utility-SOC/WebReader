import io
import os
import shutil
import base64
import logging
import zipfile
import re
from typing import List, Optional, Dict, Any, Tuple
import requests
from fastapi import FastAPI, UploadFile, File, HTTPException, Body, Depends
from fastapi.responses import JSONResponse, HTMLResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

# Internal imports
# Internal imports
from database import engine, get_db, Base
from models import Document, ProcessingTask, TaskStatus
from utils import (
    extract_text_from_pdf_range, 
    process_text, 
    load_epub_manual, 
    extract_text_with_ocr, 
    TESSERACT_CMD
)
from tasks import process_pdf_task

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("SpeedReaderAPI")

# Create Tables
Base.metadata.create_all(bind=engine)

# Document parsers (still needed for some direct checks)
import pdfplumber
import docx
from PIL import Image

app = FastAPI()

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
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Path Resolution Fix for Docker vs Local
# In Docker, we are in /app, and temp_uploads is in /app/temp_uploads (mounted)
# Locally, we are in .../backend, and temp_uploads is .../temp_uploads (sibling)
if os.path.isdir(os.path.join(BASE_DIR, "temp_uploads")):
    ROOT_DIR = BASE_DIR
    TEMP_DIR = os.path.join(BASE_DIR, "temp_uploads")
    LAYOUTS_DIR = os.path.join(BASE_DIR, "layouts")
else:
    ROOT_DIR = os.path.dirname(BASE_DIR)
    TEMP_DIR = os.path.join(ROOT_DIR, "temp_uploads")
    LAYOUTS_DIR = os.path.join(ROOT_DIR, "layouts")

os.makedirs(TEMP_DIR, exist_ok=True)
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



def cleanup_temp():
    """Clean old files if needed. (Optional)"""
    pass

# ----------------------------------------------------------------------------
# API ENDPOINTS
# ----------------------------------------------------------------------------

@app.get("/")
def api_root():
    return {"message": "WebReader API", "version": "1.0"}

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
async def upload_document(
    file: UploadFile = File(...), 
    force_ocr: bool = False,
    db: Session = Depends(get_db)
):
    """
    Async upload endpoint. Saves file, triggers Celery task, returns task_id.
    """
    try:
        # 1. Save File
        safe_name = os.path.basename(file.filename)
        path = os.path.join(TEMP_DIR, safe_name)
        with open(path, "wb") as f:
            f.write(await file.read())
            
        file_type = "unknown"
        if safe_name.lower().endswith(".pdf"): file_type = "pdf"
        elif safe_name.lower().endswith(".epub"): file_type = "epub"
        elif safe_name.lower().endswith(".txt"): file_type = "txt"
        
        # 2. Create Document Record
        doc = Document(
            filename=safe_name,
            file_path=path,
            file_type=file_type
        )
        db.add(doc)
        db.commit()
        db.refresh(doc)
        
        # 3. Trigger Task
        # We pass the doc.id so the task can retrieve the file path and update the record
        task_res = process_pdf_task.delay(
            document_id=doc.id, 
            force_ocr=force_ocr
        )
        
        # 4. Create Task Record
        task_record = ProcessingTask(
            id=task_res.id,
            document_id=doc.id,
            status=TaskStatus.PENDING
        )
        db.add(task_record)
        db.commit()
        
        return {"task_id": task_res.id, "document_id": doc.id, "message": "Processing started"}
        
    except Exception as e:
        logger.error(f"Async upload failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/tasks/{task_id}")
def get_task_status(task_id: str, db: Session = Depends(get_db)):
    """
    Check status of a background task.
    """
    task = db.query(ProcessingTask).filter(ProcessingTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
        
    response = {
        "id": task.id,
        "status": task.status,
        "error": task.error_message
    }
    
    if task.status == TaskStatus.COMPLETED:
        # Include result directly here or a link to it
        doc = db.query(Document).filter(Document.id == task.document_id).first()
        if doc and doc.content:
            response["result"] = doc.content
            
    return response

@app.post("/legacy_upload")
async def legacy_upload(file: UploadFile = File(...), force_ocr: bool = False):
    """
    Legacy endpoint for direct text extraction (Synchronous).
    Kept for backward compatibility or simple testing.
    """
    content = await file.read()
    filename = file.filename.lower()
    text = ""
    chapters = []
    
    try:
        # Use simple temp save to reuse the utils logic
        tpath = os.path.join(TEMP_DIR, f"legacy_{file.filename}")
        with open(tpath, "wb") as f: f.write(content)
        
        if filename.endswith(".pdf"):
            text, _ = extract_text_from_pdf_range(tpath, 1, force_ocr=force_ocr)
        elif filename.endswith(".epub"):
            text, chapters = load_epub_manual(tpath)
        elif filename.endswith(".txt"):
            text = content.decode("utf-8", errors="ignore")
        # ... other types omitted for brevity in legacy
    
        words = process_text(text)
        return {"words": words, "word_count": len(words), "filename": file.filename, "chapters": chapters}
    
    except Exception as e:
        logger.error(f"Legacy upload failed: {e}")
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

    # 1c. Aggressive Sanitization for Shell Safety
    # Remove backticks (PowerShell escape), dollar signs (variable expansion), and other risky symbols
    # We allow basic punctuation, letters, numbers, and common safe symbols
    # This prevents "Unexpected token" errors in PowerShell
    text = re.sub(r'[`$]', '', text) 
    
    # Optional: Replace weird quotes with standard ones
    text = text.replace('‘', "'").replace('’', "'").replace('“', '"').replace('”', '"')
    
    # Remove anything that isn't alphanumeric or basic punctuation
    # This is slightly heavy-handed but ensures stability for CLI TTS
    # text = re.sub(r'[^\w\s.,?!:;\'\"()-]', ' ', text) # Too aggressive for some languages?
    # Let's just remove the known breakers for now:
    text = re.sub(r'[^\x00-\x7F]+', ' ', text) # Strip non-ASCII if we really want to be safe, or just...
    # Better: just strip the known shell-breakers that we missed.
    # The backtick and $ removal above covers the main PowerShell issues.
    
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
        # Check if manual_boxes not provided, try to load from disk
        if not manual_boxes:
            loaded = load_layout(filename)
            if loaded:
                logger.info(f"TTS Download: Loaded saved layout for {filename}")
                manual_boxes = loaded

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