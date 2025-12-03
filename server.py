import os
import traceback
from fastapi import FastAPI
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.proxies import WebshareProxyConfig

app = FastAPI()

# ---- DEBUG: Print environment and config status ----
def debug_state():
    return {
        "WS_USERNAME_SET": os.getenv("WS_USERNAME") is not None,
        "WS_PASSWORD_SET": os.getenv("WS_PASSWORD") is not None,
        "username_value_preview": (os.getenv("WS_USERNAME")[:3] + "***") if os.getenv("WS_USERNAME") else None,
        "proxy_mode": "enabled" if os.getenv("WS_USERNAME") and os.getenv("WS_PASSWORD") else "disabled"
    }

# ---- Proxy configuration using proper environment variables ----
proxy = WebshareProxyConfig(
    proxy_username=os.getenv("txqylbdv"),
    proxy_password=os.getenv("qx2kyqif5zmk"),
)

TEST_VIDEO_ID = "KLe7Rxkrj94"


@app.get("/")
def home():
    return {
        "status": "YouTube Transcript API is running 🚀",
        "proxy_status": debug_state(),
    }


@app.get("/transcript")
def get_transcript(video_id: str = TEST_VIDEO_ID):
    debug_output = {
        "requested_video_id": video_id,
        "proxy_status": debug_state(),
    }

    try:
        transcript = YouTubeTranscriptApi.get_transcript(
            video_id,
            proxy_config=proxy
        )

        debug_output["success"] = True
        debug_output["transcript_length"] = len(transcript)
        debug_output["transcript_preview"] = transcript[:3]  # show first 3 entries

        return debug_output

    except Exception as e:
        return {
            "error": str(e),
            "traceback": traceback.format_exc(),
            "debug_state": debug_state(),
        }
