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

# Direct internal YouTube API key (no HTML needed)
INNERTUBE_API_KEY = "AIzaSyAO_FJ2slcYkHfPDXz9fm1E1JY2Eo9uVDo"

HEADERS = {
    "User-Agent": "com.google.android.youtube/19.08.35 (Linux; Android 13)",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "application/json",
    "Content-Type": "application/json",
}

# Payload rotation used by YouTube mobile/WEB
PAYLOADS = [
    {"context":{"client":{"clientName":"ANDROID","clientVersion":"19.08.35","androidSdkVersion":33}}},
    {"context":{"client":{"clientName":"ANDROID","clientVersion":"19.06.38","androidSdkVersion":33}}},
    {"context":{"client":{"clientName":"ANDROID","clientVersion":"19.04.36","androidSdkVersion":33}}},
    {"context":{"client":{"clientName":"WEB","clientVersion":"2.20240212.00.00","browserName":"Chrome","platform":"DESKTOP"}}},
    {"context":{"client":{"clientName":"WEB","clientVersion":"2.20230812.00.00","browserName":"Chrome","platform":"DESKTOP"}}},
]

rot = 0
def next_payload(video_id):
    global rot
    payload = PAYLOADS[rot].copy()
    payload["videoId"] = video_id
    log.info(f"🔄 Payload Selected: {payload['context']['client']}")
    rot = (rot + 1) % len(PAYLOADS)
    return payload

# ================= EXTRACT API KEY FROM HTML =================
def extract_innertube_key(video_id):
    """Fallback: extract key from watch page HTML"""
    resp = requests.get(
        f"https://www.youtube.com/watch?v={video_id}",
        headers={"User-Agent": HEADERS["User-Agent"]},
        timeout=15
    )
    
    log.info(f"📄 HTML Status: {resp.status_code}, Length: {len(resp.text)}")
    
    if resp.status_code != 200:
        raise Exception(f"Failed to fetch watch page: {resp.status_code}")
    
    # Multiple regex patterns for different HTML formats
    patterns = [
        r'"INNERTUBE_API_KEY":"([^"]+)"',
        r'"INNERTUBE_API_KEY"\s*:\s*"([^"]+)"',
        r'INNERTUBE_API_KEY["\']?\s*:\s*["\']([^"\']+)["\']',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, resp.text)
        if match:
            key = match.group(1)
            log.info(f"✅ API Key extracted: {key[:20]}...")
            return key
    
    raise Exception("Cannot extract INNERTUBE_API_KEY from HTML")

# ================= SUBTITLE FETCH PROCESS =================
def fetch_subtitles(video_id, preferred_lang=None):
    try:
        log.info(f"================= 📥 NEW REQUEST =================")
        log.info(f"🎯 Video ID: {video_id}")
        payload = next_payload(video_id)

        # ✅ TRY DIRECT API KEY FIRST
        url = f"https://youtubei.googleapis.com/youtubei/v1/player?key={INNERTUBE_API_KEY}"
        log.info(f"🌍 Trying direct API: {url}")

        resp = requests.post(url, json=payload, headers=HEADERS, timeout=15)
        
        # ✅ CHECK IF HTML ERROR (405/400/etc)
        if resp.status_code != 200 or not resp.headers.get("content-type", "").startswith("application/json"):
            log.warning(f"⚠️ Direct API failed ({resp.status_code}): {resp.text[:200]}")
            
            # ✅ FALLBACK: Extract key from HTML
            log.info("🔄 Falling back to HTML key extraction...")
            api_key = extract_innertube_key(video_id)
            url = f"https://youtubei.googleapis.com/youtubei/v1/player?key={api_key}"
            log.info(f"🌍 Using extracted key: {url}")
            
            resp = requests.post(url, json=payload, headers=HEADERS, timeout=15)

        # ✅ PARSE JSON SAFELY
        try:
            data = resp.json()
        except requests.exceptions.JSONDecodeError:
            log.error(f"❌ Invalid JSON response: {resp.text[:500]}")
            raise Exception(f"Invalid response from YouTube: {resp.status_code}")

        log.info(f"📥 Player JSON keys: {list(data.keys())}")

        # Captions availability check
        if "captions" not in data:
            log.warning("⚠ No captions found in player response")
            return {"success": False, "error": "NO_CAPTIONS"}

        tracks = data["captions"]["playerCaptionsTracklistRenderer"]["captionTracks"]
        log.info(f"🎧 Tracks Available: {len(tracks)}")

        # Pick language (improved matching)
        track = None
        if preferred_lang:
            track = next((t for t in tracks if t.get("languageCode") == preferred_lang and not t.get("kind")), None)
        
        if not track:
            track = next((t for t in tracks if not t.get("kind")), None)
        
        if not track and len(tracks) > 0:
            track = tracks[0]

        if not track:
            return {"success": False, "error": "NO_TRACKS"}

        sub_url = track["baseUrl"] + "&fmt=srv3"
        log.info(f"📄 Subtitle XML URL: {sub_url}")

        xml_resp = requests.get(sub_url, headers=HEADERS, timeout=15)
        xml = xml_resp.text
        log.info(f"📄 XML Status: {xml_resp.status_code}")

        root = ET.fromstring(xml)

        subs = []
        
        # Try SRV3 format first
        for node in root.iter("p"):
            chunks = [s.text.strip() for s in node.iter("s") if s.text]
            text_value = " ".join(chunks) if chunks else (node.text or "").strip()
            
            if text_value:
                subs.append({
                    "text": text_value,
                    "start": float(node.attrib.get("t", 0)) / 1000,
                    "duration": float(node.attrib.get("d", 0)) / 1000,
                })

        # Fallback to old format
        if not subs:
            for node in root.iter("text"):
                text = (node.text or "").replace("\n", " ").strip()
                if text:
                    subs.append({
                        "text": text,
                        "start": float(node.attrib.get("start", 0)),
                        "duration": float(node.attrib.get("dur", 0)),
                    })

        log.info(f"📝 Subtitles Extracted: {len(subs)} lines")

        result = {
            "success": True,
            "video_id": video_id,
            "lang": track.get("languageCode", "unknown"),
            "count": len(subs),
            "subtitles": subs
        }

        log.info(f"✅ Process Completed Successfully for {video_id}")
        return result

    except Exception as e:
        log.error("❌ ERROR OCCURRED")
        log.error(traceback.format_exc())
        return {"success": False, "error": str(e)}

# ================= ROUTES =================
@app.get("/")
def home():
    log.info("🌍 Root Accessed")
    return {"status":"running","endpoint":"/transcript?video_id=xxxx"}

@app.get("/transcript")
def transcript(video_id: str, request: Request):
    log.info("================== API HIT ==================")
    log.info(f"🔐 Checking API Key")

    if request.headers.get("X-API-KEY") != API_KEY:
        log.warning("❌ Invalid API Key Used")
        raise HTTPException(401, "Invalid API Key")

    log.info(f"🔓 Auth Passed → Fetching Transcript for {video_id}")
    return fetch_subtitles(video_id)
