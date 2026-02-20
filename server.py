import traceback
import logging
import requests
import time
from fastapi import FastAPI, Request, HTTPException

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("yt-rev")

app = FastAPI()

HEADERS = {
    "User-Agent": "com.google.android.youtube/19.08.35 (Linux; Android 13)"
}


API_KEY = "x9J2f8S2pA9W-qZvB"

# ========= PAYLOAD ROTATION =========
PAYLOADS = [

    # ======================
    # ANDROID (Working Ones)
    # ======================
    {
        "context": { "client": { "clientName": "ANDROID", "clientVersion": "19.08.35", "androidSdkVersion": 33 }}
    },
    {
        "context": { "client": { "clientName": "ANDROID", "clientVersion": "19.06.38", "androidSdkVersion": 33 }}
    },
    {
        "context": { "client": { "clientName": "ANDROID", "clientVersion": "19.06.38", "androidSdkVersion": 32 }}
    },
    {
        "context": { "client": { "clientName": "ANDROID", "clientVersion": "19.04.36", "androidSdkVersion": 33 }}
    },
    {
        "context": { "client": { "clientName": "ANDROID", "clientVersion": "19.02.33", "androidSdkVersion": 33 }}
    },

    # ======================
    # *** WORKING WEB PAYLOADS ***
    # ======================
    {
        "context": { "client": {
            "clientName": "WEB",
            "clientVersion": "2.20240101.00.00",
            "browserName": "Chrome",
            "platform": "DESKTOP"
        }}
    },
    {
        "context": { "client": {
            "clientName": "WEB",
            "clientVersion": "2.20240212.00.00",
            "browserName": "Chrome",
            "platform": "DESKTOP"
        }}
    },
    {
        "context": { "client": {
            "clientName": "WEB",
            "clientVersion": "2.20240205.00.00",
            "browserName": "Chrome",
            "platform": "DESKTOP"
        }}
    },
    {
        "context": { "client": {
            "clientName": "WEB",
            "clientVersion": "2.20231215.00.00",
            "browserName": "Chrome",
            "platform": "DESKTOP"
        }}
    },
    {
        "context": { "client": {
            "clientName": "WEB",
            "clientVersion": "2.20230812.00.00",
            "browserName": "Chrome",
            "platform": "DESKTOP"
        }}
    },
]

_current_payload_index = 0

def get_next_payload(video_id: str):
    global _current_payload_index

    base_payload = PAYLOADS[_current_payload_index].copy()
    base_payload["videoId"] = video_id

    log.info(f"🔧 Using payload: {PAYLOADS[_current_payload_index]['context']['client']}")


    # rotate
    _current_payload_index = (_current_payload_index + 1) % len(PAYLOADS)

    return base_payload

# =========================
#  CORE REVERSE ENGINEERING
# =========================
def fetch_subtitles(video_id: str, preferred_lang: str | None = None):

    MAX_TOTAL_TIME = 30  # seconds (change if needed)
    start_time = time.time()

    log.info(f"▶ Fetching watch page → {video_id}")

    try:
        resp = requests.get(
            f"https://www.youtube.com/watch?v={video_id}",
            headers=HEADERS,
            timeout=5
        )
    except Exception as e:
        return {"error": "WATCH_PAGE_FAILED"}

    html = resp.text

    import re
    key_match = re.search(r'"INNERTUBE_API_KEY":"(.*?)"', html)
    if not key_match:
        return {"error": "NO_API_KEY"}

    api_key = key_match.group(1)
    url = f"https://youtubei.googleapis.com/youtubei/v1/player?key={api_key}&prettyPrint=false"

    for index, payload_template in enumerate(PAYLOADS):

        # 🔴 GLOBAL TIME CHECK
        if time.time() - start_time > MAX_TOTAL_TIME:
            log.error("⏱ Global timeout reached. Stopping.")
            return {"error": "GLOBAL_TIMEOUT"}

        payload = payload_template.copy()
        payload["videoId"] = video_id
        client_info = payload["context"]["client"]

        log.info(f"🔧 Trying Payload {index+1}/{len(PAYLOADS)} → {client_info}")

        try:
            player_resp = requests.post(
                url,
                json=payload,
                headers=HEADERS,
                timeout=4  # shorter timeout
            )
            player_json = player_resp.json()

        except Exception as e:
            log.warning(f"⚠ Payload {index+1} failed → {e}")
            continue

        if "captions" not in player_json:
            log.info(f"❌ Payload {index+1} → No captions")
            continue

        tracks = player_json["captions"]["playerCaptionsTracklistRenderer"]["captionTracks"]

        if not tracks:
            continue

        selected = tracks[0]
        track_url = selected["baseUrl"]

        try:
            xml = requests.get(track_url, headers=HEADERS, timeout=4).text
        except:
            continue

        import xml.etree.ElementTree as ET
        try:
            root = ET.fromstring(xml)
        except:
            continue

        subs = []
        for node in root.iter("text"):
            subs.append({
                "text": (node.text or "").strip(),
                "start": float(node.attrib.get("start", 0)),
                "duration": float(node.attrib.get("dur", 0)),
            })

        if subs:
            log.info(f"🎉 SUCCESS → Payload {index+1}")
            return {
                "success": True,
                "count": len(subs),
                "subtitles": subs,
                "payload_used": client_info
            }

    log.error("🚫 All payloads failed")
    return {"error": "ALL_PAYLOADS_FAILED"}
# ===========
#  API ROUTE
# ===========
@app.get("/transcript")
def transcript(video_id: str, request: Request):
    client_key = request.headers.get("X-API-KEY")

    if client_key != API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")

    log.info(f"🎬 Request → {video_id}")
    
    try:
        result = fetch_subtitles(video_id)
        if result.get("success"):
            return {**result, "mode": "DIRECT"}
        else:
            return result
    except Exception as e:
        log.error(f"❌ Error: {e}")
        return {"success": False, "error": str(e)}
