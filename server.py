import traceback
import logging
import requests
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from datetime import datetime, timezone

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("yt-rev")

app = FastAPI()

API_KEY = "x9J2f8S2pA9W-qZvB"
SENSITIVE_HEADERS = {"x-api-key", "authorization", "cookie", "set-cookie"}

# ======== CLIENT HEADERS PER PAYLOAD ========
ANDROID_HEADERS = {
    "User-Agent": "com.google.android.youtube/20.19.08 (Linux; Android 14)",
    "Accept-Language": "en-US,en;q=0.9",
}

WEB_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9"
}

def _snippet(text: str, limit: int = 400) -> str:
    compact = (text or "").replace("\n", " ").replace("\r", " ")
    return compact if len(compact) <= limit else compact[:limit] + "...(truncated)"

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
    return f"{video_id}-{ts}" if video_id else ts

def log_exception_details(request: Request | None, exc: Exception, req_id: str, video_id: str | None = None):
    log.error("request_id=%s error_type=%s error=%s", req_id, type(exc).__name__, str(exc))
    if request:
        client_host = request.client.host if request.client else "unknown"
        log.error(
            "request_id=%s method=%s path=%s query=%s client=%s headers=%s",
            req_id, request.method, request.url.path, dict(request.query_params),
            client_host, _masked_headers(dict(request.headers)),
        )
    if video_id:
        log.error("request_id=%s video_id=%s", req_id, video_id)
    log.error("request_id=%s traceback:\n%s", req_id, traceback.format_exc())

# ======== UPDATED 2026 PAYLOADS ========
PAYLOADS = [
    # ANDROID (recent known versions)
    {"context": {"client": {"clientName": "ANDROID", "clientVersion": "20.19.08", "androidSdkVersion": 34}}},
    {"context": {"client": {"clientName": "ANDROID", "clientVersion": "20.15.03", "androidSdkVersion": 33}}},
    {"context": {"client": {"clientName": "ANDROID", "clientVersion": "20.12.01", "androidSdkVersion": 33}}},
    # WEB (recent known versions)
    {"context": {"client": {"clientName": "WEB", "clientVersion": "2.20260101.00.00", "browserName": "Chrome", "platform": "DESKTOP"}}},
    {"context": {"client": {"clientName": "WEB", "clientVersion": "2.20260215.00.00", "browserName": "Chrome", "platform": "DESKTOP"}}},
    {"context": {"client": {"clientName": "WEB", "clientVersion": "2.20260320.00.00", "browserName": "Chrome", "platform": "DESKTOP"}}},
]

