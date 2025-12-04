import random
import traceback
import logging
import requests
from fastapi import FastAPI

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("yt-rev")

app = FastAPI()

# 🎭 Rotating Android fake client identities
ANDROID_CLIENTS = [
    {"clientName": "ANDROID", "clientVersion": "19.08.35", "androidSdkVersion": 33, "hl": "en", "deviceModel": "Pixel 7 Pro"},
    {"clientName": "ANDROID", "clientVersion": "18.41.38", "androidSdkVersion": 30, "hl": "en", "deviceModel": "Samsung S21"},
    {"clientName": "ANDROID", "clientVersion": "17.36.4",  "androidSdkVersion": 29, "hl": "en", "deviceModel": "Redmi Note 10"},
    {"clientName": "ANDROID", "clientVersion": "16.20.35",  "androidSdkVersion": 28, "hl": "en", "deviceModel": "OnePlus 6T"},
    {"clientName": "ANDROID", "clientVersion": "15.01.36",  "androidSdkVersion": 26, "hl": "en", "deviceModel": "Vivo V9"},
]

HEADERS = {
    "User-Agent": "com.google.android.youtube/19.08.35 (Linux; Android 13)"
}


# =========================
#  CORE FUNCTION
# =========================
def fetch_subtitles(video_id: str, preferred_lang: str | None = None):

    android_client = random.choice(ANDROID_CLIENTS)
    log.info(f"📱 Using payload: {android_client['deviceModel']} (v{android_client['clientVersion']})")

    resp = requests.get(
        f"https://www.youtube.com/watch?v={video_id}",
        headers=HEADERS,
        timeout=15
    )

    html = resp.text

    import re
    key_match = re.search(r'"INNERTUBE_API_KEY":"(.*?)"', html)
    if not key_match:
        raise Exception("❌ Could not extract API key")

    api_key = key_match.group(1)

    payload = {
        "videoId": video_id,
        "context": {
            "client": android_client
        }
    }

    url = f"https://youtubei.googleapis.com/youtubei/v1/player?key={api_key}&prettyPrint=false"

    player_json = requests.post(
        url, json=payload, headers=HEADERS, timeout=15
    ).json()

    if "captions" not in player_json:
        return {"error": "NO_CAPTIONS"}

    tracks = player_json["captions"]["playerCaptionsTracklistRenderer"]["captionTracks"]
    selected = None

    if preferred_lang:
        selected = next((t for t in tracks if t.get("languageCode") == preferred_lang and not t.get("kind")), None)
    if not selected:
        selected = next((t for t in tracks if not t.get("kind")), None)
    if not selected:
        selected = next((t for t in tracks if t.get("kind")), None)
    if not selected:
        selected = tracks[0]

    track_url = selected["baseUrl"]
    lang = selected.get("languageCode", "unknown")

    log.info(f"🌍 Language: {lang}")
    log.info(f"📄 Subtitle URL: {track_url}")

    xml = requests.get(track_url, headers=HEADERS, timeout=15).text

    import xml.etree.ElementTree as ET
    root = ET.fromstring(xml)

    subs = []

    # ---- VTT/XML Type 1 ----
    for node in root.iter("text"):
        subs.append({
            "text": (node.text or "").replace("\n", " ").strip(),
            "start": float(node.attrib.get("start", 0)),
            "duration": float(node.attrib.get("dur", 0)),
            "lang": lang
        })

    # ---- SRV3 Format (Tamil/Hindi/Korean) ----
    if len(subs) == 0:
        for node in root.iter("p"):
            chunks = [s.text.strip() for s in node.iter("s") if s.text]
            text_value = " ".join(chunks) if chunks else (node.text or "").strip()
            subs.append({
                "text": text_value,
                "start": float(node.attrib.get("t", 0)) / 1000,
                "duration": float(node.attrib.get("d", 0)) / 1000,
                "lang": lang
            })

    return {
        "success": True,
        "count": len(subs),
        "device_used": android_client,
        "lang": lang,
        "subtitles": subs
    }


# =========================
#  API ROUTE
# =========================
@app.get("/transcript")
def transcript(video_id: str):
    log.info(f"🎬 Request → {video_id}")

    try:
        result = fetch_subtitles(video_id)
        return {**result, "mode": "DIRECT"}
    except Exception as e:
        log.error(f"❌ Error: {e}")
        log.error(traceback.format_exc())
        return {"success": False, "error": "FAILED"}
