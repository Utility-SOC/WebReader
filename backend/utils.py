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
import winreg
from PIL import Image
import pdfplumber
import docx
import pytesseract
from pytesseract import Output

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("SpeedReaderUtils")

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
            os.path.expandvars(r"%LOCALAPPDATA%\Tesseract-OCR\tesseract.exe")
        ]
        for p in common_paths:
            if os.path.exists(p):
                TESSERACT_CMD = p
                # Add to PATH so subprocess usage (shutil.which) works later
                os.environ["PATH"] += os.pathsep + os.path.dirname(p)
                break

    if not TESSERACT_CMD:
        # Check Registry (HKLM/HKCU)
        try:
            search_terms = ["tesseract-ocr", "tesseract"]
            roots = [
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
                (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Uninstall")
            ]
            for hive, subkey_root in roots:
                try:
                    with winreg.OpenKey(hive, subkey_root) as key:
                        for i in range(0, winreg.QueryInfoKey(key)[0]):
                            try:
                                subkey_name = winreg.EnumKey(key, i)
                                with winreg.OpenKey(key, subkey_name) as sub:
                                    try:
                                        dn, _ = winreg.QueryValueEx(sub, "DisplayName")
                                        if any(s in str(dn).lower() for s in search_terms):
                                            # Try InstallLocation
                                            try:
                                                loc, _ = winreg.QueryValueEx(sub, "InstallLocation")
                                                if loc:
                                                    exe = os.path.join(loc, "tesseract.exe")
                                                    if os.path.exists(exe):
                                                        TESSERACT_CMD = exe
                                                        break
                                            except: pass
                                            # Try UninstallString
                                            try:
                                                uninst, _ = winreg.QueryValueEx(sub, "UninstallString")
                                                if uninst:
                                                    uninst = uninst.replace('"', '').replace("'", "")
                                                    loc = os.path.dirname(uninst)
                                                    exe = os.path.join(loc, "tesseract.exe")
                                                    if os.path.exists(exe):
                                                        TESSERACT_CMD = exe
                                                        break
                                            except: pass
                                    except: pass
                            except: pass
                        if TESSERACT_CMD: break
                except: pass
                if TESSERACT_CMD: break
        except Exception as e:
            logger.warning(f"Registry check failed: {e}")

    if TESSERACT_CMD:
        # Add to PATH so subprocess checks work
        os.environ["PATH"] += os.pathsep + os.path.dirname(TESSERACT_CMD)

if TESSERACT_CMD and os.path.exists(TESSERACT_CMD):
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD
    logger.info(f"Tesseract found at: {TESSERACT_CMD}")
else:
    logger.warning("Tesseract executable not found in PATH or common headers. OCR features will fail.")


def extract_text_with_ocr(image: Image.Image) -> str:
    """Run OCR on a PIL Image and return text."""
    try:
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
                        txt = page.extract_text(layout=True, x_tolerance=1)
                    
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
                                    txt = cropped.extract_text(layout=True, x_tolerance=1)
                                
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
            container_path = 'META-INF/container.xml'
            if container_path in epub_zip.namelist():
                container_xml = epub_zip.read(container_path).decode('utf-8')
                root = ET.fromstring(container_xml)
                rootfile = root.find(".//{urn:oasis:names:tc:opendocument:xmlns:container}rootfile")
                rootfile_path = rootfile.attrib['full-path'] if rootfile is not None else ""
            else:
                return "", []
            
            if not rootfile_path: return "", []

            opf_content = epub_zip.read(rootfile_path).decode('utf-8')
            opf_root = ET.fromstring(opf_content)
            
            ns = {'opf': 'http://www.idpf.org/2007/opf', 'dc': 'http://purl.org/dc/elements/1.1/'}
            if opf_root.tag.startswith("{"):
                 uri = opf_root.tag.split("}")[0].strip("{")
                 ns['opf'] = uri

            manifest = {}
            m = opf_root.find('opf:manifest', ns)
            if m is None: m = opf_root.find('manifest')
            
            if m is not None:
                for item in m.findall("opf:item", ns) or m.findall("item"):
                    manifest[item.get('id')] = item.get('href')
                
            spine = opf_root.find('opf:spine', ns)
            if spine is None: spine = opf_root.find('spine')
            
            spine_ids = []
            if spine is not None:
                for item in spine.findall("opf:itemref", ns) or spine.findall("itemref"):
                    spine_ids.append(item.get('idref'))
            
            base_dir = os.path.dirname(rootfile_path)
            reading_order = [manifest[idref] for idref in spine_ids if idref in manifest]
            
            all_text = ""
            chapters = []
            import re
            
            current_word_count = 0
            
            for index, item in enumerate(reading_order):
                full_path = f"{base_dir}/{item}" if base_dir else item
                full_path = full_path.replace("\\", "/")
                
                if full_path in epub_zip.namelist():
                    html = epub_zip.read(full_path).decode("utf-8", errors="ignore")
                    from bs4 import BeautifulSoup
                    soup = BeautifulSoup(html, "html.parser")
                    for tag in soup(["script", "style"]): tag.decompose()
                    
                    chapter_text = soup.get_text(separator=' ', strip=True) + "\n\n"
                    if not chapter_text.strip(): continue

                    words_in_chapter = len(re.findall(r'\S+', chapter_text))
                    
                    chapters.append({
                        "title": f"Section {index + 1}",
                        "start_index": current_word_count,
                        "word_count": words_in_chapter
                    })
                    current_word_count += words_in_chapter
                    all_text += chapter_text
                    
            return all_text, chapters
    except Exception as e:
        logger.error(f"EPUB Error: {e}")
        return "", []

def load_mobi_manual(path: str) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Extract MOBI/AZW3 files using mobi and process the resulting EPUB or HTML.
    """
    import mobi
    try:
        tempdir, extracted_path = mobi.extract(path)
        try:
            if extracted_path.endswith(".epub"):
                return load_epub_manual(extracted_path)
            elif extracted_path.endswith(".html"):
                with open(extracted_path, 'r', encoding='utf-8', errors='ignore') as f:
                    html = f.read()
                from bs4 import BeautifulSoup
                import re
                soup = BeautifulSoup(html, "html.parser")
                for tag in soup(["script", "style"]): tag.decompose()
                
                text = soup.get_text(separator=' ', strip=True) + "\n\n"
                words_in_chapter = len(re.findall(r'\S+', text))
                
                chapters = [{
                    "title": "MOBI Content",
                    "start_index": 0,
                    "word_count": words_in_chapter
                }]
                return text, chapters
            else:
                logger.warning(f"MOBI extracted to unsupported format: {extracted_path}")
                return "", []
        finally:
            import shutil
            shutil.rmtree(tempdir, ignore_errors=True)
    except Exception as e:
        logger.error(f"MOBI Error: {e}")
        return "", []

def process_image_file(path: str) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Process a single image file (PNG, JPG, WEBP) and return OCR text.
    Returns (text, []) - no extracted images list needed for a single image usually, 
    but we could return the image itself as an 'extracted image' if desired.
    """
    try:
        from PIL import Image
        img = Image.open(path)
        text = extract_text_with_ocr(img)
        return text, []
    except Exception as e:
        logger.error(f"Image Processing Error: {e}")
        return "", []
