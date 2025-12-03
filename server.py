import time
import random
import traceback
import logging
import requests
from fastapi import FastAPI
from youtube_transcript_api import YouTubeTranscriptApi, NoTranscriptFound, TranscriptsDisabled

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("yt-proxy")

app = FastAPI()

USERNAME = "txqylbdv"
PASSWORD = "qx2kyqif5zmk"

PROXIES = [
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

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 13; Pixel 7)",
    "X-YouTube-Client-Name": "3",
    "X-YouTube-Client-Version": "19.03.36"
}

def random_proxy():
    ip = random.choice(PROXIES)
    proxy = f"http://{USERNAME}:{PASSWORD}@{ip}/"
    return {"http": proxy, "https": proxy}


@app.get("/")
def home():
    return {"status": "Online", "proxy_count": len(PROXIES)}


@app.get("/transcript")
def transcript(video_id: str):
    logger.info(f"🎬 Transcript request for {video_id}")

    for attempt in range(1, 6):
        try:
            proxy = random_proxy()
            logger.info(f"🔄 Proxy attempt {attempt}: {proxy}")

            session = requests.Session()
            session.headers.update(HEADERS)
            session.proxies.update(proxy)

            yt = YouTubeTranscriptApi(http_client=session)

            # NEW API METHOD (works in 2024–2025)
            transcripts = yt.list_transcripts(video_id)

            # Prefer English manual, else auto-generated
            try:
                chosen = transcripts.find_manually_created_transcript(["en"])
            except:
                chosen = transcripts.find_generated_transcript(["en"])

            data = chosen.fetch()
            logger.info(f"📄 SUCCESS — {len(data)} items")

            return {
                "success": True,
                "video_id": video_id,
                "items": len(data),
                "preview": data[:3],
                "proxy_used": proxy,
                "attempt": attempt
            }

        except NoTranscriptFound:
            return {"success": False, "error": "No transcript exists"}

        except TranscriptsDisabled:
            return {"success": False, "error": "Captions disabled"}

        except Exception as e:
            logger.warning(f"⚠️ Proxy failed ({attempt}): {e}")
            time.sleep(1)

    return {"success": False, "error": "All proxies failed"}
