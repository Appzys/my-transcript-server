import traceback
import logging
import requests
from fastapi import FastAPI

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("yt-rev")

app = FastAPI()

HEADERS = {
    "User-Agent": "com.google.android.youtube/19.08.35 (Linux; Android 13)"
}

# =========================
#  CORE REVERSE ENGINEERING
# =========================
def fetch_subtitles(video_id: str, preferred_lang: str | None = None):

    resp = requests.get(
        f"https://www.youtube.com/watch?v={video_id}",
        headers=HEADERS,
        timeout=15
    )

    html = resp.text

    import re
    key_match = re.search(r'"INNERTUBE_API_KEY":"(.*?)"', html)
    if not key_match:
        raise Exception("Cannot extract innertube key")

    api_key = key_match.group(1)

    payload = {
        "videoId": video_id,
        "context": {
            "client": {
                "clientName": "ANDROID",
                "clientVersion": "19.08.35",
                "androidSdkVersion": 33
            }
        }
    }

    url = f"https://youtubei.googleapis.com/youtubei/v1/player?key={api_key}&prettyPrint=false"

    player_json = requests.post(
        url, json=payload, headers=HEADERS, timeout=15
    ).json()

    if "captions" not in player_json:
        return {"error": "NO_CAPTIONS"}

    tracks = player_json["captions"]["playerCaptionsTracklistRenderer"]["captionTracks"]

    # -------- Language Matching -------
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

    log.info(f"📄 Sub URL: {track_url}")

    xml = requests.get(track_url, headers=HEADERS, timeout=15).text

    import xml.etree.ElementTree as ET
    root = ET.fromstring(xml)

    subs = []
    format_used = "text"

    # ---- OLD format (English style) ----
    for node in root.iter("text"):
        subs.append({
            "text": (node.text or "").replace("\n", " ").strip(),
            "start": float(node.attrib.get("start", 0)),
            "duration": float(node.attrib.get("dur", 0)),
            "lang": lang
        })

    # ---- NEW SRV3 format (Tamil/Hindi/Korean etc) ----
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

    return {
        "success": True,
        "count": len(subs),
        "lang": lang,
        "format": format_used,
        "subtitles": subs
    }


# ===========
#  API ROUTE
# ===========
@app.get("/transcript")
def transcript(video_id: str):
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
