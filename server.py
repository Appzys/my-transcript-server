import random
import traceback
import logging
import requests
from fastapi import FastAPI

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("yt-rev")

app = FastAPI()

USERNAME = "txqylbdv"
PASSWORD = "qx2kyqif5zmk"

PROXIES = [
    "142.111.48.253:7030",
    "31.59.20.176:6754",
    "23.95.150.145:6114",
    "198.23.239.134:6540",
    "107.172.163.27:6543",
    "198.105.121.200:6462",
    "64.137.96.74:6641",
    "84.247.60.125:6095",
    "216.10.27.159:6837",
    "142.111.67.146:5611",
]


def get_proxy():
    ip = random.choice(PROXIES)
    p = {
        "http": f"http://{USERNAME}:{PASSWORD}@{ip}",
        "https": f"http://{USERNAME}:{PASSWORD}@{ip}"
    }
    log.info(f"🔁 Using proxy: {p['http']}")
    return p


HEADERS = {
    "User-Agent": "Mozilla/5.0 (Android 13; Pixel 7)",
}


@app.get("/")
def home():
    return {"status": "running", "proxies": len(PROXIES)}


@app.get("/transcript")
def get_transcript(video_id: str):

    for attempt in range(1, 6):
        try:
            proxy = get_proxy()

            # 1️⃣ Fetch the YouTube HTML to extract Innertube API key
            log.info(f"🌐 Fetching watch page for {video_id}...")
            html = requests.get(
                f"https://www.youtube.com/watch?v={video_id}",
                headers=HEADERS,
                proxies=proxy,
                timeout=15
            ).text

            api_key_match = '"INNERTUBE_API_KEY":"(.*?)"'
            import re
            key = re.search(api_key_match, html)

            if not key:
                raise Exception("No INNERTUBE_API_KEY found")

            api_key = key.group(1)

            log.info(f"🔑 Extracted API key: {api_key}")

            # 2️⃣ Call Internal YouTube Player API
            data = {
                "videoId": video_id,
                "context": {
                    "client": {
                        "clientName": "ANDROID",
                        "clientVersion": "19.08.35",
                        "androidSdkVersion": 33,
                        "deviceMake": "Google",
                        "deviceModel": "Pixel 7 Pro",
                        "osName": "Android",
                        "osVersion": "13"
                    }
                }
            }

            url = f"https://youtubei.googleapis.com/youtubei/v1/player?key={api_key}&prettyPrint=false"

            log.info("📡 Calling YouTube internal API...")

            r = requests.post(
                url,
                json=data,
                headers=HEADERS,
                proxies=proxy,
                timeout=15
            ).json()

            if "captions" not in r:
                return {"success": False, "error": "No subtitles available"}

            tracks = r["captions"]["playerCaptionsTracklistRenderer"]["captionTracks"]
            selected = tracks[0]  # choose best first match
            subtitle_url = selected["baseUrl"]

            lang = selected.get("languageCode", "unknown")
            log.info(f"🌍 Subtitle Language: {lang}")
            log.info(f"📄 Subtitle URL: {subtitle_url}")

            # 3️⃣ Download subtitles XML
            xml = requests.get(subtitle_url, proxies=proxy, timeout=15).text

            # 4️⃣ Parse XML subtitles
            import xml.etree.ElementTree as ET

            root = ET.fromstring(xml)
            subtitles = []

            for node in root.iter("text"):
                subtitles.append({
                    "text": node.text.replace("\n", " ") if node.text else "",
                    "start": float(node.attrib.get("start", "0")),
                    "duration": float(node.attrib.get("dur", "0")),
                    "lang": lang
                })

            if len(subtitles) == 0:
                for node in root.iter("p"):
                    subtitles.append({
                        "text": node.text.replace("\n", " ") if node.text else "",
                        "start": float(node.attrib.get("t", "0")) / 1000,
                        "duration": float(node.attrib.get("d", "0")) / 1000,
                        "lang": lang
                    })

            log.info(f"✅ Extracted {len(subtitles)} subtitles")

            return {
                "success": True,
                "video_id": video_id,
                "language": lang,
                "count": len(subtitles),
                "preview": subtitles[:5],
                "proxy_used": proxy["http"],
                "attempt": attempt,
                "subtitles": subtitles
            }

        except Exception as e:
            log.warning(f"⚠️ Attempt {attempt} failed: {e}")
            log.warning(traceback.format_exc())

    return {"success": False, "error": "All proxy attempts failed"}
