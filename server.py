import traceback
import logging
import requests
import re
from fastapi import FastAPI, Request, HTTPException
import xml.etree.ElementTree as ET

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
log = logging.getLogger("yt-rev")

app = FastAPI()
API_KEY = "x9J2f8S2pA9W-qZvB"


# -----------------------------------------
# 1) Extract fresh Innertube API Key
# -----------------------------------------
def extract_key(video_id):
    log.info("🕵 Extracting API key from HTML...")
    html = requests.get(f"https://www.youtube.com/watch?v={video_id}",
                        headers={"User-Agent": "Mozilla/5.0"}).text
    match = re.search(r'"INNERTUBE_API_KEY":"([^"]+)"', html)
    if not match:
        raise Exception("❌ Failed to extract INNERTUBE_API_KEY")
    key = match.group(1)
    log.info(f"🔑 Key extracted: {key[:15]}...")
    return key


# -----------------------------------------
# 2) Get Caption Track List
# -----------------------------------------
def get_tracks(video_id):

    log.info(f"📥 Getting track list for {video_id}")

    key = extract_key(video_id)

    url = f"https://youtubei.googleapis.com/youtubei/v1/player?key={key}"

    payload = {
        "context": {
            "client": {
                "clientName": "ANDROID",
                "clientVersion": "19.08.35",
                "androidSdkVersion": 33
            }
        },
        "videoId": video_id,
        "params": ""
    }

    res = requests.post(url, json=payload).json()
    log.info(f"📄 Response keys: {list(res.keys())}")

    if "captions" not in res:
        return {"success": False, "error": "NO_CAPTIONS"}

    tracks = res["captions"]["playerCaptionsTracklistRenderer"]["captionTracks"]

    output = []
    for t in tracks:
        output.append({
            "name": t.get("name", {}).get("simpleText", "Unknown"),
            "lang": t.get("languageCode"),
            "url": t.get("baseUrl")
        })

    log.info(f"🎧 Tracks found: {len(output)}")
    return {"success": True, "tracks": output}


# -----------------------------------------
# 3) Fetch & Parse Subtitles from URL
# -----------------------------------------
def fetch_subtitle_from_url(track_url):

    # force srv3 format if available
    if "&fmt=" not in track_url:
        track_url += "&fmt=srv3"

    xml = requests.get(track_url).text
    root = ET.fromstring(xml)

    subs = []

    # SRV3 captions
    for node in root.iter("p"):
        text = "".join(s.text.strip()+" " for s in node.iter("s") if s.text).strip()
        subs.append({
            "text": text,
            "start": float(node.attrib.get("t",0))/1000,
            "duration": float(node.attrib.get("d",0))/1000
        })

    # fallback <text>
    if not subs:
        for node in root.iter("text"):
            subs.append({
                "text": node.text,
                "start": float(node.attrib.get("start",0)),
                "duration": float(node.attrib.get("dur",0))
            })

    return {"success": True, "count": len(subs), "subtitles": subs}


# ================= ROUTES =================

@app.get("/")
def home():
    return {"status": "running",
            "endpoints": ["/tracks?video_id=xxx", "/subtitles?url=xxx"]}


@app.get("/tracks")
def tracks(video_id: str, request: Request):
    if request.headers.get("X-API-KEY") != API_KEY:
        raise HTTPException(401,"API KEY required")

    return get_tracks(video_id)


@app.get("/subtitles")
def subtitles(url: str, request: Request):
    if request.headers.get("X-API-KEY") != API_KEY:
        raise HTTPException(401,"API KEY required")

    return fetch_subtitle_from_url(url)
