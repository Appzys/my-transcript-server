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

PAYLOADS = [
    {"context": {"client": {"clientName": "ANDROID", "clientVersion": "19.08.35", "androidSdkVersion": 33}}},
    {"context": {"client": {"clientName": "ANDROID", "clientVersion": "19.06.38", "androidSdkVersion": 33}}},
    {"context": {"client": {"clientName": "ANDROID", "clientVersion": "19.06.38", "androidSdkVersion": 32}}},
    {"context": {"client": {"clientName": "ANDROID", "clientVersion": "19.04.36", "androidSdkVersion": 33}}},
    {"context": {"client": {"clientName": "ANDROID", "clientVersion": "19.02.33", "androidSdkVersion": 33}}},
    {"context": {"client": {"clientName": "WEB", "clientVersion": "2.20240101.00.00", "browserName": "Chrome", "platform": "DESKTOP"}}},
    {"context": {"client": {"clientName": "WEB", "clientVersion": "2.20240212.00.00", "browserName": "Chrome", "platform": "DESKTOP"}}},
    {"context": {"client": {"clientName": "WEB", "clientVersion": "2.20240205.00.00", "browserName": "Chrome", "platform": "DESKTOP"}}},
    {"context": {"client": {"clientName": "WEB", "clientVersion": "2.20231215.00.00", "browserName": "Chrome", "platform": "DESKTOP"}}},
    {"context": {"client": {"clientName": "WEB", "clientVersion": "2.20230812.00.00", "browserName": "Chrome", "platform": "DESKTOP"}}},
]

_current_payload_index = 0

def get_next_payload(video_id: str):
    global _current_payload_index

    base_payload = PAYLOADS[_current_payload_index].copy()
    base_payload["videoId"] = video_id

    log.info("=" * 60)
    log.info(f"🔧 USING PAYLOAD INDEX → {_current_payload_index}")
    log.info(f"🔧 CLIENT INFO → {PAYLOADS[_current_payload_index]['context']['client']}")

    _current_payload_index = (_current_payload_index + 1) % len(PAYLOADS)
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
    log.info(f"🌐 WATCH_SIZE → {len(resp.text)} bytes")

    html = resp.text

    import re
    key_match = re.search(r'"INNERTUBE_API_KEY":"(.*?)"', html)
    if not key_match:
        log.error("❌ INNERTUBE API KEY NOT FOUND")
        raise Exception("Cannot extract innertube key")

    api_key = key_match.group(1)
    log.info(f"🔑 API KEY EXTRACTED → {api_key[:10]}...")

    payload = get_next_payload(video_id)

    url = f"https://youtubei.googleapis.com/youtubei/v1/player?key={api_key}&prettyPrint=false"
    log.info(f"📡 PLAYER URL → {url}")

    player_start = time.time()
    player_resp = requests.post(
        url, json=payload, headers=HEADERS, timeout=15
    )
    player_time = round(time.time() - player_start, 3)

    log.info(f"📡 PLAYER_STATUS → {player_resp.status_code}")
    log.info(f"📡 PLAYER_TIME → {player_time}s")
    log.info(f"📡 PLAYER_SIZE → {len(player_resp.text)} bytes")

    player_json = player_resp.json()

    playability = player_json.get("playabilityStatus", {})
    log.info(f"▶ PLAYABILITY_STATUS → {playability}")

    if "captions" not in player_json:
        log.warning("❌ CAPTIONS FIELD NOT FOUND")
        return {"error": "NO_CAPTIONS"}

    tracks = player_json["captions"]["playerCaptionsTracklistRenderer"]["captionTracks"]
    log.info(f"🧾 TRACK_COUNT → {len(tracks)}")

    selected = None

    if preferred_lang:
        selected = next(
            (t for t in tracks if t.get("languageCode") == preferred_lang and not t.get("kind")),
            None
        )
        log.info(f"🌍 MATCHED preferred_lang → {preferred_lang}")

    if selected is None:
        selected = next((t for t in tracks if not t.get("kind")), None)
        log.info("🌍 SELECTED NON-AUTO TRACK")

    if selected is None:
        selected = next((t for t in tracks if t.get("kind")), None)
        log.info("🌍 SELECTED AUTO TRACK")

    if selected is None and len(tracks) > 0:
        selected = tracks[0]
        log.info("🌍 FALLBACK FIRST TRACK")

    if selected is None:
        log.error("❌ NO TRACK SELECTED")
        return {"error": "NO_TRACKS"}

    track_url = selected["baseUrl"]
    lang = selected.get("languageCode", "unknown")

    log.info("=" * 40)
    log.info(f"🔗 CAPTION URL → {track_url}")
    log.info(f"🌍 LANGUAGE → {lang}")
    log.info("=" * 40)

    # XML FETCH
    xml_start = time.time()
    xml_resp = requests.get(track_url, headers=HEADERS, timeout=15)
    xml_time = round(time.time() - xml_start, 3)

    log.info(f"📄 XML_STATUS → {xml_resp.status_code}")
    log.info(f"📄 XML_TIME → {xml_time}s")
    log.info(f"📄 XML_SIZE → {len(xml_resp.text)} bytes")
    log.info("📄 XML_PREVIEW ↓")
    log.info(xml_resp.text[:500])

    import xml.etree.ElementTree as ET
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

    log.info(f"🧾 TEXT_FORMAT_COUNT → {len(subs)}")

    if len(subs) == 0:
        format_used = "srv3"
        log.info("🔄 SWITCHING TO SRV3 FORMAT PARSE")

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
    log.info(f"🧾 FORMAT_USED → {format_used}")
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
