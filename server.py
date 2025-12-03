import time
import random
import traceback
import logging
from fastapi import FastAPI
from youtube_transcript_api import YouTubeTranscriptApi, NoTranscriptFound, TranscriptsDisabled
from youtube_transcript_api.proxies import GenericProxyConfig

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

def random_proxy_pair():
    """
    Build HTTP/HTTPS proxy URLs for GenericProxyConfig.
    """
    ip = random.choice(PROXIES)
    http_url = f"http://{USERNAME}:{PASSWORD}@{ip}"
    https_url = f"http://{USERNAME}:{PASSWORD}@{ip}"  # library will tunnel HTTPS through HTTP proxy
    return http_url, https_url


@app.get("/")
def home():
    return {"status": "Online", "proxy_count": len(PROXIES)}


@app.get("/transcript")
def transcript(video_id: str):
    logger.info(f"🎬 Transcript request for {video_id}")

    for attempt in range(1, 6):
        try:
            http_url, https_url = random_proxy_pair()
            logger.info(f"🔄 Proxy attempt {attempt}: http={http_url}, https={https_url}")

            # Configure youtube-transcript-api with GenericProxyConfig
            proxy_config = GenericProxyConfig(
                http_url=http_url,
                https_url=https_url,
            )

            # Instance-based API with proxy
            yt = YouTubeTranscriptApi(proxy_config=proxy_config)

            # 1) Get list of available transcripts (instance method: list)
            transcript_list = yt.list(video_id)

            # 2) Prefer English manual, else auto-generated
            try:
                chosen = transcript_list.find_manually_created_transcript(["en"])
            except Exception:
                chosen = transcript_list.find_generated_transcript(["en"])

            # 3) Fetch actual captions from chosen transcript
            data = chosen.fetch()
            logger.info(f"📄 SUCCESS — {len(data)} items")

            return {
                "success": True,
                "video_id": video_id,
                "items": len(data),
                "preview": data[:3],
                "proxy_used": {
                    "http": http_url,
                    "https": https_url,
                },
                "attempt": attempt,
            }

        except NoTranscriptFound:
            return {"success": False, "error": "No transcript exists for this video"}

        except TranscriptsDisabled:
            return {"success": False, "error": "Captions are disabled for this video"}

        except Exception as e:
            logger.warning(f"⚠️ Proxy failed ({attempt}): {e}")
            logger.debug(traceback.format_exc())
            time.sleep(1)

    return {"success": False, "error": "All proxies failed"}
