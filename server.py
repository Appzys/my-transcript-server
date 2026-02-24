import traceback
import logging
import requests
import time
import random
import copy
import re
import xml.etree.ElementTree as ET
from fastapi import FastAPI, Request, HTTPException

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("yt-rev")

app = FastAPI()

API_KEY = "x9J2f8S2pA9W-qZvB"

# ✅ Realistic modern headers
HEADERS = {
    "User-Agent": "com.google.android.youtube/20.03.35 (Linux; U; Android 14; en_US; SM-S918B Build/UP1A.231005.007)",
    "Accept-Language": "en-US,en;q=0.9",
    "Content-Type": "application/json"
}

# ✅ Updated realistic 2026 payload fingerprints
PAYLOADS = [

    # Android Samsung
    {
        "context": {
            "client": {
                "clientName": "ANDROID",
                "clientVersion": "20.03.35",
                "androidSdkVersion": 34,
                "hl": "en",
                "gl": "US",
                "utcOffsetMinutes": 0,
                "deviceMake": "Samsung",
                "deviceModel": "SM-S918B",
                "clientScreen": "WATCH",
                "osName": "Android",
                "osVersion": "14"
            }
        }
    },

    # Android Pixel
    {
        "context": {
            "client": {
                "clientName": "ANDROID",
                "clientVersion": "20.01.32",
                "androidSdkVersion": 34,
                "hl": "en",
                "gl": "US",
                "utcOffsetMinutes": 0,
                "deviceMake": "Google",
                "deviceModel": "Pixel 8",
                "clientScreen": "WATCH",
                "osName": "Android",
                "osVersion": "14"
            }
        }
    },

    # Android TV
    {
        "context": {
            "client": {
                "clientName": "ANDROID_TV",
                "clientVersion": "7.20250115.16.00",
                "hl": "en",
                "gl": "US",
                "clientScreen": "WATCH"
            }
        }
    },

    # Desktop Chrome
    {
        "context": {
            "client": {
                "clientName": "WEB",
                "clientVersion": "2.20250201.00.00",
                "hl": "en",
                "gl": "US",
                "browserName": "Chrome",
                "browserVersion": "121.0.0.0",
                "platform": "DESKTOP",
                "clientScreen": "WATCH"
            }
        }
    },

    # Mobile Chrome
    {
        "context": {
            "client": {
                "clientName": "WEB",
                "clientVersion": "2.20250201.00.00",
                "hl": "en",
                "gl": "US",
                "browserName": "Chrome",
                "browserVersion": "121.0.0.0",
                "platform": "MOBILE",
                "clientScreen": "WATCH"
            }
        }
    }
]


def get_next_payload(video_id: str):
    payload_template = random.choice(PAYLOADS)
    base_payload = copy.deepcopy(payload_template)
    base_payload["videoId"] = video_id

    log.info("=" * 60)
    log.info("🔀 RANDOM PAYLOAD SELECTED")
    log.info(f"CLIENT → {payload_template['context']['client']}")

    return base_payload


