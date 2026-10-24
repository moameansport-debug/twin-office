"""Publish a product's reel + story to Instagram via the Graph API.

Usage: python scripts/publish.py <product-slug> [reel|story|both]
Needs env IG_USER_ID, IG_ACCESS_TOKEN, and the videos served on GitHub Pages.
"""
import json, os, sys, time, urllib.parse, urllib.request

API = "https://graph.facebook.com/v21.0"
PAGES = os.environ.get("PAGES_BASE", "https://moameansport-debug.github.io/twin-office")
USER = os.environ["IG_USER_ID"]
TOKEN = os.environ["IG_ACCESS_TOKEN"]


def call(method, path, **params):
    params["access_token"] = TOKEN
    data = urllib.parse.urlencode(params).encode()
    url = f"{API}/{path}"
    if method == "GET":
        url, data = f"{url}?{data.decode()}", None
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=data, method=method)) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        sys.exit(f"Graph API error {e.code}: {e.read().decode()}")


def wait_public(url, tries=40):
    for _ in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, method="HEAD")) as r:
                if r.status == 200:
                    return
        except urllib.error.HTTPError:
            pass
        time.sleep(15)
    sys.exit(f"Video never became public: {url}")


def publish(kind, video_url, caption):
    wait_public(video_url)
    params = {"media_type": "REELS" if kind == "reel" else "STORIES", "video_url": video_url}
    if kind == "reel":
        params.update(caption=caption, share_to_feed="true")
    container = call("POST", f"{USER}/media", **params)["id"]
    for _ in range(60):
        status = call("GET", container, fields="status_code,status")
        if status.get("status_code") == "FINISHED":
            break
        if status.get("status_code") == "ERROR":
            sys.exit(f"Instagram rejected the {kind}: {status}")
        time.sleep(10)
    media = call("POST", f"{USER}/media_publish", creation_id=container)
    print(f"published {kind}: {media['id']}")


slug = sys.argv[1]
which = sys.argv[2] if len(sys.argv) > 2 else "both"
folder = os.path.join("products", slug)
caption = open(os.path.join(folder, "caption.txt"), encoding="utf-8").read().strip()
base = f"{PAGES}/products/{urllib.parse.quote(slug)}"
if which in ("reel", "both"):
    publish("reel", f"{base}/reel.mp4", caption)
if which in ("story", "both"):
    publish("story", f"{base}/story.mp4", "")