# ======== CORE REQUEST LOGIC WITH MULTI-PAYLOAD RETRIES ========
def fetch_subtitles(video_id: str, preferred_lang: str | None = None):
    log.info("fetch_subtitles.start video_id=%s preferred_lang=%s", video_id, preferred_lang)

    # 1️⃣ Fetch watch page
    page_resp = requests.get(f"https://www.youtube.com/watch?v={video_id}", headers=WEB_HEADERS, timeout=15)
    log.info("watch_page.status=%s url=%s", page_resp.status_code, page_resp.url)
    page_resp.raise_for_status()

    html = page_resp.text
    import re
    key_match = re.search(r'"INNERTUBE_API_KEY":"(.*?)"', html)
    if not key_match:
        log.error("innertube_key_missing video_id=%s html_snippet=%s", video_id, _snippet(html))
        raise Exception("Cannot extract innertube key")

    api_key = key_match.group(1)
    log.info("innertube_key_found video_id=%s key_prefix=%s", video_id, api_key[:8])

    url = f"https://youtubei.googleapis.com/youtubei/v1/player?key={api_key}&prettyPrint=false"

    # 2️⃣ Try all payloads
    last_non_captions = None
    for payload in PAYLOADS:
        client_ctx = payload["context"]["client"]
        clientName = client_ctx.get("clientName", "").upper()

        headers = ANDROID_HEADERS if clientName == "ANDROID" else WEB_HEADERS
        headers["Accept"] = "application/json"

        log.info("trying payload client=%s headers_ua=%s", client_ctx, headers["User-Agent"])
        payload["videoId"] = video_id

        player_resp = requests.post(url, json=payload, headers=headers, timeout=15)
        log.info("player_api.status=%s client=%s", player_resp.status_code, client_ctx)
        if player_resp.status_code != 200:
            log.warning("player_api_non_200 video_id=%s client=%s text=%s", video_id, client_ctx, _snippet(player_resp.text))
            continue

        try:
            player_json = player_resp.json()
        except Exception:
            log.error("player_api_invalid_json video_id=%s response_snippet=%s", video_id, _snippet(player_resp.text))
            continue

        # 3️⃣ Check playabilityStatus
        play_status = player_json.get("playabilityStatus", {})
        status = play_status.get("status")
        reason = play_status.get("reason")
        log.info("playabilityStatus status=%s reason=%s", status, reason)

        if status != "OK":
            last_non_captions = {"status": status, "reason": reason}
            log.warning("UNPLAYABLE for client=%s", client_ctx)
            continue

        # 4️⃣ Captions present?
        if "captions" not in player_json:
            log.warning("captions_missing video_id=%s client=%s", video_id, client_ctx)
            last_non_captions = {"error": "NO_CAPTIONS"}
            continue

        # 5️⃣ Extract tracks
        tracks = player_json["captions"]["playerCaptionsTracklistRenderer"]["captionTracks"]
        log.info("caption_tracks_found video_id=%s total=%s client=%s", video_id, len(tracks), client_ctx)

        # 6️⃣ Choose track
        selected = None
        if preferred_lang:
            selected = next((t for t in tracks if t.get("languageCode") == preferred_lang and not t.get("kind")), None)
        if not selected:
            selected = next((t for t in tracks if not t.get("kind")), None)
        if not selected:
            selected = next((t for t in tracks if t.get("kind")), None)
        if not selected and tracks:
            selected = tracks[0]
        if not selected:
            return {"error": "NO_TRACKS"}

        track_url = selected["baseUrl"]
        lang = selected.get("languageCode", "unknown")
        log.info("caption_track_selected lang=%s kind=%s", lang, selected.get("kind"))

        # 7️⃣ Fetch caption XML
        xml_resp = requests.get(track_url, headers=headers, timeout=15)
        log.info("subtitle_xml.status=%s video_id=%s", xml_resp.status_code, video_id)
        xml_resp.raise_for_status()

        import xml.etree.ElementTree as ET
        try:
            root = ET.fromstring(xml_resp.text)
        except Exception:
            log.error("subtitle_xml_parse_error video_id=%s xml_snippet=%s", video_id, _snippet(xml_resp.text))
            raise

        subs = []
        format_used = "text"
        for node in root.iter("text"):
            subs.append({
                "text": (node.text or "").replace("\n", " ").strip(),
                "start": float(node.attrib.get("start", 0)),
                "duration": float(node.attrib.get("dur", 0)),
                "lang": lang
            })
        if not subs:
            format_used = "srv3"
            for node in root.iter("p"):
                chunks = [s.text.strip() for s in node.iter("s") if s.text]
                text_val = " ".join(chunks) if chunks else (node.text or "").strip()
                subs.append({"text": text_val, "start": float(node.attrib.get("t", 0)) / 1000,
                             "duration": float(node.attrib.get("d", 0)) / 1000, "lang": lang})

        return {"success": True, "count": len(subs), "lang": lang, "format": format_used, "subtitles": subs}

    # If we exit loop with no captions
    log.info("transcript_non_success result=%s", last_non_captions)
    return last_non_captions or {"error": "FAILED_ALL_PAYLOADS"}

# ======== API ROUTE ========
@app.get("/transcript")
def transcript(video_id: str, request: Request):
    req_id = _request_id(video_id)
    client_key = request.headers.get("X-API-KEY")

    if client_key != API_KEY:
        log.warning("request_id=%s unauthorized_access", req_id)
        raise HTTPException(status_code=401, detail="Unauthorized")

    log.info("request_id=%s transcript_request", req_id)
    try:
        result = fetch_subtitles(video_id)
        if result.get("success"):
            log.info("request_id=%s transcript_success count=%s", req_id, result["count"])
            return {**result, "mode": "DIRECT", "request_id": req_id}
        else:
            log.info("request_id=%s transcript_non_success result=%s", req_id, result)
            return result
    except Exception as exc:
        log_exception_details(request, exc, req_id, video_id)
        return JSONResponse(status_code=500,
                            content={"success": False, "error": "INTERNAL_SERVER_ERROR", "request_id": req_id})