def fetch_subtitles(video_id: str, preferred_lang: str | None = None):

    start_total = time.time()
    log.info("=" * 70)
    log.info(f"🎬 START TRANSCRIPT → {video_id}")

    # WATCH PAGE
    watch_start = time.time()
    resp = requests.get(
        f"https://www.youtube.com/watch?v={video_id}",
        headers=HEADERS,
        timeout=15
    )
    watch_time = round(time.time() - watch_start, 3)

    log.info(f"🌐 WATCH_STATUS → {resp.status_code}")
    log.info(f"🌐 WATCH_TIME → {watch_time}s")

    if resp.status_code != 200:
        raise Exception(f"WATCH_PAGE_FAILED: {resp.status_code}")

    html = resp.text

    key_match = re.search(r'"INNERTUBE_API_KEY":"(.*?)"', html)
    if not key_match:
        log.error("❌ INNERTUBE API KEY NOT FOUND")
        raise Exception("Cannot extract innertube key")

    api_key = key_match.group(1)
    log.info(f"🔑 API KEY EXTRACTED")

    payload = get_next_payload(video_id)

    url = f"https://youtubei.googleapis.com/youtubei/v1/player?key={api_key}&prettyPrint=false"

    player_start = time.time()
    player_resp = requests.post(
        url, json=payload, headers=HEADERS, timeout=15
    )
    player_time = round(time.time() - player_start, 3)

    log.info(f"📡 PLAYER_STATUS → {player_resp.status_code}")
    log.info(f"📡 PLAYER_TIME → {player_time}s")

    if player_resp.status_code != 200:
        raise Exception(f"PLAYER_REQUEST_FAILED: {player_resp.status_code}")

    player_json = player_resp.json()
    playability = player_json.get("playabilityStatus", {})
    log.info(f"▶ PLAYABILITY_STATUS → {playability}")

    # ✅ Block detection
    status = playability.get("status")

    if status == "LOGIN_REQUIRED":
        log.error("🚫 LOGIN REQUIRED BLOCK")
        return {"error": "LOGIN_REQUIRED"}

    if status == "UNPLAYABLE":
        log.error("🚫 VIDEO UNPLAYABLE")
        return {"error": "UNPLAYABLE"}

    if status == "ERROR":
        log.error("🚫 GENERAL PLAYABILITY ERROR")
        return {"error": "PLAYABILITY_ERROR"}

    if "captions" not in player_json:
        log.warning("❌ CAPTIONS FIELD NOT FOUND")
        return {"error": "NO_CAPTIONS"}

    tracks = player_json["captions"]["playerCaptionsTracklistRenderer"]["captionTracks"]

    selected = None

    if preferred_lang:
        selected = next(
            (t for t in tracks if t.get("languageCode") == preferred_lang and not t.get("kind")),
            None
        )

    if selected is None:
        selected = next((t for t in tracks if not t.get("kind")), None)

    if selected is None:
        selected = next((t for t in tracks if t.get("kind")), None)

    if selected is None and len(tracks) > 0:
        selected = tracks[0]

    if selected is None:
        return {"error": "NO_TRACKS"}

    track_url = selected["baseUrl"]
    lang = selected.get("languageCode", "unknown")

    # XML FETCH
    xml_resp = requests.get(track_url, headers=HEADERS, timeout=15)

    if xml_resp.status_code != 200:
        raise Exception(f"XML_FETCH_FAILED: {xml_resp.status_code}")

    root = ET.fromstring(xml_resp.text)

    subs = []
    format_used = "text"

    for node in root.iter("text"):
        subs.append({
            "text": (node.text or "").replace("\n", " ").strip(),
            "start": float(node.attrib.get("start", 0)),
            "duration": float(node.attrib.get("dur", 0)),
            "lang": lang
        })

    if len(subs) == 0:
        format_used = "srv3"

        for node in root.iter("p"):
            chunks = []
            for s in node.iter("s"):
                if s.text:
                    chunks.append(s.text.strip())

            text_value = " ".join(chunks) if chunks else (node.text or "").strip()

            subs.append({
                "text": text_value,
                "start": float(node.attrib.get("t", 0)) / 1000,
                "duration": float(node.attrib.get("d", 0)) / 1000,
                "lang": lang
            })

    log.info(f"🧾 FINAL_SUB_COUNT → {len(subs)}")
    log.info(f"⏱ TOTAL_TIME → {round(time.time() - start_total, 3)}s")

    return {
        "success": True,
        "count": len(subs),
        "lang": lang,
        "format": format_used,
        "subtitles": subs
    }


@app.get("/transcript")
def transcript(video_id: str, request: Request):
    client_key = request.headers.get("X-API-KEY")

    if client_key != API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")

    log.info(f"🎬 REQUEST RECEIVED → {video_id}")

    try:
        result = fetch_subtitles(video_id)

        if result.get("success"):
            return {**result, "mode": "DIRECT"}
        else:
            return result

    except Exception as e:
        log.error(f"❌ ERROR OCCURRED → {str(e)}")
        log.error(traceback.format_exc())
        return {"success": False, "error": str(e)}
