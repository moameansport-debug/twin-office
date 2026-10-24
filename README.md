# مكتب التوام — Twin Office

قالب ريلز وستوري متحرك للنراكيل الإلكترونية، ونشر تلقائي على انستكرام.

- `template/` القالب (HTML) وسكربت التصدير `render.js`
- `products/<اسم-المنتج>/` بيانات كل منتج (`product.json`) والصور والفيديوهات (`reel.mp4`, `story.mp4`) والكابشن (`caption.txt`)
- `.github/workflows/publish.yml` ينشر المنتج على انستكرام (Actions ← Publish to Instagram ← Run workflow)

## التصدير
```
cd template
node render.js ../products/<slug>/product.json reel ../products/<slug>/reel.mp4
node render.js ../products/<slug>/product.json story ../products/<slug>/story.mp4
```

## الأسرار المطلوبة (Settings ← Secrets ← Actions)
- `IG_USER_ID`
- `IG_ACCESS_TOKEN`

## بوت تلكرام
الزبون يدز للبوت صورة المنتج وبالتعليق الفورم (الاسم، السعر، الوصف، المواصفات، النكهات)،
وكل 5 دقائق `.github/workflows/telegram-bot.yml` يشغّل `bot/bot.py` اللي يصمم الريلز والستوري ويرجّعهن للزبون.
يحتاج Secret باسم `TELEGRAM_BOT_TOKEN`، و`ANTHROPIC_API_KEY` (اختياري) حتى يقرأ المواصفات من الكارتون ويكتب الكابشن.
الموسيقى بيتات أصلية تتولد بـ `python template/music.py`.
