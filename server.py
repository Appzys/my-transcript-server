import os
from fastapi import FastAPI
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.proxies import WebshareProxyConfig

app = FastAPI()

# Correct environment key names
proxy = WebshareProxyConfig(
    proxy_username=os.getenv("appzysrc@gmail.com"),
    proxy_password=os.getenv("Appzys@2025"),)

TEST_VIDEO_ID = "KLe7Rxkrj94"


@app.get("/")
def home():
    return {"status": "YouTube Transcript API is running 🚀"}


@app.get("/transcript")
def get_transcript(video_id: str = TEST_VIDEO_ID):
    try:
        transcript = YouTubeTranscriptApi.get_transcript(
            video_id,
            proxy_config=proxy
        )

        return {
            "video_id": video_id,
            "transcript": transcript
        }

    except Exception as e:
        return {"error": str(e)}
