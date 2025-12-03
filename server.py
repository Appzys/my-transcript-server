import time
import traceback
import logging
from fastapi import FastAPI, Request
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.proxies import WebshareProxyConfig

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("transcript-service")

app = FastAPI()

# ---- Webshare proxy (using your current cred values directly for now) ----
proxy = WebshareProxyConfig(
    proxy_username="txqylbdv",
    proxy_password="qx2kyqif5zmk",
)

TEST_VIDEO_ID = "KLe7Rxkrj94"


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    logger.info(f"➡️ Request: {request.method} {request.url}")
    response = await call_next(request)
    logger.info(f"⬅️ Completed in {round(time.time() - start_time, 2)}s")
    return response


@app.get("/")
def home():
    return {"status": "running", "proxy_set": True}


@app.get("/transcript")
def get_transcript(video_id: str = TEST_VIDEO_ID):
    logger.info(f"🎬 Getting transcript for: {video_id}")

    try:
        # ✅ new API style: create instance + .fetch()
        ytt_api = YouTubeTranscriptApi(proxy_config=proxy)
        fetched = ytt_api.fetch(video_id)

        # fetched is a FetchedTranscript object with .snippets list
        snippets = fetched.snippets

        logger.info(f"✅ SUCCESS: {len(snippets)} lines received")

        # Convert snippets to simple list of dicts for Flutter
        simple_snippets = [
            {
                "text": s.text,
                "start": s.start,
                "duration": s.duration,
            }
            for s in snippets
        ]

        return {
            "success": True,
            "video_id": video_id,
            "count": len(simple_snippets),
            "preview": simple_snippets[:3],  # first 3 items
        }

    except Exception as e:
        logger.error("❌ TRANSCRIPT ERROR:")
        logger.error(traceback.format_exc())
        return {
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc(),
        }
