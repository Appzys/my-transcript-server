import traceback
import logging
import requests, random, string
from fastapi import FastAPI, Request, HTTPException

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("yt-rev")

app = FastAPI()

def rand_string(n=16):
    return ''.join(random.choices(string.ascii_letters+string.digits,k=n))

# Cookie bypass for CAPTCHA/Consent
def generate_cookie():
    return {
        "CONSENT": "YES+cb",
        "VISITOR_INFO1_LIVE": rand_string(11),
        "PREF": "f6=50000000&hl=en",
        "YSC": rand_string(20)
    }

HEADERS = {
    "User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
    "Accept-Language":"en-US,en;q=0.9",
    "Referer":"https://www.youtube.com",
    "Accept":"text/html,application/json"
}

API_KEY="x9J2f8S2pA9W-qZvB"

# ROTATION PAYLOAD
PAYLOADS=[
    {"context":{"client":{"clientName":"ANDROID","clientVersion":"19.08.35","androidSdkVersion":33}}},
    {"context":{"client":{"clientName":"ANDROID","clientVersion":"19.06.38","androidSdkVersion":33}}},
    {"context":{"client":{"clientName":"ANDROID","clientVersion":"19.06.38","androidSdkVersion":32}}},
    {"context":{"client":{"clientName":"WEB","clientVersion":"2.20240101.00.00","browserName":"Chrome","platform":"DESKTOP"}}},
    {"context":{"client":{"clientName":"WEB","clientVersion":"2.20240212.00.00","browserName":"Chrome","platform":"DESKTOP"}}},
]

i=0
def get_payload(video_id):
    global i
    p=PAYLOADS[i].copy()
    p["videoId"]=video_id
    i=(i+1)%len(PAYLOADS)
    return p


# ==================== SUB FETCH LOGIC ======================
def fetch_subtitles(video_id,preferred_lang=None):
    try:
        cookie=generate_cookie()
        resp=requests.get(
            f"https://www.youtube.com/watch?v={video_id}",
            headers=HEADERS,
            cookies=cookie,
            timeout=15
        )

        html=resp.text
        log.info("\n=== HTML (1500 chars) ===")
        log.info(html[:1500])
        log.info("========================\n")

        import re
        key=re.search(r'"INNERTUBE_API_KEY"\s*:\s*"([^"]+)"',html) or \
            re.search(r'"innertubeApiKey"\s*:\s*"([^"]+)"',html)

        if not key:
            raise Exception("YT Blocked → Showing CAPTCHA/CONSENT page. Cookie applied, retry again.")

        api_key=key.group(1)
        log.info(f"✔ API_KEY extracted = {api_key}")

        url=f"https://youtubei.googleapis.com/youtubei/v1/player?key={api_key}&prettyPrint=false"
        payload=get_payload(video_id)

        player=requests.post(url,json=payload,headers=HEADERS,cookies=cookie,timeout=15).json()

        if "captions" not in player:
            raise Exception("No Captions Found")

        tracks=player["captions"]["playerCaptionsTracklistRenderer"]["captionTracks"]

        selected=None
        if preferred_lang:
            selected=next((t for t in tracks if t.get("languageCode")==preferred_lang),None)
        if not selected: selected=tracks[0]

        sub_url=selected["baseUrl"]
        xml=requests.get(sub_url,headers=HEADERS,cookies=cookie,timeout=15).text

        import xml.etree.ElementTree as ET
        root=ET.fromstring(xml)

        subs=[]
        for node in root.iter("text"):
            subs.append({
                "text":(node.text or "").replace("\n"," "),
                "start":float(node.attrib.get("start",0)),
                "duration":float(node.attrib.get("dur",0)),
            })

        return{
            "success":True,
            "count":len(subs),
            "language":selected.get("languageCode"),
            "subtitles":subs
        }

    except Exception as e:
        log.error(traceback.format_exc())
        return {"success":False,"error":str(e)}



# ================= API =================
@app.get("/")
def home():
    return {"status":"online","use":"/transcript?video_id=xxxxx"}


@app.get("/transcript")
def api(video_id:str,request:Request):
    if request.headers.get("X-API-KEY")!=API_KEY:
        raise HTTPException(401,"Invalid API KEY")

    return fetch_subtitles(video_id)
