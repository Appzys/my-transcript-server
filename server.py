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
INNERTUBE_API_KEY = "AIzaSyAO_FJ2slcYkHfPDXz9fm1E1JY2Eo9uVDo"

HEADERS = {
    "User-Agent": "com.google.android.youtube/19.08.35 (Linux; Android 13)",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "application/json",
    "Content-Type": "application/json",
}

# ✅ CORRECT Payloads for NEXT endpoint (captions)
PAYLOADS = [
    {
        "context": {
            "client": {
                "clientName": "ANDROID",
                "clientVersion": "19.08.35",
                "androidSdkVersion": 33,
                "hl": "en"
            }
        },
        "videoId": "VIDEO_ID_PLACEHOLDER"
    },
    {
        "context": {
            "client": {
                "clientName": "WEB",
                "clientVersion": "2.20240212.00.00",
                "hl": "en"
            }
        },
        "videoId": "VIDEO_ID_PLACEHOLDER"
    }
]

rot = 0
def next_payload(video_id):
    global rot
    payload = PAYLOADS[rot].copy()
    payload["videoId"] = video_id
    log.info(f"🔄 Payload Selected: {PAYLOADS[rot]['context']['client']['clientName']}")
    rot = (rot + 1) % len(PAYLOADS)
    return payload

def extract_innertube_key(video_id):
    """Extract INNERTUBE_API_KEY from watch page"""
    resp = requests.get(
        f"https://www.youtube.com/watch?v={video_id}",
        headers={"User-Agent": HEADERS["User-Agent"]},
        timeout=15
    )
    
    if resp.status_code != 200:
        raise Exception(f"Watch page failed: {resp.status_code}")
    
    patterns = [
        r'"INNERTUBE_API_KEY"\s*:\s*"([^"]+)"',
        r'INNERTUBE_API_KEY["\']?\s*:\s*["\']([^"\']+)["\']',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, resp.text)
        if match:
            return match.group(1)
    
    raise Exception("INNERTUBE_API_KEY not found")

def fetch_subtitles(video_id, preferred_lang=None):
    try:
        log.info(f"🎯 Video ID: {video_id}")
        payload = next_payload(video_id)

        # ✅ ENDPOINT 1: /next (for captions)
        url = f"https://youtubei.googleapis.com/youtubei/v1/next?key={INNERTUBE_API_KEY}"
        log.info(f"🌍 NEXT endpoint: {url}")

        resp = requests.post(url, json=payload, headers=HEADERS, timeout=20)
        
        if resp.status_code != 200:
            log.warning(f"⚠️ NEXT failed ({resp.status_code}), trying HTML fallback")
            # Fallback to HTML extraction
            api_key = extract_innertube_key(video_id)
            url = f"https://youtubei.googleapis.com/youtubei/v1/next?key={api_key}"
            resp = requests.post(url, json=payload, headers=HEADERS, timeout=20)

        data = resp.json()
        log.info(f"📥 Response keys: {list(data.keys())}")

        # ✅ Check multiple caption locations
        captions = None
        if "captions" in data:
            captions = data["captions"]
        elif "contents" in data and "twoColumnWatchNextResults" in data["contents"]:
            # Alternative path
            overlay = data["contents"]["twoColumnWatchNextResults"]["results"]["results"]["contents"][0].get("videoPrimaryInfoRenderer", {})
            if "metadata" in overlay:
                captions = overlay["metadata"].get("videoDetails", {}).get("captions", None)

        if not captions:
            log.warning("⚠ No captions found")
            return {"success": False, "error": "NO_CAPTIONS"}

        # Extract tracks
        tracks = []
        if "playerCaptionsTracklistRenderer" in captions:
            tracks = captions["playerCaptionsTracklistRenderer"]["captionTracks"]
        elif "captionTracks" in captions:
            tracks = captions["captionTracks"]

        log.info(f"🎧 Found {len(tracks)} caption tracks")

        if not tracks:
            return {"success": False, "error": "NO_TRACKS"}

        # Select best track
        track = next((t for t in tracks if t.get("languageCode") == (preferred_lang or "en")), tracks[0])
        log.info(f"✅ Selected track: {track.get('languageCode')}")

        # Fetch subtitles
        sub_url = track["baseUrl"] + "&fmt=json3"  # JSON format is more reliable
        log.info(f"📄 Fetching: {sub_url}")

        xml_resp = requests.get(sub_url, headers=HEADERS, timeout=15)
        if xml_resp.status_code != 200:
            sub_url = track["baseUrl"] + "&fmt=srv3"
            xml_resp = requests.get(sub_url, headers=HEADERS, timeout=15)

        if xml_resp.status_code != 200:
            return {"success": False, "error": f"Subtitle fetch failed: {xml_resp.status_code}"}

        # Parse XML/JSON
        try:
            root = ET.fromstring(xml_resp.text)
            subs = parse_xml_subs(root, track.get("languageCode", "en"))
        except:
            # Try JSON format
            import json
            subs_data = json.loads(xml_resp.text)
            subs = parse_json_subs(subs_data, track.get("languageCode", "en"))

        log.info(f"📝 Extracted {len(subs)} subtitles")

        return {
            "success": True,
            "video_id": video_id,
            "lang": track.get("languageCode", "unknown"),
            "count": len(subs),
            "subtitles": subs[:1000]  # Limit for API response size
        }

    except Exception as e:
        log.error(f"❌ Error: {str(e)}")
        log.error(traceback.format_exc())
        return {"success": False, "error": str(e)}

def parse_xml_subs(root, lang):
    subs = []
    # SRV3 format
    for node in root.iter("p"):
        chunks = [s.text.strip() for s in node.iter("s") if s.text and s.text.strip()]
        text = " ".join(chunks) if chunks else (node.text or "").strip()
        if text:
            subs.append({
                "text": text,
                "start": float(node.attrib.get("t", 0)) / 1000,
                "duration": float(node.attrib.get("d", 0)) / 1000,
                "lang": lang
            })
    
    # Fallback text format
    if not subs:
        for node in root.iter("text"):
            text = (node.text or "").replace("\n", " ").strip()
            if text:
                subs.append({
                    "text": text,
                    "start": float(node.attrib.get("start", 0)),
                    "duration": float(node.attrib.get("dur", 0)),
                    "lang": lang
                })
    return subs

def parse_json_subs(data, lang):
    subs = []
    if "events" in data:
        for event in data["events"]:
            if "tStartMs" in event and "dDurationMs" in event and "segs" in event:
                text = " ".join(seg["utf8"] for seg in event["segs"] if "utf8" in seg)
                subs.append({
                    "text": text.strip(),
                    "start": int(event["tStartMs"]) / 1000,
                    "duration": int(event["dDurationMs"]) / 1000,
                    "lang": lang
                })
    return subs

# ================= ROUTES =================
@app.get("/")
def home():
    return {"status": "running", "endpoint": "/transcript?video_id=xxxx"}

@app.get("/transcript")
def transcript(video_id: str, request: Request):
    if request.headers.get("X-API-KEY") != API_KEY:
        raise HTTPException(401, "Invalid API Key")
    return fetch_subtitles(video_id)
