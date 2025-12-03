import time
import random
import traceback
import logging
import requests
from fastapi import FastAPI, Request
from youtube_transcript_api import YouTubeTranscriptApi, NoTranscriptFound

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("transcript-service")

app = FastAPI()

USERNAME = "txqylbdv"
PASSWORD = "qx2kyqif5zmk"

# 🔥 Your full proxy pool
PROXY_LIST = [
    "142.111.48.253:7030",
    "31.59.20.176:6754",
    "23.95.150.145:6114",
    "198.23.239.134:6540",
    "107.172.163.27:6543",
    "198.105.121.200:6462",
    "64.137.96.74:6641",
    "84.247.60.125:6095",
    "216.10.27.159:6837",
    "142.111.67.146:5611",
]


def get_random_proxy():
    ip = random.choice(PROXY_LIST)
    proxy_url = f"http://{USERNAME}:{PASSWORD}@{ip}/"
    logger.info(f"🔄 Using Proxy: {proxy_url}")
    return {"http": proxy_url, "https": proxy_url}


HEADERS = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 13; Pixel 7)",
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
    return {
        "status": "running",
        "proxy_count": len(PROXY_LIST),
    }


@app.get("/transcript")
def get_transcript(video_id: str = TEST_VIDEO_ID):
    logger.info(f"🎬 Fetching transcript for: {video_id}")

    for attempt in range(1, 6):  # Try 5 different proxies
        try:
            proxy = get_random_proxy()

            session = requests.Session()
            session.headers.update(HEADERS)
            session.proxies.update(proxy)

            yt = YouTubeTranscriptApi(http_client=session)
            transcript = yt.get_transcript(video_id)

            logger.info(f"📄 SUCCESS after {attempt} attempt(s): {len(transcript)} lines")

            return {
                "success": True,
                "video_id": video_id,
                "count": len(transcript),
                "preview": transcript[:3],
                "used_proxy": proxy,
                "attempts": attempt,
            }

        except NoTranscriptFound:
            return {"success": False, "error": "No transcript available"}

        except Exception as e:
            logger.warning(f"⚠️ Proxy failed on attempt {attempt}: {e}")
            time.sleep(1)

    # If all proxies fail
    return {
        "success": False,
        "error": "All proxies failed — YouTube blocked requests",
        "trace": traceback.format_exc(),
    }
