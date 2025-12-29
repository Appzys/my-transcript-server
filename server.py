import traceback
import logging
import requests
import re
from fastapi import FastAPI, Request, HTTPException
import xml.etree.ElementTree as ET

# ================= LOGGING =================
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
log = logging.getLogger("yt-rev")

# ================= APP SETUP =================
app = FastAPI()
API_KEY = "x9J2f8S2pA9W-qZvB"

YOUTUBE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9"
}

# =========================================================
# 1) Extract INNERTUBE_API_KEY
# =========================================================
def extract_key(video_id):
    log.info(f"\n\n================ KEY EXTRACT START ================")
    url = f"https://www.youtube.com/watch?v={video_id}"
    log.info(f"📥 Fetching HTML → {url}")

    resp = requests.get(url, headers=YOUTUBE_HEADERS, timeout=15)
    log.info(f"🌐 HTML Status={resp.status_code}, size={len(resp.text)}")

    match = re.search(r'"INNERTUBE_API_KEY":"([^"]+)"', resp.text)
    if not match:
        log.error("❌ Could not extract key (YouTube returned challenge or new format)")
        raise Exception("Failed to extract INNERTUBE_KEY")

    key = match.group(1)
    log.info(f"🔑 Extracted Key: {key}")
    log.info(f"================ KEY EXTRACT END ==================\n")
    return key


# =========================================================
# 2) Get available caption tracks
# =========================================================
def get_tracks(video_id):
    log.info(f"\n\n============== TRACK REQUEST START ==============")
    key = extract_key(video_id)

    url = f"https://youtubei.googleapis.com/youtubei/v1/player?key={key}"
    payload = {
        "context": {"client": {"clientName": "ANDROID", "clientVersion": "19.08.35"}},
        "videoId": video_id,
        "params": ""
    }

    log.info(f"▶ POST {url}")
    log.info(f"📦 Payload = {payload}")

    res = requests.post(url, json=payload, headers={"Content-Type": "application/json"})
    log.info(f"🌍 PlayerAPI Status={res.status_code}")

    try:
        data = res.json()
    except:
        return {"success": False, "error": "INVALID_JSON", "body": res.text[:300]}

    log.info(f"🔑 Response Keys: {list(data.keys())}")

    if "captions" not in data:
        log.warning("❌ No captions available for this video")
        return {"success": False, "error": "NO_CAPTIONS"}

    tracks = data["captions"]["playerCaptionsTracklistRenderer"]["captionTracks"]
    log.info(f"🎧 Found Tracks Count: {len(tracks)}")

    output=[]
    for t in tracks:
        out = {
            "name": t.get("name", {}).get("simpleText","Unknown"),
            "lang": t.get("languageCode",""),
            "url": t.get("baseUrl","")
        }
        log.info(f"📌 Track -> {out}")
        output.append(out)

    log.info("============== TRACK REQUEST END ==============\n")
    return {"success": True, "tracks": output}


# =========================================================
# 3) Fetch subtitles using baseUrl
# =========================================================
def fetch_subtitle(track_url):
    
    log.info(f"\n\n============== SUBTITLE FETCH START ==============")
    log.info(f"📥 URL = {track_url}")

    if "&fmt=" not in track_url:
        track_url += "&fmt=srv3"

    resp = requests.get(track_url, headers=YOUTUBE_HEADERS)
    log.info(f"🌍 XML Fetch Status={resp.status_code}")
    log.info(f"📝 Raw XML Preview: {resp.text[:200]} ")

    root = ET.fromstring(resp.text)
    subs=[]

    # ---- SRV3 Format ----
    for p in root.iter("p"):
        text=" ".join(s.text for s in p.iter("s") if s.text).strip()
        subs.append({
            "text":text,
            "start":float(p.attrib.get("t",0))/1000,
            "duration":float(p.attrib.get("d",0))/1000
        })

    # fallback
    if not subs:
        for node in root.iter("text"):
            subs.append({
                "text":node.text,
                "start":float(node.attrib.get("start",0)),
                "duration":float(node.attrib.get("dur",0))
            })

    log.info(f"✔ Subtitle Lines Extracted = {len(subs)}")
    log.info("============== SUBTITLE FETCH END ==============\n")
    
    return {"success": True, "count": len(subs), "subtitles": subs}


# ================= ROUTES =================

@app.get("/")
def home():
    return {
        "status":"running",
        "usage":[
            "/tracks?video_id=xxxx",
            "/subtitles?url=PASTE_TRACK_URL"
        ],
        "note":"You must pass ?video_id=xxx or ?url=xxx, otherwise you see 404"
    }


@app.get("/tracks")
def tracks(video_id:str, request:Request):
    if request.headers.get("X-API-KEY") != API_KEY:
        raise HTTPException(401, "API KEY required")
    return get_tracks(video_id)


@app.get("/subtitles")
def subtitles(url:str, request:Request):
    if request.headers.get("X-API-KEY") != API_KEY:
        raise HTTPException(401, "API KEY required")
    return fetch_subtitle(url)
