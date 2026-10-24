"""Telegram bot: a customer sends a product photo with a filled-in form as the caption,
and gets back an animated reel + story made from template/reel.html.

Runs on a schedule (GitHub Actions). Telegram keeps unconfirmed updates for 24h, so each
run reads the pending updates, handles them, then confirms them with the next offset.

Usage: python bot/bot.py check   -> prints has_work=true|false (for the workflow)
       python bot/bot.py run     -> handle all pending messages
"""
import colorsys, io, json, os, re, subprocess, sys, tempfile
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageEnhance

ROOT = Path(__file__).resolve().parent.parent
TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
API = f"https://api.telegram.org/bot{TOKEN}"
FILE_API = f"https://api.telegram.org/file/bot{TOKEN}"

# Telegram usernames (without @) or numeric ids allowed to use the bot, comma separated; empty = everyone
ALLOWED = {x.strip().lstrip("@").lower() for x in os.environ.get("ALLOWED_USERS", "").split(",") if x.strip()}


def allowed(msg):
    user = msg.get("from") or {}
    return not ALLOWED or str(user.get("id")) in ALLOWED or (user.get("username") or "").lower() in ALLOWED


# with an Anthropic key the specs and name are read from the box photo, so the form is short
AI = bool(os.environ.get("ANTHROPIC_API_KEY"))

FORM = """السعر: 14000
النكهات:
- عنب مثلج
- فراولة وركي
- نعناع مثلج""" if AI else """الاسم: VOZOL RAVE 40000
السعر: 14000
الوصف: 40 ألف سحبة تطوّل وياك
المواصفات:
- عدد السحبات: 40,000 سحبة
- البطارية: 650 mAh
- الشحن: سريع Type-C
- النيكوتين: 2%
النكهات:
- عنب مثلج
- فراولة وركي
- نعناع مثلج"""

HELP = (
    "هلا بيك بمكتب التوام 👋\n\n"
    "حتى أسويلك ريلز وستوري وكابشن للمنتج:\n"
    "1️⃣ دز *صورة وحدة* للمنتج، والأفضل الكارتون من القدام وتكون المواصفات واضحة.\n"
    "2️⃣ وبنفس الرسالة، بخانة التعليق (Caption) انسخ هذا الفورم وعدّله:\n\n"
    f"```\n{FORM}\n```\n\n"
    + ("المواصفات واسم المنتج آني أقراها من الكارتون. " if AI else "الوصف اختياري. ")
    + "خلال 5 إلى 15 دقيقة يوصلك الفيديو جاهز 🎬"
)

SPEC_ICONS = [("سحب", "💨"), ("puff", "💨"), ("بطاري", "🔋"), ("mah", "🔋"), ("شحن", "⚡"),
              ("نيكوتين", "🧪"), ("nic", "🧪"), ("شاش", "📊"), ("كويل", "🔥"), ("coil", "🔥"),
              ("سعة", "💧"), ("مل", "💧"), ("وضع", "🚀"), ("mode", "🚀"), ("وزن", "⚖️"), ("حجم", "📏")]
FLAVORS = [("عنب", "🍇", "#7B2CBF"), ("فراول", "🍓", "#E63946"), ("فرول", "🍓", "#E63946"),
           ("ركي", "🍉", "#E5383B"), ("بطيخ", "🍉", "#E5383B"), ("نعناع", "🌿", "#14A39A"),
           ("خوخ", "🍑", "#FF7F6B"), ("منك", "🥭", "#F3A712"), ("مانج", "🥭", "#F3A712"),
           ("بلوبيري", "🫐", "#3A6FF7"), ("توت", "🫐", "#5A4FCF"), ("تفاح", "🍏", "#5CB338"),
           ("ليمون", "🍋", "#E9C46A"), ("كرز", "🍒", "#C1121F"), ("موز", "🍌", "#E9C46A"),
           ("اناناس", "🍍", "#F4A261"), ("أناناس", "🍍", "#F4A261"), ("كولا", "🥤", "#6F1D1B"),
           ("قهوة", "☕", "#7F5539"), ("رمان", "🍎", "#9D0208"), ("كيوي", "🥝", "#70A83B"),
           ("جوز الهند", "🥥", "#A68A64"), ("فانيل", "🍦", "#D4A373"), ("لوف", "💖", "#F15BB5"),
           ("ثلج", "❄️", "#4CC9F0"), ("مثلج", "❄️", "#4CC9F0")]
PALETTE = ["#7B2CBF", "#E63946", "#F15BB5", "#14A39A", "#F3A712", "#3A6FF7", "#FF7F6B", "#5CB338"]


def tg(method, **params):
    r = requests.post(f"{API}/{method}", data=params, timeout=60)
    return r.json()


