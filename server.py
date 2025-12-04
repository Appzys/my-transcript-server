import random
import traceback
import logging
import requests
from fastapi import FastAPI

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("yt-rev")

app = FastAPI()

# Rotating Android fingerprints (avoid fingerprint ban)
ANDROID_CLIENTS = [
    {"clientName": "ANDROID", "clientVersion": "19.08.35", "androidSdkVersion": 33, "hl": "en", "deviceModel": "Pixel 7 Pro"},
    {"clientName": "ANDROID", "clientVersion": "18.41.38", "androidSdkVersion": 30, "hl": "en", "deviceModel": "Samsung S21"},
    {"clientName": "ANDROID", "clientVersion": "17.36.4",  "androidSdkVersion": 29, "hl": "en", "deviceModel": "Redmi Note 10"},
    {"clientName": "ANDROID", "clientVersion": "16.20.35",  "androidSdkVersion": 28, "hl": "en", "deviceModel": "OnePlus 6T"},
    {"clientName": "ANDROID", "clientVersion": "15.01.36",  "androidSdkVersion": 26, "hl": "en", "deviceModel": "Vivo V9"}
]

HEADERS = {
    "User-Agent": "com.google.android.youtube/19.08.35 (Linux; Android 13)"
}


def fetch_subtitles(video_id: str, preferred_lang: str | None = None):
    android_client = random.choice(ANDROID_CLIENTS)
    log.info(f"📱 Using device profile → {android_client}")

    resp = requests.get(
        f"https://www.youtube.com/watch?v={video_id}",
        headers=HEADERS,
        timeout=15
    )
    html = resp.text

    import re
    match = re.search(r'"INNERTUBE_API_KEY":"(.*?)"', html)
    if not match:
        raise Exception("Failed to extract Innertube API key")

    api_key = match.group(1)
    log.info(f"🔑 API KEY FOUND → {api_key[:10]}...")

    # 💡 IMPORTANT: `params` enables auto-generated captions!
    payload = {
        "videoId": video_id,
        "params": "CgQIARgA",
        "context": {"client": android_client}
    }

    log.info(f"📦 Payload → {android_client['deviceModel']} ({android_client['clientVersion']})")

    url = f"https://youtubei.googleapis.com/youtubei/v1/player?key={api_key}&prettyPrint=false"
    player_json = requests.post(url, json=payload, headers=HEADERS, timeout=15).json()

    if "captions" not in player_json:
        return {"error": "NO_CAPTIONS_FIELD_FROM_YT"}

    captions = player_json["captions"]

    # -------------------------------
    # Find captionTracks LOCATION
    # -------------------------------

    tracks = None

    if "playerCaptionsTracklistRenderer" in captions:
        tracks = captions["playerCaptionsTracklistRenderer"].get("captionTracks")

    if tracks is None and "playerCaptionsRenderer" in captions:
        tracks = captions["playerCaptionsRenderer"].get("captionTracks")

    if not tracks:
        return {"error": "NO_TRACKS_FOUND"}

    # Try preferred language
    selected = None

    if preferred_lang:
        selected = next((t for t in tracks if t.get("languageCode") == preferred_lang), None)

    # Try normal captions first
    if selected is None:
        selected = next((t for t in tracks if not t.get("kind")), None)

    # Try auto-generated captions (`kind=asr`)
    if selected is None:
        selected = next((t for t in tracks if t.get("kind") == "asr"), None)

    # Last fallback
    if selected is None:
        selected = tracks[0]

    track_url = selected["baseUrl"]
    lang = selected.get("languageCode", "unknown")

    log.info(f"🌍 Caption Language → {lang}")
    log.info(f"🔗 Subtitle URL → {track_url}")

    xml = requests.get(track_url, headers=HEADERS, timeout=15).text

    import xml.etree.ElementTree as ET
    root = ET.fromstring(xml)

    subs = []

    # ---- English/Old Format ----
    for node in root.iter("text"):
        subs.append({
            "text": (node.text or "").strip(),
            "start": float(node.attrib.get("start", 0)),
            "duration": float(node.attrib.get("dur", 0)),
            "lang": lang
        })

    # ---- SRV3 Format (Tamil/Hindi/Korean) ----
    if not subs:
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
        "client_used": android_client,
        "lang": lang,
        "subtitles": subs
    }


@app.get("/transcript")
def transcript(video_id: str):
    log.info(f"➡ Request → {video_id}")

    try:
        result = fetch_subtitles(video_id)
        if result.get("success"):
            log.info(f"✅ Transcript Loaded ({result['count']} lines)")
            return result
    except Exception as e:
        log.error(str(e))
        log.error(traceback.format_exc())

    return {"success": False, "error": "FAILED"}
