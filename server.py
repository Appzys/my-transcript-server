import traceback
import logging
import requests
from fastapi import FastAPI, Request, HTTPException
import re, json

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("yt-rev")

app = FastAPI()

# Desktop for watch-page HTML (because Android returns trimmed HTML)
WATCH_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
}

# Android headers for Innertube API request
INNERTUBE_HEADERS = {
    "User-Agent": "com.google.android.youtube/19.08.35 (Linux; Android 13)",
    "Content-Type": "application/json"
}

# Your API auth key for FastAPI route security
API_KEY = "x9J2f8S2pA9W-qZvB"

# ========= ROTATION PAYLOADS (unchanged) =========
PAYLOADS = [
    {"context": { "client": {"clientName": "ANDROID","clientVersion": "19.08.35","androidSdkVersion": 33 }}},
    {"context": { "client": {"clientName": "ANDROID","clientVersion": "19.06.38","androidSdkVersion": 33 }}},
    {"context": { "client": {"clientName": "ANDROID","clientVersion": "19.06.38","androidSdkVersion": 32 }}},
    {"context": { "client": {"clientName": "ANDROID","clientVersion": "19.04.36","androidSdkVersion": 33 }}},
    {"context": { "client": {"clientName": "ANDROID","clientVersion": "19.02.33","androidSdkVersion": 33 }}},

    # WEB
    {"context": { "client": {"clientName": "WEB","clientVersion": "2.20240101.00.00","browserName": "Chrome","platform": "DESKTOP"}}},
    {"context": { "client": {"clientName": "WEB","clientVersion": "2.20240212.00.00","browserName": "Chrome","platform": "DESKTOP"}}},
    {"context": { "client": {"clientName": "WEB","clientVersion": "2.20240205.00.00","browserName": "Chrome","platform": "DESKTOP"}}},
    {"context": { "client": {"clientName": "WEB","clientVersion": "2.20231215.00.00","browserName": "Chrome","platform": "DESKTOP"}}},
    {"context": { "client": {"clientName": "WEB","clientVersion": "2.20230812.00.00","browserName": "Chrome","platform": "DESKTOP"}}},
]

_current_payload_index = 0

def get_next_payload(video_id):
    global _current_payload_index
    payload = PAYLOADS[_current_payload_index].copy()
    payload["videoId"] = video_id

    log.info(f"🌀 Using Payload index {_current_payload_index} → {payload['context']['client']}")

    _current_payload_index = (_current_payload_index + 1) % len(PAYLOADS)
    return payload


# ========================= SUBTITLE FETCH =========================
def fetch_subtitles(video_id: str, preferred_lang=None):

    log.info(f"\n========================")
    log.info(f"▶ Step 1: Fetching watch page HTML for {video_id}")
    log.info(f"========================")

    resp = requests.get(
        f"https://www.youtube.com/watch?v={video_id}",
        headers=WATCH_HEADERS, timeout=15
    )

    html = resp.text
    log.info(f"📃 HTML length: {len(html)} chars")

    # --- Extract API Key Robust Way ---
    log.info("🔍 Extracting INNERTUBE_API_KEY...")

    api_key = None

    # First: extract full config json
    ytcfg_match = re.search(r'ytcfg\.set\s*\(\s*(\{.*?\})\s*\)', html, re.DOTALL)
    if ytcfg_match:
        try:
            cfg = json.loads(ytcfg_match.group(1))
            api_key = cfg.get("INNERTUBE_API_KEY")
        except Exception:
            pass

    # Fallback regex
    if not api_key:
        m = re.search(r'"INNERTUBE_API_KEY":"(.*?)"', html)
        if m:
            api_key = m.group(1)

    # Final fallback static key
    if not api_key:
        api_key = "AIzaSyB9..."       # ← Insert working public fallback if needed
        log.warning("⚠ API key not found in HTML -> Using fallback key")

    log.info(f"⭐ INNERTUBE_API_KEY = {api_key}")

    payload = get_next_payload(video_id)
    url = f"https://youtubei.googleapis.com/youtubei/v1/player?key={api_key}&prettyPrint=false"

    log.info(f"▶ Step 2: Fetching Player API → {url}")

    player_json = requests.post(url, json=payload, headers=INNERTUBE_HEADERS, timeout=15).json()
    log.info(f"✔ Player response keys: {list(player_json.keys())}")

    if "captions" not in player_json:
        log.error("❌ No captions found.")
        return {"error":"NO_CAPTIONS", "debug_keys":list(player_json.keys())}

    tracks = player_json["captions"]["playerCaptionsTracklistRenderer"]["captionTracks"]
    log.info(f"📝 Tracks found: {len(tracks)}")

    # Select subtitle track
    track = None
    if preferred_lang:
        track = next((t for t in tracks if t.get("languageCode")==preferred_lang and not t.get("kind")),None)
    if not track:
        track = next((t for t in tracks if not t.get("kind")),None)
    if not track:
        track = tracks[0]

    url_xml = track["baseUrl"]
    lang = track.get("languageCode","unknown")

    log.info(f"▶ Step 3: Downloading XML → {url_xml}")

    xml = requests.get(url_xml, timeout=15).text

    import xml.etree.ElementTree as ET
    root = ET.fromstring(xml)

    subs=[]
    for node in root.iter("text"):
        subs.append({
            "text": (node.text or "").replace("\n"," ").strip(),
            "start": float(node.attrib.get("start",0)),
            "duration": float(node.attrib.get("dur",0)),
            "lang": lang
        })

    log.info(f"📌 Final subtitles: {len(subs)}")

    return {"success":True,"lang":lang,"count":len(subs),"subtitles":subs}


# =================== API ROUTE ===================
@app.get("/transcript")
def transcript(video_id: str, request: Request):
    client_key = request.headers.get("X-API-KEY")

    if client_key != API_KEY:
        raise HTTPException(status_code=401,detail="Unauthorized")

    try:
        return fetch_subtitles(video_id)
    except Exception as e:
        return {"success":False,"error":str(e),"trace":traceback.format_exc()}
