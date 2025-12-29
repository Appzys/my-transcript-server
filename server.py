import traceback
import logging
import requests
from fastapi import FastAPI, Request, HTTPException

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("yt-rev")

app = FastAPI()

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.youtube.com"
}

API_KEY = "x9J2f8S2pA9W-qZvB"


# ================= PAYLOAD ROTATION =================
PAYLOADS = [
    {"context": {"client": {"clientName": "ANDROID", "clientVersion": "19.08.35", "androidSdkVersion": 33}}},
    {"context": {"client": {"clientName": "ANDROID", "clientVersion": "19.06.38", "androidSdkVersion": 33}}},
    {"context": {"client": {"clientName": "ANDROID", "clientVersion": "19.06.38", "androidSdkVersion": 32}}},
    {"context": {"client": {"clientName": "ANDROID", "clientVersion": "19.04.36", "androidSdkVersion": 33}}},
    {"context": {"client": {"clientName": "ANDROID", "clientVersion": "19.02.33", "androidSdkVersion": 33}}},

    {"context": {"client": {"clientName": "WEB","clientVersion": "2.20240101.00.00","browserName": "Chrome","platform":"DESKTOP"}}},
    {"context": {"client": {"clientName": "WEB","clientVersion": "2.20240212.00.00","browserName": "Chrome","platform":"DESKTOP"}}},
    {"context": {"client": {"clientName": "WEB","clientVersion": "2.20240205.00.00","browserName": "Chrome","platform":"DESKTOP"}}},
    {"context": {"client": {"clientName": "WEB","clientVersion": "2.20231215.00.00","browserName": "Chrome","platform":"DESKTOP"}}},
    {"context": {"client": {"clientName": "WEB","clientVersion": "2.20230812.00.00","browserName": "Chrome","platform":"DESKTOP"}}},
]

_current_payload_index = 0
def get_next_payload(video_id: str):
    global _current_payload_index

    payload = PAYLOADS[_current_payload_index].copy()
    payload["videoId"] = video_id
    log.info(f"🔧 Payload Using → {payload['context']['client']}")

    _current_payload_index = (_current_payload_index + 1) % len(PAYLOADS)
    return payload


# ================= FETCH SUBTITLES =================
def fetch_subtitles(video_id: str, preferred_lang: str | None = None):
    try:
        resp = requests.get(
            f"https://www.youtube.com/watch?v={video_id}",
            headers=HEADERS,
            timeout=15
        )

        html = resp.text
        log.info("====== YOUTUBE HTML (first 1500 chars) ======")
        log.info(html[:1500])
        log.info("=============================================")

        import re
        key_match = re.search(r'"INNERTUBE_API_KEY"\s*:?\s*"([^"]+)"', html) or \
                    re.search(r'"innertubeApiKey"\s*:?\s*"([^"]+)"', html)

        if not key_match:
            with open("debug_youtube.html", "w", encoding="utf-8") as f:  # debugging
                f.write(html)

            raise Exception("Cannot extract innertube key (YouTube served consent/captcha page)")

        api_key = key_match.group(1)
        log.info(f"✔ Extracted API KEY: {api_key}")

        payload = get_next_payload(video_id)
        url = f"https://youtubei.googleapis.com/youtubei/v1/player?key={api_key}&prettyPrint=false"

        player_json = requests.post(url, json=payload, headers=HEADERS, timeout=15).json()
        log.info(f"Player JSON keys: {list(player_json.keys())}")

        if "captions" not in player_json:
            raise Exception("NO_CAPTIONS_AVAILABLE")

        tracks = player_json["captions"]["playerCaptionsTracklistRenderer"]["captionTracks"]

        # ================= Track Selection =================
        selected = None
        if preferred_lang:
            selected = next((t for t in tracks if t.get("languageCode") == preferred_lang and not t.get("kind")), None)
        if not selected:
            selected = next((t for t in tracks if not t.get("kind")), None)
        if not selected:
            selected = next((t for t in tracks if t.get("kind")), None)
        if not selected:
            raise Exception("NO_TRACKS_FOUND")

        track_url = selected["baseUrl"]
        lang = selected.get("languageCode","unknown")

        xml = requests.get(track_url, headers=HEADERS, timeout=15).text

        import xml.etree.ElementTree as ET
        root = ET.fromstring(xml)

        subs = []
        format_used = "text"

        for node in root.iter("text"):
            subs.append({
                "text": (node.text or "").replace("\n"," ").strip(),
                "start": float(node.attrib.get("start",0)),
                "duration": float(node.attrib.get("dur",0)),
                "lang": lang
            })

        if not subs:     # SRV3 format
            format_used ="srv3"
            for node in root.iter("p"):
                chunks=[s.text.strip() for s in node.iter("s") if s.text]
                text_value=" ".join(chunks) if chunks else (node.text or "").strip()
                subs.append({
                    "text": text_value,
                    "start": float(node.attrib.get("t",0))/1000,
                    "duration": float(node.attrib.get("d",0))/1000,
                    "lang": lang
                })

        return {
            "success":True,
            "lang":lang,
            "format":format_used,
            "count":len(subs),
            "subtitles":subs
        }

    except Exception as e:
        log.error("🔥 TRACEBACK ↓↓↓")
        log.error(traceback.format_exc())
        return {"success":False,"error":str(e)}



# ================= ROUTE =================
@app.get("/")
def root():
    return {"status":"running","usage":"/transcript?video_id=XXXX"}


@app.get("/transcript")
def transcript(video_id:str,request:Request):
    if request.headers.get("X-API-KEY") != API_KEY:
        raise HTTPException(status_code=401,detail="Unauthorized")

    log.info(f"📩 Transcript Request: {video_id}")
    return fetch_subtitles(video_id)
