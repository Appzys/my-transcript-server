import traceback
import logging
import requests
import time
import re
import xml.etree.ElementTree as ET
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


def fetch_subtitles(video_id: str):

    TOTAL_START = time.time()
    MAX_TOTAL_TIME = 30

    log.info("=" * 70)
    log.info(f"🎬 START TRANSCRIPT REQUEST → {video_id}")

    # WATCH PAGE
    try:
        resp = requests.get(
            f"https://www.youtube.com/watch?v={video_id}",
            headers=HEADERS,
            timeout=5
        )
    except Exception as e:
        log.error(f"❌ WATCH_PAGE_EXCEPTION → {e}")
        return {"error": "WATCH_PAGE_FAILED"}

    log.info(f"🌐 WATCH_STATUS → {resp.status_code}")
    log.info(f"🌐 WATCH_SIZE → {len(resp.text)} bytes")

    if resp.status_code != 200:
        return {"error": f"WATCH_HTTP_{resp.status_code}"}

    html = resp.text

    key_match = re.search(r'"INNERTUBE_API_KEY":"(.*?)"', html)
    if not key_match:
        log.error("❌ API KEY NOT FOUND")
        return {"error": "NO_API_KEY"}

    api_key = key_match.group(1)
    log.info("🔑 API KEY FOUND")

    url = f"https://youtubei.googleapis.com/youtubei/v1/player?key={api_key}&prettyPrint=false"

    failure_summary = []

    # PAYLOAD LOOP
    for index, payload_template in enumerate(PAYLOADS):

        if time.time() - TOTAL_START > MAX_TOTAL_TIME:
            log.error("⏱ GLOBAL TIMEOUT")
            return {"error": "GLOBAL_TIMEOUT"}

        payload = payload_template.copy()
        payload["videoId"] = video_id
        client_info = payload["context"]["client"]

        log.info("-" * 40)
        log.info(f"🔧 PAYLOAD {index+1}/{len(PAYLOADS)} → {client_info}")

        try:
            player_resp = requests.post(
                url,
                json=payload,
                headers=HEADERS,
                timeout=5
            )
        except Exception as e:
            log.error(f"❌ PLAYER_EXCEPTION → {e}")
            failure_summary.append(f"P{index+1}:EXCEPTION")
            continue

        log.info(f"📡 PLAYER_STATUS → {player_resp.status_code}")
        log.info(f"📡 PLAYER_SIZE → {len(player_resp.text)} bytes")

        if player_resp.status_code != 200:
            failure_summary.append(f"P{index+1}:HTTP_{player_resp.status_code}")
            continue

        try:
            player_json = player_resp.json()
        except Exception:
            log.error("❌ INVALID JSON RESPONSE")
            failure_summary.append(f"P{index+1}:INVALID_JSON")
            continue

        playability = player_json.get("playabilityStatus", {})
        status = playability.get("status")
        reason = playability.get("reason")

        log.info(f"▶ PLAYABILITY → {status} | {reason}")

        if status and status != "OK":
            failure_summary.append(f"P{index+1}:PLAY_{status}")
            continue

        captions_data = player_json.get("captions")
        if not captions_data:
            log.warning("❌ NO CAPTIONS FIELD")
            failure_summary.append(f"P{index+1}:NO_CAPTIONS")
            continue

        tracks = captions_data.get("playerCaptionsTracklistRenderer", {}).get("captionTracks")
        if not tracks:
            log.warning("❌ EMPTY CAPTION TRACKS")
            failure_summary.append(f"P{index+1}:EMPTY_TRACKS")
            continue

        selected = tracks[0]
        track_url = selected.get("baseUrl")

        if not track_url:
            log.warning("❌ NO TRACK URL")
            failure_summary.append(f"P{index+1}:NO_TRACK_URL")
            continue

        # 🔥 THIS IS WHAT YOU WANTED
        log.info("=" * 40)
        log.info(f"🔗 CAPTION URL → {track_url}")
        log.info("=" * 40)

        # XML FETCH
        try:
            xml_resp = requests.get(track_url, headers=HEADERS, timeout=5)
        except Exception as e:
            log.error(f"❌ XML_EXCEPTION → {e}")
            failure_summary.append(f"P{index+1}:XML_EXCEPTION")
            continue

        log.info(f"📄 XML_STATUS → {xml_resp.status_code}")
        log.info(f"📄 XML_SIZE → {len(xml_resp.text)} bytes")

        if xml_resp.status_code != 200:
            failure_summary.append(f"P{index+1}:XML_HTTP_{xml_resp.status_code}")
            continue

        if "<html" in xml_resp.text.lower():
            log.warning("⚠ XML returned HTML page")
            failure_summary.append(f"P{index+1}:XML_BLOCKED")
            continue

        # Debug preview
        log.info("📄 XML PREVIEW (first 500 chars):")
        log.info(xml_resp.text[:500])

        try:
            root = ET.fromstring(xml_resp.text)
        except Exception:
            log.error("❌ XML_PARSE_ERROR")
            failure_summary.append(f"P{index+1}:XML_PARSE_ERROR")
            continue

        # Namespace-safe extraction
        subs = []
        for node in root.findall(".//{*}text"):
            subs.append({
                "text": (node.text or "").strip(),
                "start": float(node.attrib.get("start", 0)),
                "duration": float(node.attrib.get("dur", 0)),
            })

        if subs:
            total_time = round(time.time() - TOTAL_START, 3)
            log.info(f"🎉 SUCCESS → PAYLOAD {index+1}")
            return {
                "success": True,
                "count": len(subs),
                "payload_used": client_info,
                "caption_url": track_url,
                "total_time": total_time,
                "subtitles": subs
            }

        log.warning("❌ NO_SUBS AFTER PARSING")
        failure_summary.append(f"P{index+1}:NO_SUBS")

    total_time = round(time.time() - TOTAL_START, 3)

    log.error("🚫 ALL PAYLOADS FAILED")
    log.error(f"🧾 FAILURE SUMMARY → {failure_summary}")

    return {
        "success": False,
        "error": "ALL_PAYLOADS_FAILED",
        "failure_summary": failure_summary,
        "total_time": total_time
    }


@app.get("/transcript")
def transcript(video_id: str, request: Request):

    client_key = request.headers.get("X-API-KEY")

    if client_key != API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")

    return fetch_subtitles(video_id)
