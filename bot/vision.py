"""Read a product photo with Claude: name, specs printed on the box, where the product is in
the photo, its colours, and an Instagram caption in Iraqi Arabic."""
import base64
import json

import anthropic

MODEL = "claude-opus-5-5"

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["name", "subtitle", "tagline", "specs", "colors", "box", "caption"],
    "properties": {
        "name": {"type": "string", "description": "Brand + model as printed, e.g. VOZOL RAVE"},
        "subtitle": {"type": "string", "description": "Short English line under the name, e.g. 40000 PUFFS, or empty"},
        "tagline": {"type": "string", "description": "One catchy Iraqi Arabic line, max 28 characters, no emoji"},
        "specs": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["icon", "label", "value"],
                "properties": {
                    "icon": {"type": "string", "description": "One emoji"},
                    "label": {"type": "string", "description": "Arabic label, max 22 characters"},
                    "value": {"type": "string", "description": "Value, max 16 characters"},
                },
            },
        },
        "colors": {"type": "array", "items": {"type": "string", "description": "#RRGGBB"}},
        "box": {
            "type": "array", "items": {"type": "integer"},
            "description": "Product packaging bounding box [left, top, right, bottom], each 0-1000 relative to image size",
        },
        "caption": {"type": "string", "description": "Full Instagram caption"},
    },
}

PROMPT = """This photo shows an electronic hookah / disposable vape (usually its box) that the store
"مكتب التوام للنراكيل الإلكترونية" in Iraq is announcing on Instagram.

Read ONLY what is actually printed on the packaging and fill the fields:
- name: brand and model exactly as printed.
- specs: 4 to 6 of the most useful specs printed on the box (puffs, modes, battery, charging,
  coil, display, nicotine strength, capacity...). Translate labels to short Arabic; keep numbers and
  technical words (Type-C, Mesh, mAh) as printed. Never invent a spec that is not on the box.
  Skip health warnings and barcodes.
- colors: the two dominant vivid colours of the product/packaging.
- box: bounding box of the product packaging only (exclude hands and background).
- tagline: a short catchy line in Iraqi dialect about the strongest selling point.
- caption: an Instagram caption in Iraqi Arabic with emojis: a hook line announcing the new
  product, the specs as an emoji list, then the flavours list, then the price, then
  "📞 للطلب: 07763756593 (اتصال أو واتساب أو بالخاص)" and
  "🛵 التوصيل عن طريق تطبيق بلي لباب البيت", then 8-10 hashtags including #مكتب_التوام.

Price from the customer: {price}
Flavours from the customer: {flavors}
Extra notes from the customer: {notes}"""


def analyze(image_bytes, media_type, price, flavors, notes=""):
    client = anthropic.Anthropic()
    response = client.messages.create(
        model=MODEL,
        max_tokens=16000,
        output_config={"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}},
        # if a safety classifier declines, let the API retry on its recommended fallback model
        extra_headers={"anthropic-beta": "server-side-fallback-2026-07-01"},
        extra_body={"fallbacks": "default"},
        messages=[{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "media_type": media_type,
                                             "data": base64.standard_b64encode(image_bytes).decode()}},
                {"type": "text", "text": PROMPT.format(price=price or "غير محدد",
                                                       flavors="، ".join(flavors) or "غير محدد",
                                                       notes=notes or "لا يوجد")},
            ],
        }],
    )
    if response.stop_reason == "refusal":
        raise RuntimeError(f"model declined: {response.stop_details}")
    text = next(b.text for b in response.content if b.type == "text")
    return json.loads(text)
