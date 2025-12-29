import traceback
import logging
import requests
from fastapi import FastAPI, Request, HTTPException

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("yt-rev")

app = FastAPI()

HEADERS = {
    "User-Agent": "com.google.android.youtube/19.08.35 (Linux; Android 13)"
}

API_KEY = "x9J2f8S2pA9W-qZvB"

# ========= ROTATION PAYLOADS =========
PAYLOADS = [
    {"context": { "client": {"clientName": "ANDROID","clientVersion": "19.08.35","androidSdkVersion": 33 }}},
    {"context": { "client": {"clientName": "ANDROID","clientVersion": "19.06.38","androidSdkVersion": 33 }}},
    {"context": { "client": {"clientName": "ANDROID","clientVersion": "19.06.38","androidSdkVersion": 32 }}},
    {"context": { "client": {"clientName": "ANDROID","clientVersion": "19.04.36","androidSdkVersion": 33 }}},
    {"context": { "client": {"clientName": "ANDROID","clientVersion": "19.02.33","androidSdkVersion": 33 }}},

    # WEB WORKING
    {"context": { "client": {"clientName": "WEB","clientVersion": "2.20240101.00.00","browserName": "Chrome","platform": "DESKTOP"}}},
    {"context": { "client": {"clientName": "WEB","clientVersion": "2.20240212.00.00","browserName": "Chrome","platform": "DESKTOP"}}},
    {"context": { "client": {"clientName": "WEB","clientVersion": "2.20240205.00.00","browserName": "Chrome","platform": "DESKTOP"}}},
    {"context": { "client": {"clientName": "WEB","clientVersion": "2.20231215.00.00","browserName": "Chrome","platform": "DESKTOP"}}},
    {"context": { "client": {"clientName": "WEB","clientVersion": "2.20230812.00.00","browserName": "Chrome","platform": "DESKTOP"}}},
]

_current_payload_index = 0


def get_next_payload(video_id: str):
    global _current_payload_index
    log.info(f"🌀 Selecting Payload index: {_current_payload_index}")

    payload = PAYLOADS[_current_payload_index].copy()
    payload["videoId"] = video_id

    used = PAYLOADS[_current_payload_index]["context"]["client"]
    log.info(f"🔧 Using Payload: {used}")

    # rotate forward
    _current_payload_index = (_current_payload_index + 1) % len(PAYLOADS)
    log.info(f"🔁 Next Payload index will be: {_current_payload_index}")

    return payload


# ========================= SUBTITLE FETCH =========================
def fetch_subtitles(video_id: str, preferred_lang=None):

    log.info(f"\n========================")
    log.info(f"▶ Step 1: Fetching HTML Page for {video_id}")
    log.info(f"========================")

    try:
        resp = requests.get(
            f"https://www.youtube.com/watch?v={video_id}",
            headers=HEADERS, timeout=15
        )
        log.info("✔ HTML Page Request Success")
    except Exception as e:
        log.error("❌ Failed fetching watch page")
        traceback.print_exc()
        raise e

    html = resp.text
    log.info(f"📃 HTML Length: {len(html)} chars")

    import re
    log.info("🔍 Extracting INNERTUBE_API_KEY")
    key_match = re.search(r'"INNERTUBE_API_KEY":"(.*?)"', html)

    if not key_match:
        log.error("❌ Cannot extract INNERTUBE_API_KEY — IMPORTANT FAILURE")
        raise Exception("Cannot extract INNERTUBE_API_KEY")

    api_key = key_match.group(1)
    log.warning(f"⭐ INNERTUBE_API_KEY FOUND = {api_key}")   # ⭐ highlight here

    payload = get_next_payload(video_id)

    url = f"https://youtubei.googleapis.com/youtubei/v1/player?key={api_key}&prettyPrint=false"
    log.info(f"▶ Step 2: Sending Player API Request")
    log.info(f"POST → {url}")
    log.info(f"Payload → {payload}")

    try:
        player_json = requests.post(url, json=payload, headers=HEADERS, timeout=15).json()
        log.info("✔ Player API Response received")
        log.info(f"🔍 Keys in response → {list(player_json.keys())}")
    except Exception as e:
        log.error("❌ Player API Request Failed")
        traceback.print_exc()
        raise e

    if "captions" not in player_json:
        log.error("❌ No captions found in response")
        return {"error": "NO_CAPTIONS", "debug_keys": list(player_json.keys())}

    tracks = player_json["captions"]["playerCaptionsTracklistRenderer"]["captionTracks"]
    log.info(f"📝 Found {len(tracks)} subtitle track(s)")

    selected = None

    # language priority
    if preferred_lang:
        log.info(f"🌐 Looking preferred language → {preferred_lang}")
        selected = next((t for t in tracks if t.get("languageCode") == preferred_lang and not t.get("kind")), None)

    if selected is None:
        log.info("➡ Selecting first normal subtitle track")
        selected = next((t for t in tracks if not t.get("kind")), None)

    if selected is None:
        log.info("➡ Fallback: selecting forced/auto track")
        selected = next((t for t in tracks if t.get("kind")), None)

    if selected is None:
        log.error("❌ NO TRACKS FOUND EVEN AFTER FALLBACK")
        return {"error": "NO_TRACKS"}

    track_url = selected["baseUrl"]
    lang = selected.get("languageCode", "unknown")

    log.info(f"▶ Step 3: Downloading actual .XML subtitles")
    log.info(f"Subtitle URL → {track_url}")
    log.info(f"Language → {lang}")

    try:
        xml = requests.get(track_url, headers=HEADERS, timeout=15).text
        log.info("✔ Subtitle XML downloaded")
        log.info(f"XML Length: {len(xml)} chars")
    except:
        log.error("❌ Failed to download XML Track")
        traceback.print_exc()
        raise

    import xml.etree.ElementTree as ET
    root = ET.fromstring(xml)

    subs = []
    format_used = "text"

    log.info("▶ Step 4: Parsing XML (old format <text>)")

    for node in root.iter("text"):
        subs.append({
            "text": (node.text or "").replace("\n", " ").strip(),
            "start": float(node.attrib.get("start", 0)),
            "duration": float(node.attrib.get("dur", 0)),
            "lang": lang
        })

    if len(subs) == 0:
        log.warning("⚠ No <text> tags, trying NEW SRV3 <p><s> format")
        format_used = "srv3"

        for node in root.iter("p"):
            chunks = [s.text.strip() for s in node.iter("s") if s.text]
            text_value = " ".join(chunks) if chunks else (node.text or "").strip()

            subs.append({
                "text": text_value,
                "start": float(node.attrib.get("t", 0)) / 1000,
                "duration": float(node.attrib.get("d", 0)) / 1000,
                "lang": lang
            })

    log.info(f"📌 Final Subtitle Count → {len(subs)}")
    log.info(f"Format Used → {format_used}")
    log.info("========================\n")

    return {
        "success": True,
        "lang": lang,
        "count": len(subs),
        "format": format_used,
        "subtitles": subs
    }


# =================== API ROUTE ===================
@app.get("/transcript")
def transcript(video_id: str, request: Request):
    log.info(f"\n========================")
    log.info(f"📥 Incoming Request → {video_id}")
    log.info("========================")

    client_key = request.headers.get("X-API-KEY")
    log.info(f"Sent API KEY: {client_key}")

    if client_key != API_KEY:
        log.error("❌ Invalid API Key")
        raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        result = fetch_subtitles(video_id)
        log.info("✔ Transcript fetch complete")
        return result
    except Exception as e:
        log.error("❌ FINAL ERROR CAUGHT")
        traceback.print_exc()
        return {
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }
