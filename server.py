import time
import traceback
import logging
import requests
from fastapi import FastAPI, Request
from youtube_transcript_api import YouTubeTranscriptApi

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("transcript-service")

app = FastAPI()

# ---- Proxy (Webshare) ----
PROXY_USER = "txqylbdv"
PROXY_PASS = "qx2kyqif5zmk"

proxy_url = f"http://{PROXY_USER}:{PROXY_PASS}@p.webshare.io:80/"

proxies = {
    "http": proxy_url,
    "https": proxy_url,
}

# ---- Fake Android headers (needed to bypass YouTube rate limits) ----
headers = {
    "User-Agent": "com.google.android.youtube/19.03.36 (Linux; Android 13; Pixel 7)",
    "X-YouTube-Client-Name": "3",
    "X-YouTube-Client-Version": "19.03.36",
}

TEST_VIDEO_ID = "KLe7Rxkrj94"


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.time()
    logger.info(f"➡️ {request.method} {request.url}")
    
    response = await call_next(request)
    
    logger.info(f"⬅️ Done in {round(time.time() - start, 2)}s")
    return response


@app.get("/")
def home():
    return {"status": "Running", "proxy": True, "client": "Android Spoofed"}


@app.get("/transcript")
def get_transcript(video_id: str = TEST_VIDEO_ID):
    logger.info(f"🎬 Fetching: {video_id}")

    try:
        # Create a custom requests session
        session = requests.Session()
        session.proxies.update(proxies)
        session.headers.update(headers)

        # Patch the transcript API to use this session
        yt = YouTubeTranscriptApi(http_client=session)

        # Call fetch()
        fetched = yt.fetch(video_id)
        snippets = fetched.snippets

        logger.info(f"📄 SUCCESS: {len(snippets)} lines fetched")

        return {
            "success": True,
            "video_id": video_id,
            "count": len(snippets),
            "preview": [
                {"text": s.text, "start": s.start, "duration": s.duration}
                for s in snippets[:3]
            ]
        }

    except Exception as e:
        logger.error("❌ ERROR")
        logger.error(traceback.format_exc())
        return {"success": False, "error": str(e), "trace": traceback.format_exc()}
