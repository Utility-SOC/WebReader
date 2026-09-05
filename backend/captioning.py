"""
Florence-2 image captioning for WebReader.

Runs on CPU (no GPU expected in deployment), so this is written for that
constraint specifically -- see the memory-safety notes below. The model is
loaded lazily and cached at module scope: a Celery worker process loads it
once on the first image it needs to caption, then reuses it for the rest of
that worker's lifetime, rather than reloading per-task.

Design notes learned from hardening this on real hardware:
  - Dynamic INT8 quantization of the model's Linear layers cuts peak RSS
    roughly in half (~4.2GB -> ~2.3GB observed) and is the correct approach
    for CPU-only inference (bitsandbytes 4/8-bit quantization is
    GPU-oriented and doesn't help here).
  - The quantized backend matters: some CPUs (including budget/older ones,
    and some virtualized/emulated environments) lack AVX2/AVX512, and the
    default `onednn` backend issues instructions those CPUs don't support,
    crashing with SIGILL. `qnnpack` is the portable backend.
  - Florence-2's bundled custom modeling code (via trust_remote_code)
    predates transformers' current Cache-object KV cache and breaks against
    a current transformers version. use_cache=False works around it at the
    cost of some speed.
  - Images are downscaled before inference; a full-resolution photo isn't
    needed for a caption and holding several in memory at once is a big part
    of how this blew past 4GB in earlier testing.

This module deliberately does NOT impose a process-wide memory limit
(resource.setrlimit) the way the standalone test script does -- this code
runs inside the shared Celery worker process alongside PDF/OCR tasks that
may legitimately need more memory for large documents, and capping the
whole process here would constrain unrelated work. Instead, the container
itself is memory-capped in docker-compose.yml (`mem_limit` on the worker
service), so a runaway captioning task gets that container recycled by
Docker rather than affecting the host.
"""

import logging
import threading

import torch
from PIL import Image
from transformers import AutoModelForCausalLM, AutoProcessor

logger = logging.getLogger("SpeedReaderUtils")

# Default backend (onednn) requires AVX2/AVX512; qnnpack works everywhere.
torch.backends.quantized.engine = "qnnpack"

MODEL_ID = "microsoft/Florence-2-base"
TASK_PROMPT = "<DETAILED_CAPTION>"
MAX_IMAGE_SIDE = 1024

_lock = threading.Lock()
_model = None
_processor = None


def _load():
    global _model, _processor
    logger.info(f"Loading {MODEL_ID} for image captioning (first use this worker)...")
    model = AutoModelForCausalLM.from_pretrained(
        MODEL_ID,
        torch_dtype=torch.float32,
        attn_implementation="eager",  # flash-attn needs a GPU
        trust_remote_code=True,
    )
    model.eval()
    model = torch.ao.quantization.quantize_dynamic(
        model, {torch.nn.Linear}, dtype=torch.qint8
    )
    processor = AutoProcessor.from_pretrained(MODEL_ID, trust_remote_code=True)
    _model, _processor = model, processor
    logger.info("Captioning model ready.")


def _get_model():
    if _model is None:
        with _lock:
            if _model is None:  # re-check inside the lock
                _load()
    return _model, _processor


@torch.inference_mode()
def caption_image(image: Image.Image) -> str:
    """Caption a PIL image. Returns "" on any failure -- captioning is an
    enhancement to document processing, not something that should fail the
    whole task if the model has a bad day on a particular image."""
    try:
        model, processor = _get_model()

        img = image.convert("RGB")
        if max(img.size) > MAX_IMAGE_SIDE:
            img.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE), Image.LANCZOS)

        inputs = processor(text=TASK_PROMPT, images=img, return_tensors="pt")
        generated_ids = model.generate(
            input_ids=inputs["input_ids"],
            pixel_values=inputs["pixel_values"],
            max_new_tokens=256,
            num_beams=3,
            do_sample=False,
            use_cache=False,
        )
        generated_text = processor.batch_decode(generated_ids, skip_special_tokens=False)[0]
        parsed = processor.post_process_generation(
            generated_text, task=TASK_PROMPT, image_size=img.size
        )
        return parsed[TASK_PROMPT].strip()
    except Exception as e:
        logger.error(f"Captioning failed: {e}")
        return ""
