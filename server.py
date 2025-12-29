import traceback
import logging
import requests
from fastapi import FastAPI, Request, HTTPException

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
}

# Payload rotation used by YouTube mobile/WEB
PAYLOADS = [
    {"context":{"client":{"clientName":"ANDROID","clientVersion":"19.08.35"}}},
    {"context":{"client":{"clientName":"ANDROID","clientVersion":"19.06.38"}}},
    {"context":{"client":{"clientName":"ANDROID","clientVersion":"19.04.36"}}},
    {"context":{"client":{"clientName":"WEB","clientVersion":"2.20240212.00.00"}}},
    {"context":{"client":{"clientName":"WEB","clientVersion":"2.20230812.00.00"}}},
]


rot = 0
def next_payload(video_id):
    global rot
    payload = PAYLOADS[rot].copy()
    payload["videoId"] = video_id
    log.info(f"🔄 Payload Selected: {payload['context']['client']}")
    rot = (rot + 1) % len(PAYLOADS)
    return payload


# ================= SUBTITLE FETCH PROCESS =================
def fetch_subtitles(video_id, preferred_lang=None):
    try:
        log.info(f"================= 📥 NEW REQUEST =================")
        log.info(f"🎯 Video ID: {video_id}")
        payload = next_payload(video_id)

        # ✅ FIXED: Use correct endpoint for captions
        url = f"https://youtubei.googleapis.com/youtubei/v1/get_player?key={INNERTUBE_API_KEY}"
        log.info(f"🌍 Sending Internal API Request: {url}")

        data = requests.post(url, json=payload, headers=HEADERS, timeout=15).json()
        log.info(f"📥 Player JSON keys received: {list(data.keys())}")

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

        sub_url = track["baseUrl"] + "&fmt=srv3"  # Force srv3 format (better for non-English)
        log.info(f"📄 Subtitle XML URL: {sub_url}")

        xml = requests.get(sub_url, headers=HEADERS, timeout=15).text
        log.info(f"📄 XML Fetch Successful, Parsing...")

        import xml.etree.ElementTree as ET
        root = ET.fromstring(xml)

        subs = []
        
        # Try SRV3 format first (Tamil/Hindi/Asian langs)
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
def transcript(video_id:str, request:Request):
    log.info("================== API HIT ==================")
    log.info(f"🔐 Checking API Key")

    if request.headers.get("X-API-KEY") != API_KEY:
        log.warning("❌ Invalid API Key Used")
        raise HTTPException(401,"Invalid API Key")

    log.info(f"🔓 Auth Passed → Fetching Transcript for {video_id}")
    return fetch_subtitles(video_id)