def send(chat, text, markdown=True):
    params = {"parse_mode": "Markdown"} if markdown else {}
    tg("sendMessage", chat_id=chat, text=text, **params)


# ---------- form parsing ----------
def parse_form(text):
    data = {"name": "", "price": "", "tagline": "", "specs": [], "flavors": []}
    section = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        m = re.match(r"^(اسم المنتج|الاسم|السعر|الوصف|المواصفات|النكهات|الاطعام|الأطعام|الطعم)\s*[:：]?\s*(.*)$", line)
        if m:
            key, rest = m.group(1), m.group(2).strip()
            if key in ("الاسم", "اسم المنتج"):
                data["name"], section = rest, None
            elif key == "السعر":
                data["price"], section = rest, None
            elif key == "الوصف":
                data["tagline"], section = rest, None
            elif key == "المواصفات":
                section = "specs"
                if rest:
                    data["specs"] += [x.strip() for x in re.split(r"[،,]", rest) if x.strip()]
            else:
                section = "flavors"
                if rest:
                    data["flavors"] += [x.strip() for x in re.split(r"[،,]", rest) if x.strip()]
            continue
        item = re.sub(r"^([-•*·▪️✅]+|\d+[.)-])\s*", "", line)
        if section and item:
            data[section].append(item)
    return data


def spec_entry(item):
    label, value = "", item
    if ":" in item:
        label, value = [x.strip() for x in item.split(":", 1)]
    low = item.lower()
    icon = next((ic for k, ic in SPEC_ICONS if k in low), "✨")
    return {"icon": icon, "label": label, "value": value}


def flavor_entry(name, i):
    for k, emoji, color in FLAVORS:
        if k in name:
            return {"name": name, "emoji": emoji, "color": color}
    return {"name": name, "emoji": "🍬", "color": PALETTE[i % len(PALETTE)]}


