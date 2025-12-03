import time
import traceback
import logging
import requests
from fastapi import FastAPI, Request
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._http_client import HttpClient
from youtube_transcript_api.proxies import WebshareProxyConfig

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("transcript-service")

app = FastAPI()

proxy = {
    "http": f"http://txqylbdv:qx2kyqif5zmk@p.webshare.io:80/",
    "https": f"http://txqylbdv:qx2kyqif5zmk@p.webshare.io:80/"
}

headers = {
    "User-Agent": "com.google.android.youtube/19.03.36 (Linux; Android 13; Pixel 7)",
    "X-YouTube-Client-Name": "3",
    "X-YouTube-Client-Version": "19.03.36",
}

TEST_VIDEO_ID = "KLe7Rxkrj94"


@app.get("/transcript")
def get_transcript(video_id: str = TEST_VIDEO_ID):
    logger.info(f"🎬 Fetching transcript for: {video_id}")

    try:
        http_client = HttpClient(lambda url: requests.get(url, headers=headers, proxies=proxy, timeout=10))
        yt = YouTubeTranscriptApi(http_client=http_client)

        fetched = yt.fetch(video_id)
        snippets = fetched.snippets

        logger.info(f"✅ SUCCESS: {len(snippets)} lines received")

        return {
            "success": True,
            "count": len(snippets),
            "preview": [
                {"text": s.text, "start": s.start, "duration": s.duration}
                for s in snippets[:3]
            ]
        }

    except Exception as e:
        logger.error("❌ TRANSCRIPT ERROR:")
        logger.error(traceback.format_exc())
        return {"success": False, "error": str(e)}
