import traceback
import logging
import requests
from fastapi import FastAPI, Request, HTTPException

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("yt-rev")

app = FastAPI()

API_KEY = "x9J2f8S2pA9W-qZvB"

# ✔ Stable Android Innertube key (no scraping required)
INNERTUBE_API_KEY = "AIzaSyAO_FJ2slcYkHfPDXz9fm1E1JY2Eo9uVDo"

HEADERS = {
    "User-Agent": "com.google.android.youtube/19.08.35 (Linux; Android 13)",
    "Accept-Language": "en-US,en;q=0.9",
}

# Payload rotation - like your old working method but HTML free
PAYLOADS = [
    {"context":{"client":{"clientName":"ANDROID","clientVersion":"19.08.35"}}},
    {"context":{"client":{"clientName":"ANDROID","clientVersion":"19.06.38"}}},
    {"context":{"client":{"clientName":"ANDROID","clientVersion":"19.04.36"}}},
    {"context":{"client":{"clientName":"WEB","clientVersion":"2.20240212.00.00"}}},
    {"context":{"client":{"clientName":"WEB","clientVersion":"2.20230812.00.00"}}},
]

rot = 0
def next_payload(video_id):
    global rot
    p = PAYLOADS[rot].copy()
    p["videoId"] = video_id
    rot = (rot+1) % len(PAYLOADS)
    return p


# ================= DIRECT INTERNAL API =================
def fetch_subtitles(video_id, preferred_lang=None):
    try:
        payload = next_payload(video_id)

        url = f"https://youtubei.googleapis.com/youtubei/v1/player?key={INNERTUBE_API_KEY}"
        data = requests.post(url, json=payload, headers=HEADERS, timeout=10).json()

        if "captions" not in data:
            return {"success": False, "error": "NO_CAPTIONS"}

        tracks = data["captions"]["playerCaptionsTracklistRenderer"]["captionTracks"]

        # language priority
        track = None
        if preferred_lang:
            track = next((t for t in tracks if t.get("languageCode")==preferred_lang),None)
        if not track:
            track = tracks[0]

        xml = requests.get(track["baseUrl"], headers=HEADERS, timeout=10).text

        import xml.etree.ElementTree as ET
        root = ET.fromstring(xml)

        subs=[]
        for node in root.iter("text"):
            subs.append({
                "text":(node.text or "").replace("\n"," ").strip(),
                "start":float(node.attrib.get("start",0)),
                "duration":float(node.attrib.get("dur",0)),
            })

        return {
            "success":True,
            "lang":track.get("languageCode"),
            "count":len(subs),
            "subtitles":subs
        }

    except:
        log.error(traceback.format_exc())
        return {"success":False,"error":"INTERNAL_ERROR"}



# ================= API Routes =================
@app.get("/")
def home():
    return {"status":"running","use":"/transcript?video_id=xxxx"}


@app.get("/transcript")
def transcript(video_id:str, request:Request):
    if request.headers.get("X-API-KEY")!=API_KEY:
        raise HTTPException(401,"Invalid API Key")

    return fetch_subtitles(video_id)