def format_price(p):
    digits = re.sub(r"[^\d]", "", p.translate(str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")))
    if digits and len(digits) >= 3:
        return f"السعر {int(digits):,} دينار فقط"
    return f"السعر {p}" if p else ""


# ---------- image ----------
def product_colors(img):
    small = img.convert("RGB").resize((120, 120)).quantize(10).convert("RGB")
    counts = sorted(small.getcolors(20000), reverse=True)
    picks = []
    for _, (r, g, b) in counts:
        h, l, s = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
        if s > .35 and .2 < l < .75:
            hx = "#%02X%02X%02X" % tuple(int(c * 255) for c in colorsys.hls_to_rgb(h, .5, max(s, .7)))
            if all(abs(colorsys.rgb_to_hls(*[int(p[i:i + 2], 16) / 255 for i in (1, 3, 5)])[0] - h) > .06 for p in picks):
                picks.append(hx)
        if len(picks) == 2:
            break
    return (picks + ["#8B3DFF", "#1F6BFF"])[:2]


def prepare_image(src, dst, box=None):
    """Crop the product out of the photo: to the box Claude found (0-1000 coords), else a centre crop."""
    img = Image.open(src).convert("RGB")
    W, H = img.size
    if box and len(box) == 4 and box[2] - box[0] > 50 and box[3] - box[1] > 50:
        l, t, r, b = box[0] * W / 1000, box[1] * H / 1000, box[2] * W / 1000, box[3] * H / 1000
        pad = .015 * max(W, H)
        img = img.crop((max(0, l - pad), max(0, t - pad), min(W, r + pad), min(H, b + pad)))
    else:
        h = int(H * .72)
        w = min(W, int(h * .82))
        cx, cy = W // 2, int(H * .45)
        top = max(0, min(H - h, cy - h // 2))
        left = max(0, min(W - w, cx - w // 2))
        img = img.crop((left, top, left + w, top + h))
    img = ImageEnhance.Color(ImageEnhance.Contrast(img).enhance(1.06)).enhance(1.1)
    if img.height < 1000:
        img = img.resize((int(img.width * 1000 / img.height), 1000), Image.LANCZOS)
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, img.width - 1, img.height - 1), radius=44, fill=255)
    img.putalpha(mask)
    img.save(dst)
    return product_colors(img)


# ---------- order ----------
def handle_order(chat, msg):
    form = parse_form(msg.get("caption", ""))
    needed = (("السعر", "price"), ("النكهات", "flavors")) if AI else (("الاسم", "name"), ("النكهات", "flavors"))
    missing = [n for n, k in needed if not form[k]]
    if missing:
        send(chat, "⚠️ ناقص بالفورم: " + "، ".join(missing) + "\n\n" + HELP)
        return
    send(chat, "استلمنا طلبك ✅\nقيد التصميم ⏳ راح يوصلك الريلز والستوري والكابشن خلال دقائق.")

    work = Path(tempfile.mkdtemp())
    path = tg("getFile", file_id=image_of(msg))["result"]["file_path"]
    raw = requests.get(f"{FILE_API}/{path}", timeout=60).content
    (work / "raw.jpg").write_bytes(raw)

    read, caption = {}, ""
    if AI:
        import vision
        jpeg = io.BytesIO()
        Image.open(io.BytesIO(raw)).convert("RGB").save(jpeg, "JPEG", quality=92)
        try:
            read = vision.analyze(jpeg.getvalue(), "image/jpeg", form["price"], form["flavors"], form["tagline"])
            caption = read.get("caption", "")
        except Exception as e:  # still deliver a design from the form if reading the box fails
            print("vision failed:", e, file=sys.stderr)
    colors = prepare_image(work / "raw.jpg", work / "product.png", read.get("box"))
    hexes = [c for c in read.get("colors", []) if re.fullmatch(r"#[0-9A-Fa-f]{6}", c)]

    specs = [spec_entry(s) for s in form["specs"][:7]] or [
        {"icon": s["icon"], "label": s["label"], "value": s["value"]} for s in read.get("specs", [])[:6]]
    tagline = form["tagline"] or read.get("tagline") or "وصل جديد… لا يفوتك"
    product = {
        "name": form["name"] or read.get("name") or "منتج جديد", "nameEn": read.get("subtitle", ""),
        "colors": (hexes + colors)[:2], "image": "product.png",
        "tagline": tagline + " 🔥",
        "price": format_price(form["price"]),
        "specs": specs or [{"icon": "✨", "label": "", "value": "جودة أصلية مضمونة"}],
        "flavors": [flavor_entry(f, i) for i, f in enumerate(form["flavors"][:12])],
    }
    (work / "product.json").write_text(json.dumps(product, ensure_ascii=False), encoding="utf-8")

    for mode in ("reel", "story"):
        out = work / f"{mode}.mp4"
        subprocess.run(["node", str(ROOT / "template/render.js"), str(work / "product.json"), mode, str(out)],
                       check=True, cwd=ROOT / "template")
        with open(out, "rb") as f:
            caption = "🎬 الريلز جاهز" if mode == "reel" else "📱 الستوري جاهز"
            requests.post(f"{API}/sendVideo", data={"chat_id": chat, "caption": caption, "supports_streaming": "true",
                                                    "width": 1080, "height": 1920},
                          files={"video": (f"{mode}.mp4", f, "video/mp4")}, timeout=300)
    if caption:
        send(chat, "📝 الكابشن، انسخه ويه الريلز:")
        send(chat, caption, markdown=False)
    send(chat, "تم ✅ الفيديو بي موسيقى، وإذا تحب تكدر تبدلها بأغنية ترند من انستكرام 🎵\n📞 07515341547")


def pending():
    return tg("getUpdates", timeout=0, allowed_updates=json.dumps(["message"])).get("result", [])


def image_of(msg):
    """file_id of the photo in a message: a normal photo, or an image sent as a file."""
    if msg.get("photo"):
        return max(msg["photo"], key=lambda p: p.get("file_size", 0))["file_id"]
    doc = msg.get("document") or {}
    if doc.get("mime_type", "").startswith("image/"):
        return doc["file_id"]
    return None


def main():
    updates = pending()
    print("updates:", [sorted((u.get("message") or {}).keys()) for u in updates], file=sys.stderr)
    if sys.argv[1:] == ["check"]:
        has = any(image_of(m) and allowed(m) for m in (u.get("message") or {} for u in updates))
        print(f"has_work={'true' if has else 'false'}")
        if not has and updates:  # only text messages: answer them here, no render needed
            run(updates)
        return
    run(updates)


def run(updates):
    # an album arrives as one message per photo with the caption on only one of them
    albums = {u["message"]["media_group_id"] for u in updates
              if (u.get("message") or {}).get("caption") and u["message"].get("media_group_id")}
    for u in updates:
        msg = u.get("message") or {}
        chat = msg.get("chat", {}).get("id")
        if not chat or (msg.get("media_group_id") in albums and not msg.get("caption")):
            continue
        try:
            if not allowed(msg):
                send(chat, "هذا البوت خاص 🔒 للتواصل ويه مكتب التوام: 07515341547")
            elif image_of(msg):
                handle_order(chat, msg)
            else:
                send(chat, HELP)
        except Exception as e:  # keep going for other customers
            print("order failed:", e, file=sys.stderr)
            send(chat, "صار خطأ بالتصميم 😕 جرّب ترجع تدز الصورة ويه الفورم، أو اتصل 07515341547")
    if updates:
        tg("getUpdates", offset=updates[-1]["update_id"] + 1, timeout=0)


if __name__ == "__main__":
    main()
