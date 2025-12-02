import os
from fastapi import FastAPI
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.proxies import WebshareProxyConfig

app = FastAPI()

# Load credentials from environment variables
proxy = WebshareProxyConfig(
    proxy_username=os.getenv("appzysrc@gmail.com"),
    proxy_password=os.getenv("Appzys@2025"),
)

# Test video
TEST_VIDEO_ID = "KLe7Rxkrj94"


@app.get("/")
def home():
    return {"status": "YouTube Transcript API is running 🚀"}


@app.get("/transcript")
def get_transcript(video_id: str = TEST_VIDEO_ID):
    try:
        ytt = YouTubeTranscriptApi(proxy_config=proxy)
        transcript = ytt.get_transcript(video_id)
        return {
            "video_id": video_id,
            "transcript": transcript
        }
    except Exception as e:
        return {"error": str(e)}
