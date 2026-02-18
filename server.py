import traceback
import logging
import requests
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from datetime import datetime, timezone

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("yt-rev")

app = FastAPI()

HEADERS = {
    "User-Agent": "com.google.android.youtube/19.08.35 (Linux; Android 13)"
}


API_KEY = "x9J2f8S2pA9W-qZvB"
SENSITIVE_HEADERS = {"x-api-key", "authorization", "cookie", "set-cookie"}


def _snippet(text: str, limit: int = 400) -> str:
    compact = (text or "").replace("\n", " ").replace("\r", " ")
    if len(compact) <= limit:
        return compact
    return compact[:limit] + "...(truncated)"


def _masked_headers(headers: dict) -> dict:
    sanitized = {}
    for key, value in headers.items():
        if key.lower() in SENSITIVE_HEADERS:
            sanitized[key] = "***redacted***"
        else:
            sanitized[key] = value
    return sanitized


def _request_id(video_id: str | None = None) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    if video_id:
        return f"{video_id}-{ts}"
    return ts


def log_exception_details(request: Request | None, exc: Exception, req_id: str, video_id: str | None = None):
    log.error("request_id=%s error_type=%s error=%s", req_id, type(exc).__name__, str(exc))

    if request is not None:
        client_host = request.client.host if request.client else "unknown"
        log.error(
            "request_id=%s method=%s path=%s query=%s client=%s headers=%s",
            req_id,
            request.method,
            request.url.path,
            dict(request.query_params),
            client_host,
            _masked_headers(dict(request.headers)),
        )

    if video_id:
        log.error("request_id=%s video_id=%s", req_id, video_id)

    log.error("request_id=%s traceback:\n%s", req_id, traceback.format_exc())

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
    log.info("fetch_subtitles.start video_id=%s preferred_lang=%s", video_id, preferred_lang)

    resp = requests.get(
        f"https://www.youtube.com/watch?v={video_id}",
        headers=HEADERS,
        timeout=15
    )
    log.info("watch_page.status=%s url=%s", resp.status_code, resp.url)
    resp.raise_for_status()

    html = resp.text

    import re
    key_match = re.search(r'"INNERTUBE_API_KEY":"(.*?)"', html)
    if not key_match:
        log.error("innertube_key_missing video_id=%s html_snippet=%s", video_id, _snippet(html))
        raise Exception("Cannot extract innertube key")

    api_key = key_match.group(1)
    log.info("innertube_key_found video_id=%s key_prefix=%s", video_id, api_key[:6])

    # === CHANGED: payload now rotates ===
    payload = get_next_payload(video_id)
    client_ctx = payload.get("context", {}).get("client", {})
    log.info("player_payload video_id=%s client=%s", video_id, client_ctx)

    url = f"https://youtubei.googleapis.com/youtubei/v1/player?key={api_key}&prettyPrint=false"

    player_resp = requests.post(
        url, json=payload, headers=HEADERS, timeout=15
    )
    log.info("player_api.status=%s video_id=%s", player_resp.status_code, video_id)
    player_resp.raise_for_status()

    try:
        player_json = player_resp.json()
    except Exception:
        log.error(
            "player_api_invalid_json video_id=%s response_snippet=%s",
            video_id,
            _snippet(player_resp.text),
        )
        raise

    if "captions" not in player_json:
        log.warning(
            "captions_missing video_id=%s playability_status=%s response_keys=%s",
            video_id,
            player_json.get("playabilityStatus"),
            list(player_json.keys()),
        )
        return {"error": "NO_CAPTIONS"}

    tracks = player_json["captions"]["playerCaptionsTracklistRenderer"]["captionTracks"]
    log.info("caption_tracks_found video_id=%s total=%s", video_id, len(tracks))

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
    log.info(
        "caption_track_selected video_id=%s lang=%s kind=%s",
        video_id,
        lang,
        selected.get("kind"),
    )

    log.info(f"📄 Sub URL: {track_url}")

    xml_resp = requests.get(track_url, headers=HEADERS, timeout=15)
    log.info("subtitle_xml.status=%s video_id=%s", xml_resp.status_code, video_id)
    xml_resp.raise_for_status()
    xml = xml_resp.text

    import xml.etree.ElementTree as ET
    try:
        root = ET.fromstring(xml)
    except Exception:
        log.error("subtitle_xml_parse_error video_id=%s xml_snippet=%s", video_id, _snippet(xml))
        raise

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
def transcript(video_id: str, request: Request):
    req_id = _request_id(video_id)
    client_key = request.headers.get("X-API-KEY")

    if client_key != API_KEY:
        log.warning("request_id=%s unauthorized_access video_id=%s", req_id, video_id)
        raise HTTPException(status_code=401, detail="Unauthorized")

    log.info("request_id=%s transcript_request video_id=%s", req_id, video_id)
    
    try:
        result = fetch_subtitles(video_id)
        if result.get("success"):
            response = {**result, "mode": "DIRECT", "request_id": req_id}
            log.info("request_id=%s transcript_success count=%s", req_id, response.get("count"))
            return response
        else:
            log.info("request_id=%s transcript_non_success result=%s", req_id, result)
            return result
    except Exception as exc:
        log_exception_details(request, exc, req_id, video_id=video_id)
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": "INTERNAL_SERVER_ERROR", "request_id": req_id},
        )
