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

    log.info("=" * 70)
    log.info(f"🎬 START TRANSCRIPT → {video_id}")

    # WATCH PAGE (only once)
    resp = requests.get(
        f"https://www.youtube.com/watch?v={video_id}",
        headers=HEADERS,
        timeout=15
    )

    log.info(f"🌐 WATCH_STATUS → {resp.status_code}")
    log.info(f"🌐 WATCH_SIZE → {len(resp.text)} bytes")

    html = resp.text

    import re
    key_match = re.search(r'"INNERTUBE_API_KEY":"(.*?)"', html)
    if not key_match:
        log.error("❌ INNERTUBE API KEY NOT FOUND")
        return {"error": "NO_API_KEY"}

    api_key = key_match.group(1)
    url = f"https://youtubei.googleapis.com/youtubei/v1/player?key={api_key}&prettyPrint=false"

    # 🔥 ROTATE THROUGH ALL PAYLOADS
    for index, payload_template in enumerate(PAYLOADS):

        payload = payload_template.copy()
        payload["videoId"] = video_id

        log.info("=" * 50)
        log.info(f"🔄 TRYING PAYLOAD {index + 1}/{len(PAYLOADS)}")
        log.info(f"🔧 CLIENT INFO → {payload_template['context']['client']}")

        try:
            player_resp = requests.post(
                url,
                json=payload,
                headers=HEADERS,
                timeout=15
            )
        except Exception as e:
            log.error(f"❌ PLAYER REQUEST FAILED → {e}")
            continue

        log.info(f"📡 PLAYER_STATUS → {player_resp.status_code}")
        log.info(f"📡 PLAYER_SIZE → {len(player_resp.text)} bytes")

        if player_resp.status_code != 200:
            continue

        player_json = player_resp.json()

        playability = player_json.get("playabilityStatus", {})
        status = playability.get("status")

        log.info(f"▶ PLAYABILITY_STATUS → {status}")

        if status != "OK":
            log.warning("❌ NOT PLAYABLE")
            continue

        if "captions" not in player_json:
            log.warning("❌ NO CAPTIONS FIELD")
            continue

        tracks = player_json["captions"]["playerCaptionsTracklistRenderer"]["captionTracks"]

        if not tracks:
            log.warning("❌ EMPTY TRACKS")
            continue

        selected = tracks[0]
        track_url = selected["baseUrl"]
        lang = selected.get("languageCode", "unknown")

        log.info(f"🔗 CAPTION URL → {track_url}")
        log.info(f"🌍 LANGUAGE → {lang}")

        # FETCH XML
        try:
            xml_resp = requests.get(track_url, headers=HEADERS, timeout=15)
        except Exception as e:
            log.error(f"❌ XML FETCH FAILED → {e}")
            continue

        if xml_resp.status_code != 200:
            log.warning("❌ XML STATUS NOT 200")
            continue

        import xml.etree.ElementTree as ET

        try:
            root = ET.fromstring(xml_resp.text)
        except:
            log.warning("❌ XML PARSE FAILED")
            continue

        subs = []

        # FORMAT 1
        for node in root.iter("text"):
            subs.append({
                "text": (node.text or "").strip(),
                "start": float(node.attrib.get("start", 0)),
                "duration": float(node.attrib.get("dur", 0)),
                "lang": lang
            })

        # FORMAT 2 (srv3)
        if len(subs) == 0:
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

        if subs:
            log.info(f"✅ SUCCESS USING PAYLOAD {index + 1}")
            return {
                "success": True,
                "count": len(subs),
                "lang": lang,
                "subtitles": subs,
                "payload_used": payload_template["context"]["client"]
            }

        log.warning("❌ NO SUBTITLES AFTER PARSE")

    # 🔴 IF ALL FAILED
    log.error("🚫 ALL PAYLOADS FAILED")
    return {"error": "ALL_PAYLOADS_FAILED"}

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
