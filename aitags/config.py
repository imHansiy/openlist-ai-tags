import os
import json
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
DATA = Path(os.getenv("AI_DATA_DIR", "data")).resolve()
OPENLIST_URL = os.getenv("OPENLIST_URL", "http://openlist:5244").rstrip("/")
OPENLIST_TOKEN = os.getenv("OPENLIST_TOKEN", "")
OPENLIST_USERNAME = os.getenv("OPENLIST_USERNAME", "admin")
OPENLIST_PASSWORD = os.getenv("OPENLIST_PASSWORD", "")
MODEL_KEY = os.getenv("MODEL_API_KEY", "")
if (DATA / 'model-secret.json').is_file():
    MODEL_KEY = json.loads((DATA / 'model-secret.json').read_text(encoding='utf-8'))['key']
MODEL_URL = os.getenv("MODEL_BASE_URL", "https://api.modelbest.cn/v1").rstrip("/")
MODEL_PROXY = os.getenv("MODEL_PROXY_URL", "")
MODEL_NATIVE_VIDEO = os.getenv("MODEL_NATIVE_VIDEO", "true").lower() in ("1", "true")
MODEL_NAME = os.getenv("MODEL_NAME", "MiniCPM-V-4.7-1B")
FFMPEG = os.getenv("FFMPEG_BIN", "ffmpeg")
FFPROBE = os.getenv("FFPROBE_BIN", "ffprobe")
VIDEO_WORK_MAX_BYTES = int(os.getenv("VIDEO_WORK_MAX_BYTES", str(512 * 1024**2)))
TESSERACT = os.getenv("TESSERACT_BIN", "tesseract")
TESSDATA_DIR = os.getenv("TESSDATA_DIR", "")
SUBTITLE_OCR_CROP = os.getenv("SUBTITLE_OCR_CROP", "0.1,0.87,0.8,0.07")
SUBTITLE_OCR_AUTO_CROP = os.getenv("SUBTITLE_OCR_AUTO_CROP", "true").lower() in ("1","true")
EVIDENCE_CACHE_MAX_BYTES = int(os.getenv("EVIDENCE_CACHE_MAX_BYTES", str(64 * 1024**2)))
EVIDENCE_CACHE_TTL = int(os.getenv("EVIDENCE_CACHE_TTL", "86400"))
# Remote media is only fetched from administrator-approved host patterns.
MEDIA_HOSTS = [x.strip().lower() for x in os.getenv("MEDIA_ALLOWED_HOSTS", "").split(",") if x.strip()]
DEFAULTS = {
    "model_url": MODEL_URL, "model_name": MODEL_NAME,
    "model_thinking": True, "video_num_frames": 32, "context_frames": 5,
    "roots": ["/"], "exclude": [], "extensions": ["mp4", "mkv", "avi", "mov", "webm", "m4v", "ts", "flv"],
    "interval_minutes": 0, "concurrency": 1, "frames": 12,
    "max_video_bytes": 10737418240, "max_network_bytes": 3 * 1024**3 if MODEL_NATIVE_VIDEO else 128 * 1024**2,
    "media_timeout": 1800 if MODEL_NATIVE_VIDEO else 180, "model_timeout": 180, "page_size": 200,
    "max_depth": 64, "max_files": 100000, "scan_delay": 0.3,
}
