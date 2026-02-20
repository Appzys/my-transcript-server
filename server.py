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
]


def fetch_subtitles(video_id: str, preferred_lang: str | None = None):

    TOTAL_START = time.time()

    log.info("=" * 60)
    log.info(f"🎬 START TRANSCRIPT REQUEST → {video_id}")

    # -------- WATCH PAGE --------
    resp = requests.get(
        f"https://www.youtube.com/watch?v={video_id}",
        headers=HEADERS,
        timeout=10
    )

    log.info(f"🌐 WATCH_STATUS → {resp.status_code}")

    html = resp.text

    key_match = re.search(r'"INNERTUBE_API_KEY":"(.*?)"', html)
    if not key_match:
        log.error("❌ API KEY NOT FOUND")
        return {"error": "NO_API_KEY"}

    api_key = key_match.group(1)
    url = f"https://youtubei.googleapis.com/youtubei/v1/player?key={api_key}&prettyPrint=false"

    # -------- PAYLOAD LOOP --------
    for index, payload_template in enumerate(PAYLOADS):

        payload = payload_template.copy()
        payload["videoId"] = video_id
        client_info = payload["context"]["client"]

        log.info("-" * 40)
        log.info(f"🔧 PAYLOAD {index+1} → {client_info}")

        player_resp = requests.post(
            url,
            json=payload,
            headers=HEADERS,
            timeout=10
        )

        log.info(f"📡 PLAYER_STATUS → {player_resp.status_code}")

        if player_resp.status_code != 200:
            continue

        player_json = player_resp.json()

        playability = player_json.get("playabilityStatus", {})
        status = playability.get("status")

        log.info(f"▶ PLAYABILITY → {status}")

        if status != "OK":
            continue

        captions = player_json.get("captions")
        if not captions:
            log.warning("❌ NO_CAPTIONS")
            continue

        tracks = captions.get("playerCaptionsTracklistRenderer", {}).get("captionTracks")
        if not tracks:
            log.warning("❌ EMPTY_TRACKS")
            continue

        # ---- Language selection (from reference code) ----
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
            log.warning("❌ NO_TRACK_SELECTED")
            continue

        track_url = selected["baseUrl"]
        lang = selected.get("languageCode", "unknown")

        log.info(f"🔗 CAPTION URL → {track_url}")
        log.info(f"🌍 LANGUAGE → {lang}")

        # -------- FETCH XML --------
        xml_resp = requests.get(track_url, headers=HEADERS, timeout=10)

        log.info(f"📄 XML_STATUS → {xml_resp.status_code}")
        log.info(f"📄 XML_SIZE → {len(xml_resp.text)}")

        xml_text = xml_resp.text

        if "<html" in xml_text.lower():
            log.warning("⚠ XML returned HTML page")
            continue

        root = ET.fromstring(xml_text)

        subs = []
        format_used = "text"

        # -------- FORMAT 1: <text> --------
        for node in root.findall(".//{*}text"):
            subs.append({
                "text": (node.text or "").replace("\n", " ").strip(),
                "start": float(node.attrib.get("start", 0)),
                "duration": float(node.attrib.get("dur", 0)),
                "lang": lang
            })

        # -------- FORMAT 2: srv3 --------
        if len(subs) == 0:
            format_used = "srv3"

            for node in root.findall(".//{*}p"):
                chunks = []
                for s in node.findall(".//{*}s"):
                    if s.text:
                        chunks.append(s.text.strip())

                text_value = " ".join(chunks) if chunks else (node.text or "").strip()

                subs.append({
                    "text": text_value,
                    "start": float(node.attrib.get("t", 0)) / 1000,
                    "duration": float(node.attrib.get("d", 0)) / 1000,
                    "lang": lang
                })

        log.info(f"🧾 FORMAT_USED → {format_used}")
        log.info(f"🧾 SUB_COUNT → {len(subs)}")

        if subs:
            return {
                "success": True,
                "count": len(subs),
                "lang": lang,
                "format": format_used,
                "caption_url": track_url,
                "subtitles": subs
            }

    log.error("🚫 ALL PAYLOADS FAILED")
    return {"error": "ALL_PAYLOADS_FAILED"}


@app.get("/transcript")
def transcript(video_id: str, request: Request):
    client_key = request.headers.get("X-API-KEY")

    if client_key != API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")

    return fetch_subtitles(video_id)
