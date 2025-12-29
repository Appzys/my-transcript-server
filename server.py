import json
import random
import string
import requests
import traceback

def generate_visitor_data():
    return ''.join(random.choices(string.ascii_letters + string.digits, k=16))

def fetch_subtitles(video_id: str, preferred_lang=None):

    try:
        INNERTUBE_KEY = "AIzaSyAO_FJ2p5z1o0QGl7z0aB7q0pQ_Po8h3zM"   # <== Stable working key
        url = f"https://youtubei.googleapis.com/youtubei/v1/player?key={INNERTUBE_KEY}"

        payload = {
            "context": {
                "client": {
                    "clientName": "ANDROID",
                    "clientVersion": "19.08.35",
                    "androidSdkVersion": 33
                },
                "user": {"lockedSafetyMode": False},
                "request": {
                    "useSsl": True,
                    "internalExperimentFlags": [],
                    "consistencyTokenJars": []
                }
            },
            "videoId": video_id
        }

        headers = {
            "User-Agent": HEADERS["User-Agent"],
            "X-Goog-Visitor-Id": generate_visitor_data(),
            "Origin": "https://www.youtube.com",
            "Referer": "https://www.youtube.com",
            "Cookie": "CONSENT=YES+cb",               # <== Consent bypass
        }

        player_json = requests.post(url, json=payload, headers=headers, timeout=15).json()

        if "captions" not in player_json:
            raise Exception("No captions found / subtitles disabled / paywalled")

        tracks = player_json["captions"]["playerCaptionsTracklistRenderer"]["captionTracks"]

        # language selection
        selected = None
        if preferred_lang:
            selected = next((t for t in tracks if t.get("languageCode")==preferred_lang),None)
        if not selected:
            selected = next((t for t in tracks if not t.get("kind")),None)
        if not selected:
            selected = tracks[0]

        sub_url = selected["baseUrl"]
        lang = selected.get("languageCode","unknown")

        xml = requests.get(sub_url).text
        import xml.etree.ElementTree as ET
        root = ET.fromstring(xml)

        subs=[]
        for node in root.iter("text"):
            subs.append({
                "text": (node.text or "").replace("\n"," ").strip(),
                "start": float(node.attrib.get("start",0)),
                "duration": float(node.attrib.get("dur",0)),
                "lang": lang
            })

        if not subs:       # SRV3 format
            for node in root.iter("p"):
                chunks=[s.text.strip() for s in node.iter("s") if s.text]
                text=" ".join(chunks) if chunks else (node.text or "")
                subs.append({
                    "text": text,
                    "start": float(node.attrib.get("t",0))/1000,
                    "duration": float(node.attrib.get("d",0))/1000,
                    "lang":lang
                })

        return {"success":True,"lang":lang,"count":len(subs),"subtitles":subs}

    except Exception as e:
        log.error(traceback.format_exc())
        return {"success":False,"error":str(e)}
