#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Build the "Sephora Favorites" digital catalog (grouped-variant model).
Reads knowledge/<id>/product.json, groups shade-variants under one card,
copies images, and emits catalog/index.html (data inline → works from file://).
Re-run after adding products to knowledge/ or editing catalog_overrides.json.
"""
import json, glob, os, shutil, re

# ---- image optimization on copy (keeps the published GitHub Pages site well under the 1GB limit
#      and makes the catalog load far faster). Downscales to max 720px + recompresses. ----
IMG_MAXDIM = 720
def optimize_image(src, dst):
    try:
        from PIL import Image, ImageOps
        im = ImageOps.exif_transpose(Image.open(src))
        w, h = im.size
        m = max(w, h)
        if m > IMG_MAXDIM:
            r = IMG_MAXDIM / float(m)
            im = im.resize((max(1, int(w * r)), max(1, int(h * r))), Image.LANCZOS)
        ext = os.path.splitext(dst)[1].lower()
        if ext == ".png":
            im.save(dst, "PNG", optimize=True)
        elif ext == ".webp":
            im.save(dst, "WEBP", quality=74, method=4)
        else:
            if im.mode in ("RGBA", "LA", "P"):
                rgba = im.convert("RGBA")
                bg = Image.new("RGB", rgba.size, (255, 255, 255))
                bg.paste(rgba, mask=rgba.split()[-1])
                im = bg
            else:
                im = im.convert("RGB")
            im.save(dst, "JPEG", quality=72, optimize=True, progressive=True)
        return True
    except Exception:
        shutil.copy2(src, dst)
        return False

# ---- shade -> swatch color (from the shade NAME, since shade-specific images
#      are often unavailable / shared across the line) ----
COLOR_WORDS = [
    ("chocolate", "#4a2c1d"), ("espresso", "#3d281c"), ("mocha", "#5b3a28"), ("coffee", "#4a3120"),
    ("butterscotch", "#d99e54"), ("caramel", "#b5793f"), ("toffee", "#9c6a3c"), ("cinnamon", "#8a4b2a"),
    ("honey", "#d9a martyr"[:7] if False else "#d6a14b"), ("amber", "#b06a2c"), ("copper", "#b0673c"),
    ("bronze", "#9a6a3a"), ("golden", "#c8a24a"), ("gold", "#c8a24a"),
    ("raspberry", "#a32a5a"), ("cherry", "#9b1b30"), ("ruby", "#9b1b30"), ("berry", "#8e2f54"),
    ("rose", "#cf6d86"), ("pinkgasm", "#ef7fa6"), ("peachgasm", "#f59a78"), ("peachy", "#f6a888"),
    ("peach", "#f6a888"), ("coral", "#fb7a5a"), ("pink", "#ec9ec0"), ("red", "#c0392b"),
    ("plum", "#6e2a5a"), ("mauve", "#9c6f86"), ("nude", "#d3a07f"), ("spice", "#9c5a3c"),
    ("sand", "#d8c19a"), ("beige", "#dcc6a6"), ("star", "#caa85a"), ("vanilla", "#ead9bd"),
    ("milkshake", "#efddc7"), ("custard", "#e7c79a"), ("latte", "#c79a6e"), ("macchiato", "#a9764a"),
]
DEPTHS = [("porcelain", .08), ("fair", .17), ("light-medium", .34), ("light", .25),
          ("medium", .5), ("tan", .66), ("deep", .82), ("rich", .9), ("dark", .92), ("ebony", .95)]

def _skin_hex(depth, under):
    lo, hi = (246, 223, 197), (70, 43, 28)   # light beige -> deep brown
    r = int(lo[0] + (hi[0]-lo[0])*depth); g = int(lo[1]+(hi[1]-lo[1])*depth); b = int(lo[2]+(hi[2]-lo[2])*depth)
    if under in ("w", "g"): r = min(255, r+8); b = max(0, b-12)     # warm / golden
    elif under in ("c", "p"): r = max(0, r-6); b = min(255, b+12)   # cool / pink
    elif under == "r": r = min(255, r+12); g = max(0, g-5)          # red
    return "#%02x%02x%02x" % (r, g, b)

def shade_color(shade):
    if not shade:
        return None
    s = shade.lower()
    sk = next((d for w, d in sorted(DEPTHS, key=lambda x: -len(x[0])) if w in s), None)
    mnum = re.search(r"(\d+(?:\.\d+)?)", s)
    mund = re.search(r"\d+(?:\.\d+)?\s*([nwcrgp]{1,2})\b", s)
    under = mund.group(1)[0] if mund else None
    sig = []
    if sk is not None:
        sig.append(sk)
    if mnum:
        n = float(mnum.group(1))
        if n >= 100:
            n /= 100.0
        sig.append(max(.06, min(.95, (n-1)/8.0)) if n <= 10 else .5)
    if sig:   # skin tone (foundations / concealers / powders)
        return _skin_hex(sum(sig)/len(sig), under)
    for w, hx in COLOR_WORDS:   # color cosmetics (lip / blush / eyeshadow)
        if w in s:
            return hx
    return None

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KNOW = os.path.join(ROOT, "knowledge")
CAT  = os.path.join(ROOT, "catalog")
IMGDIR = os.path.join(CAT, "images")
OVERRIDES = os.path.join(CAT, "catalog_overrides.json")
ORDER_FILE = os.path.join(ROOT, "הזמנה 1.xlsx")

SITE_URL = "https://l3ilimport-alt.github.io/sephora-favorites"

# ---- brand normalization ----
BRAND_MAP = {
    "לא נמצא": "אחר", "לא ידוע": "אחר",
    "-417 (Minus 417) Dead Sea Cosmetics": "417", "Airspun (Coty)": "Airspun",
    "Schwarzkopf Professional": "Schwarzkopf", "Maybelline New York": "Maybelline",
    "Amorus USA": "Amorus", "Benefit Cosmetics": "Benefit",
    "Giorgio Armani": "Armani", "Armani Beauty": "Armani",
    "Charlotte Tilbury Beauty": "Charlotte Tilbury",
}
def norm_brand(b):
    if not b: return "אחר"
    return BRAND_MAP.get(b.strip(), b.strip())

# ---- product type (category) ----
FRAG = ["perfume", "fragrance", "eau de", "edp", "edt", "parfum", "בושם", "או דה"]
HAIR = ["שיער", "קרטין", "שמפו", "ווקס", "וקס", "ג'ל", "ג׳ל", "קליי", "חימר", "בלונד", "blond",
        "schwarzkopf", "3dmen", "מכונת תספורת", "תספורת", "קליפר", "trimmer", "clipper"]
SKIN = ["פילינג", "מסז", "רולר", "ספא", "אצטון", "סרום", "טיפוח", "ניקוי", "מסיר איפור", "פנים קרם", "לחות",
        "קרם פנים", "קרם עיניים", "קרם גוף", "קרם הגנה", "מסכת פנים", "מסכה", "מסיכה",
        "שקית תחת", "אנטי אייג", "טיפול מיידי", "הגנה מינרלי"]
# ---- קטגוריות חדשות (מחליפות את "אחר") ----
EQUIP  = ["ריהוט", "כיסא", "שולחן מניקור"]                                        # ציוד מקצועי / רהיטים
ACCESS = ["ריסים מלאכות", "מברש", "מכחול", "ספוג", "נרתיק", "תיק איפור", "תיק קוסמט", "אריזה",
          "שקית נשיאה", "סכין גילוח", "גילוח", "עדשות מגע", "מראת", "אפליקטור", "פאף"]   # אביזרים וכלים
NAILS  = ["ציפורנ", "מניקור", "טיפים לציפור", "soft gel", "לק ג'ל", "לק ג׳ל"]      # ציפורניים
# מונחי איפור חד-משמעיים — גוברים על "ג'ל"/"סרום"/"לחות"/"שיער" מקריים שמופיעים בתיאור
MAKEUP = ["שפתון", "ליפ", "גלוס", "גלוז", "סטיין", "lip", "gloss",
          "סומק", "בלאש", "blush", "מסקרה", "mascara", "צללי", "איישדו", "eyeshadow",
          "קונסילר", "concealer", "פאונדיישן", "foundation", "מייקאפ", "מייק-אפ", "מייק אפ", "makeup",
          "היילייטר", "highlight", "מאיר", "מבריק", "ברונזר", "bronzer", "אייליינר", "eyeliner",
          "עיפרון", "גבות", "brow", "פלטת", "palette", "פודר", "powder", "פריימר", "primer",
          "קונטור", "contour", "טינט", "tint", "צלליות", "ערכת איפור", "סט איפור", "איפור עיניים"]

def ptype(p):
    txt = " ".join(str(p.get(k) or "") for k in
                   ("name_he", "name_en", "category_refined", "category_excel", "excel_description")).lower()
    # קודם הסוגים הספציפיים שאינם קוסמטיקה
    if any(w in txt for w in EQUIP):  return "ציוד"
    if any(w in txt for w in ACCESS): return "אביזרים"
    if any(w in txt for w in NAILS):  return "ציפורניים"
    # איפור חד-משמעי — לפני שיער/טיפוח/בושם (מונע דליפת ג'ל-גבות/שפתון-סרום וכד')
    if any(w in txt for w in MAKEUP): return "איפור"
    if any(w in txt for w in FRAG):   return "בושם"
    if any(w in txt for w in HAIR):   return "שיער"
    if any(w in txt for w in SKIN):   return "טיפוח"
    if (p.get("category_excel") or "").lower() == "makeup": return "איפור"
    return "איפור"   # ברירת מחדל — הקטלוג ברובו איפור (אין יותר "אחר")

def whole_price(x):
    """עיגול מחיר למספר שלם (מחירי הקטלוג שלמים)."""
    try:
        return round(float(x))
    except (TypeError, ValueError):
        return x

def detect_vegan(p):
    t = " ".join(str(p.get(k) or "") for k in ("ingredients", "description", "key_features")).lower()
    return "vegan" in t or "טבעוני" in t

# ---- order-file filter ----
def _nbc(x):
    s = re.sub(r"\D", "", str(x or "")); return s.lstrip("0") or s
def _ndesc(x):
    return re.sub(r"\s+", " ", str(x or "").strip().lower())
def load_order_keys():
    bcs, descs = set(), set()
    try:
        import openpyxl
        wb = openpyxl.load_workbook(ORDER_FILE, read_only=True, data_only=True)
        for r in list(wb["Sheet1"].iter_rows(values_only=True))[1:]:
            if not r or not r[1]: continue
            if r[0]: bcs.add(_nbc(r[0]))
            descs.add(_ndesc(r[1]))
    except Exception as e:
        print("warning: no order file, showing all:", e); return None, None
    return bcs, descs

# ---- shade-grouping helpers ----
SHADE_WORDS = set("""fair clair claire medium deep tan dore dore doré fonce foncé neutral neutre warm
chaud cool light dark rich soft rose peach peachy berry nude gold golden silver bronze sand beige black
brown blonde blond pink red cherry original mink amber star walk shame chocolate galifornia hoola
dandelion pinkgasm peachgasm dreampop pop sunset jade lilas sable mini deluxe trio set""".split())
CODE = re.compile(r"^[0-9]+(\.[0-9]+)?[a-z]{0,4}$", re.I)

def _strip_trailing_shade(name):
    toks = name.split()
    while toks:
        last = toks[-1].strip("-–/.,()#")
        if not last:
            toks.pop(); continue
        if CODE.match(last) or last.lower() in SHADE_WORDS or len(last) <= 1:
            toks.pop()
        else:
            break
    return " ".join(toks)

def group_key(p, brand):
    base = p.get("excel_description") or p.get("name_en") or ""
    sh = p.get("shade") or ""
    if sh:
        base = re.sub(re.escape(sh), "", base, flags=re.I)
    base = re.sub(r"#?\d+\b", " ", base)              # drop numeric shade codes
    base = _strip_trailing_shade(re.sub(r"\s+", " ", base).strip())
    base = re.sub(r"[\s\-–/]+$", "", base).strip().lower()
    return (brand, ptype(p), base) if len(base) >= 6 else None

def _lcp(strings):
    if not strings: return ""
    s1, s2 = min(strings), max(strings)
    i = 0
    while i < len(s1) and i < len(s2) and s1[i] == s2[i]: i += 1
    return s1[:i]

def he_base(members):
    """Hebrew base name for a group: strip the shade from each member's name,
    then take the most common result (robust to one member leaking a shade)."""
    from collections import Counter
    bases = []
    for m in members:
        b = m["name_he"]; sh = m.get("shade") or ""
        if sh:
            b = re.sub(re.escape(sh), "", b, flags=re.I)
        b = re.sub(r"גוון\s*[^\s,–\-]*", "", b)          # "גוון X"
        b = re.sub(r"#?\d+(\.\d+)?[A-Za-z]{0,4}\b", "", b)  # shade codes
        b = re.sub(r"\s*[–\-]\s*,\s*", " ", b)             # dangling " – , "
        b = re.sub(r",\s*,", ",", b)
        b = re.sub(r"\s+", " ", b).strip(" –-,()|·")
        if b:
            bases.append(b)
    if not bases:
        return members[0]["name_he"]
    # prefer the most common; tie-break by shortest (the cleaner base)
    cnt = Counter(bases)
    top = cnt.most_common()
    best = sorted(top, key=lambda kv: (-kv[1], len(kv[0])))[0][0]
    return best

def main():
    if os.path.isdir(IMGDIR):
        shutil.rmtree(IMGDIR)
    os.makedirs(IMGDIR, exist_ok=True)

    overrides = {}
    try:
        ov = json.load(open(OVERRIDES, encoding="utf-8"))
        overrides = {k: v for k, v in ov.items() if not k.startswith("_")}
    except Exception:
        pass

    order_bc, order_desc = load_order_keys()
    excluded = []
    raw = []   # individual products (variants)

    for pj in sorted(glob.glob(os.path.join(KNOW, "[0-9]*", "product.json")),
                     key=lambda x: int(os.path.basename(os.path.dirname(x)).split("-")[0])):
        d = os.path.dirname(pj); pid = os.path.basename(d)
        try:
            p = json.load(open(pj, encoding="utf-8"))
        except Exception as e:
            print("skip", pj, e); continue

        if order_bc is not None:
            try: num = int(pid.split("-")[0])
            except ValueError: num = 0
            inb = _nbc(p.get("barcode"))
            in_order = (num >= 56) or (inb in order_bc and inb != "") \
                or (_ndesc(p.get("excel_description")) in order_desc)
            if not in_order:
                excluded.append(pid); continue

        # copy images
        src = os.path.join(d, "images"); imgs = []
        if os.path.isdir(src):
            files = sorted(f for f in os.listdir(src)
                           if f.lower().endswith((".jpg", ".jpeg", ".png", ".webp")))
            if files:
                os.makedirs(os.path.join(IMGDIR, pid), exist_ok=True)
            for f in files:
                optimize_image(os.path.join(src, f), os.path.join(IMGDIR, pid, f))
                imgs.append(f"images/{pid}/{f}")

        brand = norm_brand(p.get("brand"))
        ov = overrides.get(str(p.get("barcode") or ""), {})
        badges = list(ov.get("badges") or [])
        sale = whole_price(ov.get("sale_price")) if ov.get("sale_price") not in (None, "") else None
        if sale: badges = (["sale"] + badges) if "sale" not in badges else badges
        if detect_vegan(p): badges.append("vegan")

        raw.append({
            "id": pid,
            "name_he": p.get("name_he") or p.get("name_en") or pid,
            "name_en": p.get("name_en") or "",
            "brand": brand,
            "type": ptype(p),
            "price": whole_price(p.get("price_ils")),
            "sale": sale,
            "size": p.get("size") or "",
            "shade": p.get("shade") or "",
            "barcode": p.get("barcode") or "",
            "desc": p.get("description") or "",
            "features": p.get("key_features") or [],
            "ingredients": p.get("ingredients") or "",
            "usage": p.get("usage") or "",
            "desc_ar": p.get("description_ar") or "",
            "features_ar": p.get("features_ar") or [],
            "usage_ar": p.get("usage_ar") or "",
            "imgs": imgs,
            "badges": badges,
            "color": shade_color(p.get("shade") or ""),
            "_key": group_key(p, brand),
        })

    # ---- group shade-variants ----
    buckets = {}
    singles = []
    for p in raw:
        k = p["_key"]
        if k is None:
            singles.append(p)
        else:
            buckets.setdefault(k, []).append(p)

    groups = []
    def variant(p):
        d = {"id": p["id"], "shade": p["shade"] or p["name_he"], "price": p["price"],
                "sale": p["sale"], "size": p["size"], "barcode": p["barcode"], "imgs": p["imgs"],
                "desc": p["desc"], "features": p["features"], "ingredients": p["ingredients"],
                "usage": p["usage"], "badges": p["badges"], "color": p.get("color")}
        if p.get("desc_ar"): d["desc_ar"] = p["desc_ar"]
        if p.get("features_ar"): d["features_ar"] = p["features_ar"]
        if p.get("usage_ar"): d["usage_ar"] = p["usage_ar"]
        return d
    def make_group(members, base_he):
        members = sorted(members, key=lambda m: (m["shade"] or m["name_he"]))
        return {"gid": "g" + str(len(groups)), "name_he": base_he,
                "name_en": _strip_trailing_shade(members[0]["name_en"]),
                "brand": members[0]["brand"], "type": members[0]["type"],
                "variants": [variant(m) for m in members]}

    for k, members in buckets.items():
        if len(members) >= 2:
            groups.append(make_group(members, he_base(members)))
        else:
            singles.append(members[0])
    for p in singles:
        groups.append({"gid": "g" + str(len(groups)), "name_he": p["name_he"],
                       "name_en": p["name_en"], "brand": p["brand"], "type": p["type"],
                       "variants": [variant(p)]})

    # keep a stable, brand-grouped order
    groups.sort(key=lambda g: (g["brand"], g["name_he"]))
    for i, g in enumerate(groups): g["gid"] = "g" + str(i)

    og_image = (SITE_URL.rstrip("/") + "/og-image.png") if SITE_URL else "og-image.png"

    # ---- חיבור Supabase: מוזרק לדף כ-window.SUPA. ריק → הקטלוג עובד במצב וואטסאפ-טקסט בלבד ----
    supa_cfg = {"url": "", "anon": ""}
    try:
        sc = json.load(open(os.path.join(CAT, "supabase.config.json"), encoding="utf-8"))
        supa_cfg = {"url": sc.get("url") or "", "anon": sc.get("anon_key") or ""}
    except Exception:
        pass
    if supa_cfg["url"] and supa_cfg["anon"]:
        print(f"   Supabase מחובר: {supa_cfg['url']}")
    else:
        print("   Supabase לא מוגדר עדיין (catalog/supabase.config.json) — מצב וואטסאפ-טקסט בלבד")

    out = TEMPLATE.replace("/*__GROUPS__*/", json.dumps(groups, ensure_ascii=False))
    out = out.replace("__COUNT__", str(len(groups)))
    out = out.replace("__OG_IMAGE__", og_image)
    out = out.replace("__SUPABASE_CONFIG__", json.dumps(supa_cfg, ensure_ascii=False))
    with open(os.path.join(CAT, "index.html"), "w", encoding="utf-8") as f:
        f.write(out)

    multi = [g for g in groups if len(g["variants"]) > 1]
    nprod = sum(len(g["variants"]) for g in groups)
    nimg = sum(len(v["imgs"]) for g in groups for v in g["variants"])
    print(f"✅ index.html: {len(groups)} כרטיסים ({nprod} מוצרים, {nimg} תמונות)")
    print(f"   קבוצות-גוונים (>1 גוון): {len(multi)}")
    for g in sorted(multi, key=lambda g: -len(g["variants"]))[:8]:
        print(f"     · {g['name_he'][:42]} ({g['brand']}) — {len(g['variants'])} גוונים")
    print(f"   הוסרו (לא בהזמנה 1): {len(excluded)}")


TEMPLATE = r"""<!DOCTYPE html>
<html lang="he" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0">
<title>Sephora Favorites — קטלוג</title>
<meta name="description" content="הקולקציה הנבחרת — איפור, טיפוח, שיער ובושם מהמותגים האהובים">
<meta property="og:type" content="website">
<meta property="og:title" content="Sephora Favorites — קטלוג מוצרים">
<meta property="og:description" content="הקולקציה הנבחרת — איפור, טיפוח, שיער ובושם ✦ לחצו לצפייה והזמנה">
<meta property="og:image" content="__OG_IMAGE__">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:locale" content="he_IL">
<!-- חיבור Supabase (anon ציבורי). אם לא הוגדר — הקטלוג נופל חזרה למצב וואטסאפ-טקסט בלבד. -->
<script src="https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2/dist/umd/supabase.js"></script>
<script>window.SUPA=__SUPABASE_CONFIG__;</script>
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:image" content="__OG_IMAGE__">
<meta name="theme-color" content="#7c3aed">
<link rel="icon" type="image/svg+xml" href="favicon.svg">
<link rel="apple-touch-icon" href="favicon.svg">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Heebo:wght@300;400;500;700;900&family=Cormorant+Garamond:wght@500;600&display=swap" rel="stylesheet">
<style>
:root{
  --bg:#faf8ff; --surface:#ffffff; --border:#efe9f7; --border2:#e4daf5;
  --accent:#7c3aed; --accent-d:#5b21b6; --accent-l:#a855f7; --accent-soft:#f3edfe;
  --text:#1e1633; --muted:#8b85a0; --lux:#b9a16b;
  --radius:16px; --shadow:0 6px 28px rgba(91,33,182,.08); --shadow-h:0 14px 44px rgba(91,33,182,.16);
  --font:'Heebo',-apple-system,BlinkMacSystemFont,sans-serif;
}
*{box-sizing:border-box;margin:0;padding:0}
html{scroll-behavior:smooth}
html,body{background:var(--bg);color:var(--text);font-family:var(--font);-webkit-font-smoothing:antialiased;overflow-x:hidden}
body{padding-bottom:90px}
a{color:inherit}img{display:block}
::-webkit-scrollbar{height:0;width:0}

.brandbar{position:relative;display:flex;justify-content:center;align-items:center;padding:14px 16px 10px;background:var(--bg)}
.brandbar img{height:58px;width:auto;display:block;transition:transform .25s ease}
.brandbar img:hover{transform:translateY(-1px)}
.langbtn{position:absolute;inset-inline-start:16px;top:50%;transform:translateY(-50%);
  background:var(--surface);border:1px solid var(--border2);color:var(--accent-d);
  font-family:var(--font);font-size:13px;font-weight:500;padding:7px 14px;border-radius:30px;
  cursor:pointer;box-shadow:var(--shadow);transition:background .2s,transform .15s}
.langbtn:hover{background:var(--accent-soft);transform:translateY(-50%) scale(1.04)}
@media(max-width:640px){.brandbar img{height:46px}.brandbar{padding:11px 16px 7px}.langbtn{font-size:12px;padding:6px 11px;inset-inline-start:12px}}
.herobanner{width:100%;line-height:0;border-bottom:1px solid var(--border)}
.herobanner img{width:100%;height:auto;display:block;max-height:560px;object-fit:cover;object-position:center}
@media(max-width:640px){.herobanner img{max-height:none}}
.hero{text-align:center;padding:30px 18px 16px;background:radial-gradient(120% 90% at 50% -10%, #f1e9ff 0%, var(--bg) 60%);border-bottom:1px solid var(--border)}
.hero .mark{font-family:'Cormorant Garamond',serif;font-size:13px;letter-spacing:5px;text-transform:uppercase;color:var(--accent);font-weight:600}
.hero h1{font-family:'Cormorant Garamond',serif;font-size:40px;font-weight:600;line-height:1.05;letter-spacing:.5px;margin:2px 0 6px;background:linear-gradient(90deg,var(--accent-d),var(--accent-l));-webkit-background-clip:text;background-clip:text;color:transparent}
.hero p{color:var(--muted);font-size:14px;font-weight:300}
.hero .count{display:inline-block;margin-top:9px;font-size:12px;color:var(--accent);background:var(--accent-soft);border:1px solid var(--border2);padding:3px 14px;border-radius:30px}

/* category nav (primary) */
.catnav{display:flex;gap:8px;justify-content:center;flex-wrap:wrap;padding:14px 16px 6px;max-width:760px;margin:0 auto}
.cat{font-family:var(--font);font-size:14px;font-weight:600;cursor:pointer;padding:9px 20px;border-radius:30px;border:1px solid var(--border2);background:var(--surface);color:var(--text);transition:.18s}
.cat:hover{border-color:var(--accent-l);color:var(--accent-d)}
.cat.active{background:linear-gradient(90deg,var(--accent-d),var(--accent));color:#fff;border-color:transparent;box-shadow:0 4px 14px rgba(124,58,237,.32)}

/* search + autocomplete */
.search-wrap{position:sticky;top:0;z-index:60;background:rgba(250,248,255,.92);backdrop-filter:blur(12px);padding:10px 16px 8px;border-bottom:1px solid var(--border)}
.search{position:relative;max-width:640px;margin:0 auto}
.search input{width:100%;font-size:16px;font-family:var(--font);padding:12px 46px;border:1px solid var(--border2);border-radius:30px;background:var(--surface);color:var(--text);outline:none;transition:.2s;box-shadow:var(--shadow)}
.search input:focus{border-color:var(--accent-l);box-shadow:0 0 0 4px var(--accent-soft)}
.search input::-webkit-search-cancel-button,.search input::-webkit-search-decoration{-webkit-appearance:none;appearance:none;display:none}
.search .ico{position:absolute;right:16px;top:50%;transform:translateY(-50%);color:var(--accent-l);font-size:18px;pointer-events:none}
.search .clr{position:absolute;left:9px;top:50%;transform:translateY(-50%);width:30px;height:30px;border:none;border-radius:50%;background:var(--accent-soft);color:var(--accent-d);font-size:15px;line-height:1;cursor:pointer;display:none;align-items:center;justify-content:center;padding:0}
.search .clr.show{display:flex}
.search .clr:hover{background:var(--accent-l);color:#fff}
.ac{position:absolute;top:calc(100% + 6px);right:0;left:0;background:var(--surface);border:1px solid var(--border2);border-radius:14px;box-shadow:var(--shadow-h);overflow:hidden;z-index:70;display:none}
.ac.show{display:block}
.ac-item{display:flex;align-items:center;gap:10px;padding:9px 14px;cursor:pointer;font-size:14px}
.ac-item:hover,.ac-item.hl{background:var(--accent-soft)}
.ac-item .b{font-size:11px;color:var(--accent-l);font-weight:700;text-transform:uppercase}
.ac-item img{width:30px;height:30px;object-fit:contain;border-radius:6px;background:#f4eefe}

/* secondary brand + filters */
.brandnav{display:flex;gap:7px;overflow-x:auto;padding:8px 16px;max-width:960px;margin:0 auto;scrollbar-width:none}
.pill{flex:0 0 auto;font-family:var(--font);font-size:12.5px;font-weight:500;cursor:pointer;padding:6px 14px;border-radius:30px;border:1px solid var(--border2);background:var(--surface);color:var(--text);white-space:nowrap;transition:.18s}
.pill:hover{border-color:var(--accent-l);color:var(--accent-d)}
.pill.active{background:var(--accent);color:#fff;border-color:transparent}
.toolbar{display:flex;gap:8px;flex-wrap:wrap;align-items:center;justify-content:center;padding:2px 16px 8px;max-width:960px;margin:0 auto}
.chip{font-size:12px;font-weight:500;cursor:pointer;padding:6px 12px;border-radius:20px;border:1px solid var(--border2);background:var(--surface);color:var(--muted);transition:.15s}
.chip:hover{color:var(--accent-d)}
.chip.active{background:var(--accent-soft);color:var(--accent-d);border-color:var(--accent-l)}
.chip.favbtn.active{background:#fff0f6;color:#d6336c;border-color:#f0a6c5}
.spacer{flex:1 1 auto;min-width:8px}
select.sort{font-family:var(--font);font-size:12px;color:var(--text);background:var(--surface);border:1px solid var(--border2);border-radius:20px;padding:6px 12px;cursor:pointer;outline:none}

/* grid */
.rescount{max-width:1160px;margin:8px auto 0;padding:0 20px;font-size:12.5px;color:var(--muted);font-weight:500;text-align:right}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(190px,1fr));gap:18px;max-width:1160px;margin:8px auto 40px;padding:0 18px}
.card{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);overflow:hidden;display:flex;flex-direction:column;cursor:pointer;transition:.22s;position:relative}
.card:hover{transform:translateY(-4px);box-shadow:var(--shadow-h);border-color:var(--border2)}
.card .imgbox{position:relative;aspect-ratio:1/1;background:linear-gradient(160deg,#fbf9ff,#f4eefe);display:flex;align-items:center;justify-content:center;padding:14px}
.card .imgbox img{max-width:100%;max-height:100%;object-fit:contain;mix-blend-mode:multiply}
.ph{font-family:'Cormorant Garamond',serif;font-size:46px;color:var(--accent-l);opacity:.5}
.fav{position:absolute;top:9px;left:9px;z-index:3;width:34px;height:34px;border-radius:50%;border:none;background:rgba(255,255,255,.86);backdrop-filter:blur(4px);cursor:pointer;font-size:16px;line-height:1;display:flex;align-items:center;justify-content:center;color:#c9b8e8;transition:.15s;box-shadow:0 2px 8px rgba(0,0,0,.06)}
.fav:hover{transform:scale(1.12)}.fav.on{color:#e64980}
.bdgs{position:absolute;top:9px;right:9px;z-index:3;display:flex;flex-direction:column;gap:4px;align-items:flex-end}
.bdg{font-size:10px;font-weight:700;color:#fff;padding:2px 8px;border-radius:20px;letter-spacing:.3px;box-shadow:0 2px 6px rgba(0,0,0,.12)}
.bdg.sale{background:#e0245e}.bdg.new{background:var(--lux)}.bdg.bestseller{background:var(--accent)}
.bdg.soldout{background:#6b7280}.bdg.limited{background:#0ea5a3}.bdg.vegan{background:#16a34a}
.card .body{padding:11px 13px 13px;display:flex;flex-direction:column;gap:5px;flex:1}
.card .brand{font-size:10.5px;font-weight:700;letter-spacing:.6px;text-transform:uppercase;color:var(--accent-l)}
.card .nm{font-size:13.5px;font-weight:500;line-height:1.32;color:var(--text);display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;min-height:36px}
.card .meta{display:flex;gap:5px;flex-wrap:wrap}
.tag{font-size:10.5px;font-weight:600;color:var(--accent-d);background:var(--accent-soft);border:1px solid var(--border2);border-radius:6px;padding:1px 7px}
.shrow{display:flex;gap:6px;overflow-x:auto;padding:3px 1px;scrollbar-width:none;align-items:center}
.shrow::-webkit-scrollbar{display:none}
.sw{flex:0 0 auto;width:19px;height:19px;border-radius:50%;border:1.5px solid var(--border2);cursor:pointer;padding:0;transition:.12s;position:relative}
.sw.txt{width:auto;height:auto;border-radius:20px;font-size:10.5px;font-weight:600;padding:2px 8px;background:var(--surface);color:var(--muted);max-width:78px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.sw.on{border-color:var(--accent);box-shadow:0 0 0 2px var(--accent-soft);transform:scale(1.06)}
.sw.txt.on{background:var(--accent-soft);color:var(--accent-d)}
.nsh{font-size:10.5px;color:var(--accent-l);font-weight:600;align-self:flex-start}
.card .foot{display:flex;align-items:center;justify-content:space-between;margin-top:auto;padding-top:8px}
.price{font-size:17px;font-weight:700;color:var(--text)}
.price .was{font-size:12px;font-weight:500;color:var(--muted);text-decoration:line-through;margin-inline-start:5px}
.price.sale{color:#e0245e}
.add{width:34px;height:34px;border-radius:11px;border:none;cursor:pointer;font-size:20px;line-height:1;color:#fff;background:linear-gradient(135deg,var(--accent),var(--accent-d));box-shadow:0 4px 12px rgba(124,58,237,.3);transition:.15s;touch-action:manipulation}
.add:hover{transform:translateY(-1px) scale(1.05)}
.cardqty{display:flex;align-items:center;border:1px solid var(--accent-l);border-radius:11px;overflow:hidden;background:var(--surface);box-shadow:0 2px 8px rgba(124,58,237,.12)}
.cardqty button{width:30px;height:34px;border:none;background:var(--accent-soft);color:var(--accent-d);font-size:18px;line-height:1;cursor:pointer;touch-action:manipulation;transition:.12s}
.cardqty button:hover{background:var(--accent);color:#fff}
.cardqty span{min-width:28px;text-align:center;font-size:14px;font-weight:700;color:var(--text)}
.empty{text-align:center;color:var(--muted);padding:70px 20px;font-size:15px}

/* cart bar + back to top */
.cartbar{position:fixed;left:0;right:0;bottom:0;z-index:80;background:rgba(255,255,255,.96);backdrop-filter:blur(14px);border-top:1px solid var(--border2);padding:11px 18px;display:flex;align-items:center;gap:14px;justify-content:center;box-shadow:0 -8px 30px rgba(91,33,182,.1);transform:translateY(120%);transition:.32s cubic-bezier(.2,.8,.2,1)}
.cartbar.show{transform:translateY(0)}
.cartbar .sum{font-weight:500;font-size:14px}.cartbar .sum b{color:var(--accent-d)}
.cartbar button{font-family:var(--font);font-size:14px;font-weight:600;color:#fff;cursor:pointer;border:none;border-radius:30px;padding:11px 26px;background:linear-gradient(90deg,var(--accent-d),var(--accent));box-shadow:0 6px 18px rgba(124,58,237,.34)}
.totop{position:fixed;left:16px;bottom:84px;z-index:70;width:46px;height:46px;border-radius:50%;border:1px solid var(--border2);background:rgba(255,255,255,.94);backdrop-filter:blur(10px);color:var(--accent-d);font-size:22px;cursor:pointer;display:flex;align-items:center;justify-content:center;box-shadow:0 8px 24px rgba(91,33,182,.18);opacity:0;transform:translateY(14px) scale(.9);pointer-events:none;transition:.25s cubic-bezier(.2,.8,.2,1)}
.totop.show{opacity:1;transform:translateY(0) scale(1);pointer-events:auto}
.totop:hover{background:linear-gradient(135deg,var(--accent),var(--accent-d));color:#fff;border-color:transparent}

/* modals */
.ov{position:fixed;inset:0;z-index:200;background:rgba(30,22,51,.42);backdrop-filter:blur(3px);display:none;align-items:flex-end;justify-content:center}
.ov.open{display:flex}
.sheet{background:var(--surface);width:100%;max-width:560px;max-height:92vh;overflow-y:auto;border-radius:22px 22px 0 0;box-shadow:0 -20px 60px rgba(0,0,0,.22);animation:up .3s cubic-bezier(.2,.8,.2,1)}
@media(min-width:600px){.ov{align-items:center}.sheet{border-radius:22px}}
@keyframes up{from{transform:translateY(40px);opacity:.4}to{transform:translateY(0);opacity:1}}
.sheet .x{position:sticky;top:0;float:left;margin:12px 12px 0 0;width:46px;height:46px;border-radius:50%;border:none;background:var(--accent-soft);color:var(--accent-d);font-size:24px;line-height:1;cursor:pointer;z-index:5;display:flex;align-items:center;justify-content:center;box-shadow:var(--shadow)}
.sheet .x:hover{background:var(--accent-l);color:#fff}
.pd-gal{display:flex;gap:8px;overflow-x:auto;padding:16px 18px 4px;scroll-snap-type:x mandatory}
.pd-gal img{height:220px;width:auto;border-radius:14px;background:#f4eefe;object-fit:contain;scroll-snap-align:center;border:1px solid var(--border);padding:8px;flex:0 0 auto;max-width:88%}
.pd-gal .ph{height:220px;width:220px;display:flex;align-items:center;justify-content:center;background:#f4eefe;border-radius:14px}
.pd{padding:6px 22px 26px}
.pd .b{font-size:11px;font-weight:700;letter-spacing:.8px;text-transform:uppercase;color:var(--accent-l)}
.pd h2{font-size:21px;font-weight:700;line-height:1.25;margin:3px 0 2px}
.pd .en{font-size:13px;color:var(--muted);font-weight:300;margin-bottom:8px}
.pd .row{display:flex;gap:8px;flex-wrap:wrap;margin:10px 0}
.pd .row .tag{font-size:12px;padding:3px 11px}
.pd .pr{font-size:26px;font-weight:700;color:var(--accent-d);margin:8px 0 12px}
.pd .pr .was{font-size:15px;color:var(--muted);text-decoration:line-through;margin-inline-start:8px;font-weight:500}
.pd-shades{margin:6px 0 4px}
.pd-shades .lbl{font-size:12px;font-weight:600;color:var(--muted);margin-bottom:6px}
.pd-sw{display:flex;gap:7px;flex-wrap:wrap}
.pd-sw button{font-family:var(--font);font-size:12px;font-weight:600;padding:6px 12px;border-radius:20px;border:1px solid var(--border2);background:var(--surface);color:var(--text);cursor:pointer;transition:.12s}
.pd-sw button.on{background:var(--accent);color:#fff;border-color:transparent}
.pd-sw .dot{display:inline-block;width:13px;height:13px;border-radius:50%;border:1px solid rgba(0,0,0,.12);margin-inline-end:6px;vertical-align:middle}
.pd h4{font-size:13px;font-weight:700;color:var(--accent-d);margin:16px 0 5px;padding-bottom:5px;border-bottom:1px solid var(--border)}
.pd p,.pd li{font-size:13.5px;line-height:1.6;color:#473d5e;font-weight:300}
.pd ul{padding-right:18px;margin-top:4px}
.pd .barc{font-size:12px;color:var(--muted);margin-top:14px;font-family:monospace;direction:ltr;text-align:right}
.pd .cta{width:100%;margin-top:18px;font-family:var(--font);font-size:16px;font-weight:600;color:#fff;border:none;border-radius:14px;padding:14px;cursor:pointer;background:linear-gradient(90deg,var(--accent-d),var(--accent));box-shadow:0 8px 22px rgba(124,58,237,.3)}
.pdfav{display:inline-flex;align-items:center;gap:7px;font-family:var(--font);font-size:13.5px;font-weight:600;cursor:pointer;border:1px solid var(--border2);background:var(--surface);color:var(--accent-d);border-radius:30px;padding:8px 16px;margin:2px 0 6px;transition:.15s}
.pdfav:hover{border-color:var(--accent-l)}.pdfav .h{color:#c9b8e8;font-size:15px}.pdfav.on{background:#fff0f6;border-color:#f0a6c5;color:#d6336c}.pdfav.on .h{color:#e64980}
.sim{margin-top:22px}
.sim h4{font-size:13px;font-weight:700;color:var(--accent-d);margin-bottom:9px;padding-bottom:5px;border-bottom:1px solid var(--border)}
.sim-row{display:flex;gap:10px;overflow-x:auto;scrollbar-width:none;padding-bottom:4px}
.sim-row::-webkit-scrollbar{display:none}
.sim-card{flex:0 0 96px;cursor:pointer}
.sim-card .si{width:96px;height:96px;border-radius:12px;background:#f4eefe;border:1px solid var(--border);display:flex;align-items:center;justify-content:center;padding:7px}
.sim-card img{max-width:100%;max-height:100%;object-fit:contain;mix-blend-mode:multiply}
.sim-card .sn{font-size:10.5px;line-height:1.25;color:var(--text);margin-top:4px;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.sim-card .sp{font-size:11.5px;font-weight:700;color:var(--accent-d)}

/* order modal */
.om{padding:8px 20px 24px}
.om h3{font-size:20px;font-weight:700;margin:6px 0 14px;text-align:center}
.om-row{display:flex;align-items:center;gap:10px;padding:11px 0;border-bottom:1px solid var(--border)}
.om-row .nm{flex:1;font-size:13.5px;font-weight:500}
.om-row .nm small{display:block;color:var(--muted);font-weight:300;font-size:11.5px}
.qy{display:flex;align-items:center;border:1px solid var(--border2);border-radius:10px;overflow:hidden}
.qy button{width:30px;height:30px;border:none;background:var(--accent-soft);color:var(--accent-d);font-size:17px;cursor:pointer;touch-action:manipulation}
.qy span{min-width:28px;text-align:center;font-size:14px;font-weight:600}
.om-row .lt{min-width:62px;text-align:left;font-weight:700;font-size:14px;direction:ltr}
.om-del{border:none;background:none;color:#c9b8e8;font-size:16px;cursor:pointer}
.coupon{display:flex;gap:8px;margin:16px 0 6px}
.coupon input{flex:1;font-family:var(--font);font-size:16px;padding:11px 14px;border:1px solid var(--border2);border-radius:12px;outline:none;background:var(--surface)}
.coupon button{font-family:var(--font);font-weight:600;font-size:14px;border:1px solid var(--accent-l);background:var(--accent-soft);color:var(--accent-d);border-radius:12px;padding:0 18px;cursor:pointer}
.cmsg{font-size:12.5px;font-weight:500;min-height:18px;margin-bottom:6px}
.cmsg.ok{color:#15803d}.cmsg.err{color:#dc2626}
.totals{margin-top:10px;font-size:14px}
.totals .l{display:flex;justify-content:space-between;padding:4px 0;color:var(--muted)}
.totals .l.grand{font-size:19px;font-weight:700;color:var(--text);border-top:1px solid var(--border);margin-top:6px;padding-top:10px}
.totals .l.grand b{color:var(--accent-d)}
.form{margin-top:16px;display:flex;flex-direction:column;gap:9px}
.form h4{font-size:13px;font-weight:700;color:var(--accent-d);margin-bottom:1px;padding-bottom:6px;border-bottom:1px solid var(--border)}
.fld,.notes{width:100%;font-family:var(--font);font-size:16px;padding:11px 13px;border-radius:11px;border:1px solid var(--border2);outline:none;background:var(--surface);color:var(--text)}
.notes{resize:vertical;min-height:58px}
.fld:focus,.notes:focus{border-color:var(--accent-l);box-shadow:0 0 0 3px var(--accent-soft)}
.send{width:100%;margin-top:14px;font-family:var(--font);font-size:16px;font-weight:700;color:#fff;border:none;border-radius:14px;padding:15px;cursor:pointer;background:linear-gradient(90deg,#16a34a,#15803d);box-shadow:0 8px 22px rgba(22,163,74,.28)}
.send.pay{background:linear-gradient(90deg,var(--accent-d),var(--accent));box-shadow:0 8px 22px rgba(124,58,237,.3)}
.send:disabled{opacity:.6;cursor:progress}
.soldpill{font-size:12px;font-weight:700;color:#b91c1c;background:#fee2e2;border-radius:9px;padding:6px 10px;white-space:nowrap}
.hint{font-size:11.5px;color:var(--muted);text-align:center;margin-top:8px}

@media(max-width:480px){
  .hero{padding:24px 14px 14px}.hero h1{font-size:28px;letter-spacing:0}.hero p{font-size:12.5px}
  .cat{font-size:13px;padding:8px 16px}
  .grid{grid-template-columns:repeat(2,1fr);gap:11px;padding:0 12px;margin-top:10px}
  .card .nm{font-size:12.5px;min-height:33px}.price{font-size:15.5px}
}
</style>
</head>
<body>
<div class="brandbar">
  <img src="logo.svg" alt="Sephora Favorites" width="150" height="63" onclick="goTop()" style="cursor:pointer">
  <button class="langbtn" id="langBtn" onclick="toggleLang()" aria-label="Language">العربية</button>
</div>
<header class="herobanner">
  <picture>
    <source media="(max-width:640px)" srcset="hero-mobile.jpg">
    <img src="hero-desktop.jpg" alt="Sephora Favorites — הקולקציה הנבחרת: איפור, טיפוח, שיער ובושם" fetchpriority="high" width="1672" height="941">
  </picture>
</header>

<nav class="catnav" id="catnav"></nav>

<div class="search-wrap">
  <div class="search">
    <span class="ico">⌕</span>
    <input id="q" type="search" autocomplete="off" placeholder="חיפוש מוצר, מותג או ברקוד…" oninput="onSearch()" onkeydown="acKey(event)">
    <button class="clr" id="clrBtn" type="button" onclick="clearSearch()" aria-label="נקה חיפוש" title="נקה">✕</button>
    <div class="ac" id="ac"></div>
  </div>
</div>

<nav class="brandnav" id="brandnav"></nav>
<div class="toolbar" id="prices"></div>
<div class="toolbar">
  <button class="chip favbtn" id="favchip" onclick="toggleFavOnly()">♥ המועדפים שלי</button>
  <span class="spacer"></span>
  <select class="sort" id="sort" onchange="render()">
    <option value="default">מיון: מומלץ</option>
    <option value="price-asc">מחיר: מהנמוך לגבוה</option>
    <option value="price-desc">מחיר: מהגבוה לנמוך</option>
    <option value="name">שם: א׳–ת׳</option>
  </select>
</div>

<div class="rescount" id="rescount"></div>
<main class="grid" id="grid"></main>

<div class="cartbar" id="cartbar">
  <span class="sum" id="cartsum"></span>
  <button id="viewOrderBtn" onclick="openOrder()">צפה בהזמנה ←</button>
</div>
<button class="totop" id="toTop" onclick="goTop()" aria-label="חזרה למעלה" title="חזרה למעלה">↑</button>

<div class="ov" id="pdModal"><div class="sheet"><button class="x" onclick="closePd()">✕</button><div id="pdContent"></div></div></div>

<div class="ov" id="orderModal"><div class="sheet">
  <button class="x" onclick="closeOrder()">✕</button>
  <div class="om">
    <h3 id="omTitle">ההזמנה שלי</h3>
    <div id="omBody"></div>
    <div class="coupon"><input id="coupon" type="text" placeholder="קוד קופון" oninput="applyCoupon()"><button id="couponBtn" onclick="applyCoupon()">החל</button></div>
    <div class="cmsg" id="cmsg"></div>
    <div class="totals" id="totals"></div>
    <div class="form">
      <h4 id="buyerTitle">פרטי המזמין</h4>
      <input class="fld" id="buyer-name" type="text" placeholder="שם מלא *">
      <input class="fld" id="buyer-biz" type="text" placeholder="שם העסק / החנות (לחשבונית)">
      <input class="fld" id="buyer-id" type="text" placeholder="מספר עוסק מורשה / ח.פ / ת.ז">
      <input class="fld" id="buyer-addr" type="text" placeholder="עיר וכתובת למשלוח">
      <input class="fld" id="buyer-phone" type="tel" placeholder="טלפון *">
      <textarea class="notes" id="notes" placeholder="הערות להזמנה (אופציונלי)…"></textarea>
    </div>
    <button class="send pay" id="payBtn" onclick="payNow()" style="display:none">שלם עכשיו 💳</button>
    <button class="send" id="sendBtn" onclick="submitWhatsApp()">שלח הזמנה לאישור (וואטסאפ)</button>
    <div class="hint" id="sendHint">ההזמנה תיפתח ב-WhatsApp עם מספר ההזמנה</div>
  </div>
</div></div>

<script>
const GROUPS = /*__GROUPS__*/;
GROUPS.forEach((g,i)=>{g._i=i; g.minp=Math.min(...g.variants.map(eff)); g._noimg=g.variants.every(v=>!v.imgs||!v.imgs.length);});

/* ===== i18n: UI language toggle (HE / AR). The WhatsApp order text stays Hebrew always. ===== */
const I18N={
 he:{search_ph:'חיפוש מוצר, מותג או ברקוד…',fav_only:'המועדפים שלי',
  sort_default:'מיון: מומלץ',sort_pa:'מחיר: מהנמוך לגבוה',sort_pd:'מחיר: מהגבוה לנמוך',sort_name:'שם: א׳–ת׳',
  all:'הכל',all_brands:'כל המותגים',all_prices:'כל המחירים',
  p_u50:'עד ₪50',p_50_100:'₪50–100',p_100_200:'₪100–200',p_200p:'₪200+',
  items:'מוצרים',cart_items:'פריטים',empty:'לא נמצאו מוצרים מתאימים 🔍',
  view_order:'צפה בהזמנה ←',totop:'חזרה למעלה',
  c_איפור:'איפור',c_טיפוח:'טיפוח',c_שיער:'שיער',c_בושם:'בושם',c_ציפורניים:'ציפורניים',c_אביזרים:'אביזרים',c_ציוד:'ציוד',c_אחר:'אחר',
  b_sale:'מבצע',b_new:'חדש',b_bestseller:'רב-מכר',b_soldout:'אזל',b_limited:'מהדורה מוגבלת',b_vegan:'טבעוני',
  shades:'גוונים',feats:'מאפיינים עיקריים',ingredients:'רכיבים',usage:'אופן שימוש',
  pick_shade:'בחר גוון',similar:'מוצרים דומים',desc:'תיאור',barcode:'ברקוד:',
  add_order:'הוסף להזמנה',fav_remove:'במועדפים — הסר',fav_add:'הוסף למועדפים',
  my_order:'ההזמנה שלי',coupon_ph:'קוד קופון',apply:'החל',buyer_details:'פרטי המזמין',
  full_name:'שם מלא *',biz_name:'שם העסק / החנות (לחשבונית)',biz_id:'מספר עוסק מורשה / ח.פ / ת.ז',
  ship_addr:'עיר וכתובת למשלוח',phone:'טלפון *',notes_ph:'הערות להזמנה (אופציונלי)…',
  send_order:'שלח הזמנה לאישור (וואטסאפ)',send_hint:'ההזמנה תיפתח ב-WhatsApp עם מספר ההזמנה',
  pay_now:'שלם עכשיו 💳',sold_out:'אזל',sending:'שולח…',err_order:'אירעה תקלה ביצירת ההזמנה. נסה שוב.',
  cart_empty:'העגלה ריקה',subtotal:'סכום ביניים',discount:'הנחה',grand:'סה"כ לתשלום',
  coupon_ok:'✓ קופון הוחל: ',coupon_bad:'קוד קופון לא תקין',off:'הנחה',
  alert_empty:'העגלה ריקה',alert_fill:'נא למלא שם מלא וטלפון לפני שליחת ההזמנה',other:'العربية'},
 ar:{search_ph:'ابحث عن منتج، ماركة أو باركود…',fav_only:'المفضلة لديّ',
  sort_default:'الترتيب: موصى به',sort_pa:'السعر: من الأقل للأعلى',sort_pd:'السعر: من الأعلى للأقل',sort_name:'الاسم: أ–ي',
  all:'الكل',all_brands:'كل الماركات',all_prices:'كل الأسعار',
  p_u50:'حتى ₪50',p_50_100:'₪50–100',p_100_200:'₪100–200',p_200p:'₪200+',
  items:'منتج',cart_items:'عناصر',empty:'لم يتم العثور على منتجات مطابقة 🔍',
  view_order:'عرض الطلب ←',totop:'العودة للأعلى',
  c_איפור:'مكياج',c_טיפוח:'العناية بالبشرة',c_שיער:'العناية بالشعر',c_בושם:'عطر',c_ציפורניים:'العناية بالأظافر',c_אביזרים:'إكسسوارات',c_ציוד:'معدات',c_אחר:'أخرى',
  b_sale:'تخفيض',b_new:'جديد',b_bestseller:'الأكثر مبيعاً',b_soldout:'نفد',b_limited:'إصدار محدود',b_vegan:'نباتي',
  shades:'ألوان',feats:'أبرز المزايا',ingredients:'المكوّنات',usage:'طريقة الاستخدام',
  pick_shade:'اختر اللون',similar:'منتجات مشابهة',desc:'الوصف',barcode:'باركود:',
  add_order:'أضف إلى الطلب',fav_remove:'في المفضلة — إزالة',fav_add:'أضف إلى المفضلة',
  my_order:'طلبي',coupon_ph:'رمز الكوبون',apply:'تطبيق',buyer_details:'تفاصيل مقدّم الطلب',
  full_name:'الاسم الكامل *',biz_name:'اسم العمل / المتجر (للفاتورة)',biz_id:'رقم السجل التجاري / الهوية',
  ship_addr:'المدينة والعنوان للتوصيل',phone:'الهاتف *',notes_ph:'ملاحظات على الطلب (اختياري)…',
  send_order:'إرسال الطلب للموافقة (واتساب)',send_hint:'سيُفتح الطلب في WhatsApp مع رقم الطلب',
  pay_now:'ادفع الآن 💳',sold_out:'نفد',sending:'جارٍ الإرسال…',err_order:'حدث خطأ في إنشاء الطلب. حاول مرة أخرى.',
  cart_empty:'السلة فارغة',subtotal:'المجموع الفرعي',discount:'خصم',grand:'الإجمالي للدفع',
  coupon_ok:'✓ تم تطبيق الكوبون: ',coupon_bad:'رمز كوبون غير صالح',off:'خصم',
  alert_empty:'السلة فارغة',alert_fill:'يرجى تعبئة الاسم الكامل والهاتف قبل إرسال الطلب',other:'עברית'}
};
let LANG=localStorage.getItem('sf_lang')||'he';
function t(k){return (I18N[LANG]&&I18N[LANG][k]!=null)?I18N[LANG][k]:(I18N.he[k]!=null?I18N.he[k]:k);}
function catLabel(c){return t('c_'+c)||c;}
function setText(id,v){var e=document.getElementById(id);if(e)e.textContent=v;}
function setPh(id,v){var e=document.getElementById(id);if(e)e.placeholder=v;}
function applyStatic(){
  document.documentElement.lang=LANG;
  setPh('q',t('search_ph'));
  var fc=document.getElementById('favchip');if(fc)fc.innerHTML='♥ '+t('fav_only');
  var so=document.getElementById('sort');if(so){so.options[0].text=t('sort_default');so.options[1].text=t('sort_pa');so.options[2].text=t('sort_pd');so.options[3].text=t('sort_name');}
  setText('viewOrderBtn',t('view_order'));
  var tt=document.getElementById('toTop');if(tt){tt.title=t('totop');tt.setAttribute('aria-label',t('totop'));}
  setText('omTitle',t('my_order'));setPh('coupon',t('coupon_ph'));setText('couponBtn',t('apply'));
  setText('buyerTitle',t('buyer_details'));
  setPh('buyer-name',t('full_name'));setPh('buyer-biz',t('biz_name'));setPh('buyer-id',t('biz_id'));
  setPh('buyer-addr',t('ship_addr'));setPh('buyer-phone',t('phone'));setPh('notes',t('notes_ph'));
  setText('sendBtn',t('send_order'));setText('sendHint',t('send_hint'));setText('payBtn',t('pay_now'));
  var lb=document.getElementById('langBtn');if(lb)lb.textContent=t('other');
}
function toggleLang(){LANG=(LANG==='he')?'ar':'he';localStorage.setItem('sf_lang',LANG);applyLang();}
function applyLang(){applyStatic();buildNav();render();renderCart();
  if(document.getElementById('orderModal').classList.contains('open'))renderOrder();}

// brand prestige tiers (1 = luxury/prestige … 4 = generic) for the default "מומלץ" sort
const PRESTIGE={
 "דיור":1,"שאנל":1,"ייב סן לורן":1,"YSL":1,"ארמני":1,"ז'יבנשי":1,"גוצ'י":1,"ולנטינו":1,"Bond No. 9":1,
 "אסתי לאודר":1,"לנקום":1,"קלרינס":1,"קליניק":1,"לורה מרסייה":1,"בובי בראון":1,"האורגלאס":1,"נארס":1,
 "שרלוט טילבורי":1,"נטשה דנונה":1,"פט מקגראת'":1,"טאצ'ה":1,"דראנק אלפנט":1,"קילס":1,"לה רוש פוזה":1,
 "קודלי":1,"וישי":1,"לנייג'":1,"איט קוסמטיקס":1,"מייק אפ פור אבר":1,"פיטר תומאס רות'":1,"דרמלוגיקה":1,
 "פנטי ביוטי":2,"ריר ביוטי":2,"אנסטסיה בברלי הילס":2,"הודה ביוטי":2,"בנפיט":2,"טו פייסד":2,"טארט":2,
 "קוסאס":2,"מייקאפ ביי מריו":2,"דנסה מיריקס":2,"Rhode":2,"סאמר פריידייז":2,"Glow Recipe":2,"ONE/SIZE":2,
 "מילק מייקאפ":2,"פטריק טא":2,"סמאשבוקס":2,"אורבן דקיי":2,"MAC":2,"אולפלקס":2,"K18":2,"Gisou":2,"סול דה ז'נרו":2,"מורפי":2,
 "מייבלין":3,"לוריאל":3,"NYX":3,"מילאני":3,"קאברגירל":3,"אי.אל.אף":3,"פיקסי":3,"קולורפופ":3,"קיילי קוסמטיקס":3,"ריאל טכניקס":3,"שוורצקופף":3,"רבלון":3,"גרנייה":3,
};
function prestige(b){return PRESTIGE[b]||4;}
const VMAP={}; GROUPS.forEach(g=>g.variants.forEach(v=>{VMAP[v.id]={g,v};}));
function eff(v){return (v.sale&&v.sale>0)?v.sale:v.price}

const BADGE_LABEL={sale:'מבצע',new:'חדש',bestseller:'רב-מכר',soldout:'אזל',limited:'מהדורה מוגבלת',vegan:'טבעוני'};
const BADGE_ORDER=['sale','bestseller','new','limited','soldout','vegan'];

const CATS=['איפור','טיפוח','שיער','בושם','ציפורניים','אביזרים','ציוד'].filter(t=>GROUPS.some(g=>g.type===t));
const BRANDS=(()=>{const c={};GROUPS.forEach(g=>c[g.brand]=(c[g.brand]||0)+1);
  return Object.keys(c).sort((a,b)=>a==='אחר'?1:b==='אחר'?-1:c[b]-c[a]);})();
const PRICES=[{l:'עד ₪50',mn:0,mx:50},{l:'₪50–100',mn:50,mx:100},{l:'₪100–200',mn:100,mx:200},{l:'₪200+',mn:200,mx:1e9}];

let curCat='__all__',curBrand='__all__',curPrice=-1,favOnly=false;
const sel={};   // gid -> variant index
const FAVS=new Set(JSON.parse(localStorage.getItem('sf_favs')||'[]'));
function saveFavs(){localStorage.setItem('sf_favs',JSON.stringify([...FAVS]))}
function esc(s){return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')}
function aesc(s){return String(s).replace(/"/g,'&quot;')}
function imgErr(img){img.style.display='none';const ph=document.createElement('div');ph.className='ph';ph.textContent=img.dataset.l||'✦';img.parentNode.appendChild(ph)}
function selV(g){return g.variants[sel[g.gid]||0]}
function swPill(v,on,oc){
  if(v.color)return `<button class="sw ${on?'on':''}" style="background:${v.color}" title="${aesc(v.shade)}" onclick="event.stopPropagation();${oc}"></button>`;
  return `<button class="sw txt ${on?'on':''}" onclick="event.stopPropagation();${oc}">${esc(v.shade)}</button>`;
}

// ===== nav (rebuildable for language switch) =====
const PRICE_KEYS=['p_u50','p_50_100','p_100_200','p_200p'];
function buildNav(){
  const cn=document.getElementById('catnav');
  const mk=(l,v)=>`<button class="cat ${v===curCat?'active':''}" data-c="${v}">${l}</button>`;
  cn.innerHTML=mk(t('all'),'__all__')+CATS.map(c=>mk(catLabel(c),c)).join('');
  cn.onclick=e=>{const b=e.target.closest('[data-c]');if(!b)return;curCat=b.dataset.c;
    [...cn.children].forEach(c=>c.classList.toggle('active',c.dataset.c===curCat));render()};

  const bn=document.getElementById('brandnav');
  const mb=(l,v)=>`<button class="pill ${v===curBrand?'active':''}" data-b="${v}">${l}</button>`;
  bn.innerHTML=mb(t('all_brands'),'__all__')+BRANDS.map(b=>mb(b,b)).join('');
  bn.onclick=e=>{const b=e.target.closest('[data-b]');if(!b)return;curBrand=b.dataset.b;
    [...bn.children].forEach(c=>c.classList.toggle('active',c.dataset.b===curBrand));render()};

  const pr=document.getElementById('prices');
  const mp=(l,i)=>`<button class="chip ${i===curPrice?'active':''}" data-p="${i}">${l}</button>`;
  pr.innerHTML=mp(t('all_prices'),-1)+PRICES.map((p,i)=>mp(t(PRICE_KEYS[i]),i)).join('');
  pr.onclick=e=>{const b=e.target.closest('[data-p]');if(!b)return;curPrice=+b.dataset.p;
    [...pr.children].forEach(c=>c.classList.toggle('active',+c.dataset.p===curPrice));render()};
}
buildNav();
function toggleFavOnly(){favOnly=!favOnly;document.getElementById('favchip').classList.toggle('active',favOnly);render()}

// ===== filtering =====
// build a multilingual search blob per group (HE + EN names/brand + AR category + AR descriptions/features + shades/barcodes)
function catBoth(type){return (I18N.ar['c_'+type]||'')+' '+(I18N.he['c_'+type]||'');}
function buildHay(g){
  let s=g.name_he+' '+g.name_en+' '+g.brand+' '+catBoth(g.type);
  g.variants.forEach(v=>{s+=' '+(v.shade||'')+' '+(v.barcode||'')+' '+(v.desc_ar||'')+' '+((v.features_ar||[]).join(' '));});
  return s.toLowerCase();
}
function matchQ(g,q){
  if(!q)return true;
  const hay=g._hay||(g._hay=buildHay(g));
  return hay.includes(q);
}
function visible(){
  const q=document.getElementById('q').value.trim().toLowerCase();
  let r=GROUPS.filter(g=>{
    if(curCat!=='__all__'&&g.type!==curCat)return false;
    if(curBrand!=='__all__'&&g.brand!==curBrand)return false;
    if(curPrice>=0){const pr=PRICES[curPrice];if(!(g.minp>=pr.mn&&g.minp<pr.mx))return false}
    if(favOnly&&!FAVS.has(g.gid))return false;
    if(STOCK_READY&&!g.variants.some(inDB))return false;   // הסתרת מוצרים שאינם ב-DB (לא ניתנים להזמנה)
    return matchQ(g,q);
  });
  const s=document.getElementById('sort').value;
  // cards without an image always sink to the bottom (regardless of sort)
  const byImg=(a,b)=> (a._noimg?1:0)-(b._noimg?1:0);
  if(s==='price-asc')r.sort((a,b)=>byImg(a,b)||a.minp-b.minp);
  else if(s==='price-desc')r.sort((a,b)=>byImg(a,b)||b.minp-a.minp);
  else if(s==='name')r.sort((a,b)=>byImg(a,b)||a.name_he.localeCompare(b.name_he,'he'));
  else r.sort((a,b)=> byImg(a,b)              // default "מומלץ": prestige brands first
      || prestige(a.brand)-prestige(b.brand)
      || a.brand.localeCompare(b.brand,'he')
      || a.minp-b.minp);
  return r;
}

// ===== badges & price html =====
function badgesHtml(v){
  const bs=(v.badges||[]).slice().sort((a,b)=>BADGE_ORDER.indexOf(a)-BADGE_ORDER.indexOf(b)).slice(0,2);
  if(!bs.length)return '';
  return `<div class="bdgs">${bs.map(b=>`<span class="bdg ${b}">${t('b_'+b)||b}</span>`).join('')}</div>`;
}
function priceHtml(v,cls){
  if(v.sale&&v.sale>0)return `<div class="price sale ${cls||''}">₪${v.sale}<span class="was">₪${v.price}</span></div>`;
  return `<div class="price ${cls||''}">₪${v.price}</div>`;
}

// ===== grid =====
function cardHtml(g){
  const v=selV(g);
  const qty=CART[v.id]?CART[v.id].qty:0;
  const fav=FAVS.has(g.gid)?'on':'';
  const img=v.imgs.length?`<img src="${aesc(v.imgs[0])}" loading="lazy" data-l="${aesc(g.name_he[0]||'✦')}" onerror="imgErr(this)">`:`<div class="ph">${esc(g.name_he[0]||'✦')}</div>`;
  let shades='';
  if(g.variants.length>1){
    const idx=sel[g.gid]||0;
    shades=`<div class="shrow" onclick="event.stopPropagation()">${g.variants.map((vv,k)=>swPill(vv,k===idx,`pickV('${g.gid}',${k})`)).join('')}</div>`;
  }
  return `<div class="card" id="card-${g.gid}" onclick="openPd(${g._i})">
      <div class="imgbox">
        <button class="fav ${fav}" onclick="event.stopPropagation();toggleFav('${g.gid}',this)">♥</button>
        ${badgesHtml(v)}${img}
      </div>
      <div class="body">
        <div class="brand">${esc(g.brand)}</div>
        <div class="nm">${esc(g.name_he)}</div>
        ${g.variants.length>1?`<span class="nsh">${g.variants.length} ${t('shades')}</span>`:(v.size?`<div class="meta"><span class="tag">${esc(v.size)}</span></div>`:'')}
        ${shades}
        <div class="foot">
          ${priceHtml(v)}
          ${isSold(v)?`<span class="soldpill">${t('sold_out')}</span>`
            :qty>0?`<div class="cardqty" onclick="event.stopPropagation()"><button onclick="event.stopPropagation();cartChange('${v.id}',-1)">−</button><span>${qty}</span><button onclick="event.stopPropagation();cartChange('${v.id}',1)">+</button></div>`
                 :`<button class="add" onclick="event.stopPropagation();cartChange('${v.id}',1)">+</button>`}
        </div>
      </div>
    </div>`;
}
// ---- paginated render (incremental, for 1400+ cards) ----
let VIS=[], shown=0; const PAGE=60;
function render(){
  VIS=visible(); shown=0;
  const grid=document.getElementById('grid');
  const cnt=document.getElementById('rescount'); if(cnt)cnt.textContent=VIS.length.toLocaleString()+' '+t('items');
  grid.innerHTML='';
  if(!VIS.length){grid.innerHTML='<div class="empty">'+t('empty')+'</div>';return}
  loadMore();
}
function loadMore(){
  if(shown>=VIS.length)return;
  const slice=VIS.slice(shown,shown+PAGE);
  document.getElementById('grid').insertAdjacentHTML('beforeend', slice.map(cardHtml).join(''));
  shown+=slice.length;
}
function updateCard(gid){var el=document.getElementById('card-'+gid);if(!el)return;var g=GROUPS.find(x=>x.gid===gid);if(g)el.outerHTML=cardHtml(g);}
function pickV(gid,k){sel[gid]=k;updateCard(gid);}
function toggleFav(gid,btn){if(FAVS.has(gid))FAVS.delete(gid);else FAVS.add(gid);saveFavs();
  if(btn)btn.classList.toggle('on',FAVS.has(gid));if(favOnly)render()}

// ===== autocomplete =====
let acIdx=-1, acList=[];
function toggleClr(){var q=document.getElementById('q').value;var b=document.getElementById('clrBtn');if(b)b.classList.toggle('show',!!q);}
function clearSearch(){var q=document.getElementById('q');q.value='';document.getElementById('ac').classList.remove('show');toggleClr();render();q.focus();}
function onSearch(){buildAC();render();toggleClr();}
function buildAC(){
  const q=document.getElementById('q').value.trim().toLowerCase();
  const ac=document.getElementById('ac');
  if(q.length<2){ac.classList.remove('show');acList=[];return}
  acList=GROUPS.filter(g=>matchQ(g,q)).slice(0,6);
  acIdx=-1;
  if(!acList.length){ac.classList.remove('show');return}
  ac.innerHTML=acList.map((g,i)=>{const v=selV(g);
    const im=v.imgs.length?`<img src="${aesc(v.imgs[0])}" onerror="this.style.visibility='hidden'">`:`<span style="width:30px"></span>`;
    return `<div class="ac-item" data-i="${i}" onmousedown="acPick(${i})"><div class="b">${esc(g.brand)}</div>${im}<span>${esc(g.name_he)}</span></div>`;
  }).join('');
  ac.classList.add('show');
}
function acPick(i){const g=acList[i];if(!g)return;document.getElementById('ac').classList.remove('show');
  document.getElementById('q').blur();openPd(g._i);}
function acKey(e){
  const ac=document.getElementById('ac');if(!ac.classList.contains('show'))return;
  if(e.key==='ArrowDown'){acIdx=Math.min(acIdx+1,acList.length-1);e.preventDefault();}
  else if(e.key==='ArrowUp'){acIdx=Math.max(acIdx-1,0);e.preventDefault();}
  else if(e.key==='Enter'){ac.classList.remove('show');if(acIdx>=0)acPick(acIdx);else document.getElementById('q').blur();e.preventDefault();return;}
  else if(e.key==='Escape'){ac.classList.remove('show');return;}
  [...ac.children].forEach((c,k)=>c.classList.toggle('hl',k===acIdx));
}
document.addEventListener('click',e=>{if(!e.target.closest('.search'))document.getElementById('ac').classList.remove('show')});

// ===== product detail =====
function openPd(i){renderPd(GROUPS[i]);openOv('pdModal');}
function renderPd(g){
  const v=selV(g);
  const gal=v.imgs.length?v.imgs.map(s=>`<img src="${aesc(s)}" loading="lazy" data-l="${aesc(g.name_he[0]||'✦')}" onerror="imgErr(this)">`).join(''):`<div class="ph">${esc(g.name_he[0]||'✦')}</div>`;
  // Arabic copy when LANG=ar (fallback to Hebrew per field)
  const _dsc=(LANG==='ar'&&v.desc_ar)?v.desc_ar:v.desc;
  const _fts=(LANG==='ar'&&v.features_ar&&v.features_ar.length)?v.features_ar:v.features;
  const _usg=(LANG==='ar'&&v.usage_ar)?v.usage_ar:v.usage;
  const feats=(_fts&&_fts.length)?`<h4>${t('feats')}</h4><ul>${_fts.map(f=>`<li>${esc(f)}</li>`).join('')}</ul>`:'';
  const ing=v.ingredients?`<h4>${t('ingredients')}</h4><p>${esc(v.ingredients)}</p>`:'';
  const use=_usg?`<h4>${t('usage')}</h4><p>${esc(_usg)}</p>`:'';
  let shades='';
  if(g.variants.length>1){const idx=sel[g.gid]||0;
    shades=`<div class="pd-shades"><div class="lbl">${t('pick_shade')} (${g.variants.length}):</div><div class="pd-sw">${g.variants.map((vv,k)=>`<button class="${k===idx?'on':''}" onclick="pdPick('${g.gid}',${k})">${vv.color?`<i class="dot" style="background:${vv.color}"></i>`:''}${esc(vv.shade)}</button>`).join('')}</div></div>`;}
  const pr=v.sale&&v.sale>0?`<div class="pr">₪${v.sale}<span class="was">₪${v.price}</span></div>`:`<div class="pr">₪${v.price}</div>`;
  const bdg=(v.badges||[]).map(b=>`<span class="tag" style="color:#fff;background:${b==='sale'?'#e0245e':b==='vegan'?'#16a34a':'var(--accent)'};border:none">${t('b_'+b)||b}</span>`).join('');
  // similar: other groups, same brand first then same type
  const sim=GROUPS.filter(x=>x.gid!==g.gid&&(x.brand===g.brand||x.type===g.type))
    .sort((a,b)=>(a.brand===g.brand?0:1)-(b.brand===g.brand?0:1)).slice(0,8);
  const simHtml=sim.length?`<div class="sim"><h4>${t('similar')}</h4><div class="sim-row">${sim.map(x=>{const xv=selV(x);
    const im=xv.imgs.length?`<img src="${aesc(xv.imgs[0])}" onerror="this.style.visibility='hidden'">`:'<span class="ph" style="font-size:26px">✦</span>';
    return `<div class="sim-card" onclick="openPd(${x._i})"><div class="si">${im}</div><div class="sn">${esc(x.name_he)}</div><div class="sp">₪${eff(xv)}</div></div>`;}).join('')}</div></div>`:'';
  document.getElementById('pdContent').innerHTML=`
    <div class="pd-gal">${gal}</div>
    <div class="pd">
      <div class="b">${esc(g.brand)}</div>
      <h2>${esc(g.name_he)}</h2>
      ${g.name_en?`<div class="en">${esc(g.name_en)}</div>`:''}
      <div class="row">${bdg}${v.size?`<span class="tag">${esc(v.size)}</span>`:''}<span class="tag">${esc(catLabel(g.type))}</span></div>
      ${shades}
      ${pr}
      <button class="pdfav ${FAVS.has(g.gid)?'on':''}" id="pdFav" onclick="toggleFavFromModal('${g.gid}')"><span class="h">♥</span><span class="t">${FAVS.has(g.gid)?t('fav_remove'):t('fav_add')}</span></button>
      ${_dsc?`<h4>${t('desc')}</h4><p>${esc(_dsc)}</p>`:''}
      ${feats}${ing}${use}
      ${v.barcode?`<div class="barc">${t('barcode')} ${esc(v.barcode)}</div>`:''}
      ${isSold(v)?`<button class="cta" disabled style="opacity:.5;cursor:not-allowed">${t('sold_out')}</button>`
        :`<button class="cta" onclick="cartChange('${v.id}',1);closePd()">${t('add_order')}  ·  ₪${eff(v)}</button>`}
      ${simHtml}
    </div>`;
}
function pdPick(gid,k){sel[gid]=k;renderPd(GROUPS.find(g=>g.gid===gid));render();}
function closePd(){closeOv('pdModal')}
function toggleFavFromModal(gid){if(FAVS.has(gid))FAVS.delete(gid);else FAVS.add(gid);saveFavs();
  const on=FAVS.has(gid),b=document.getElementById('pdFav');
  if(b){b.classList.toggle('on',on);b.querySelector('.t').textContent=on?t('fav_remove'):t('fav_add')}render();}

// ===== cart (keyed by variant id) =====
const CART={};
function cartChange(vid,delta){
  const m=VMAP[vid];if(!m)return;
  if(delta>0){
    if(CART[vid])CART[vid].qty++;
    else CART[vid]={vid,name:m.g.name_he+(m.v.shade&&m.g.variants.length>1?' · '+m.v.shade:''),brand:m.g.brand,size:m.v.size,price:eff(m.v),qty:1};
  } else if(CART[vid]){CART[vid].qty--;if(CART[vid].qty<=0)delete CART[vid];}
  renderCart();updateCard(m.g.gid);
  if(document.getElementById('orderModal').classList.contains('open'))renderOrder();
}
function cartTotals(){let qty=0,sub=0;Object.values(CART).forEach(it=>{qty+=it.qty;sub+=it.qty*it.price});return{qty,sub};}
function renderCart(){const {qty,sub}=cartTotals();const bar=document.getElementById('cartbar');
  if(qty===0){bar.classList.remove('show');return}bar.classList.add('show');
  document.getElementById('cartsum').innerHTML=`${qty} ${t('cart_items')} · <b>₪${sub}</b>`;}

const COUPONS={'SEPHORA10':{type:'percent',val:10,label:'10% הנחה'},'FAV20':{type:'fixed',val:20,label:'₪20 הנחה'}};
let activeCoupon=null;
function applyCoupon(){const code=document.getElementById('coupon').value.trim().toUpperCase();const msg=document.getElementById('cmsg');
  if(!code){activeCoupon=null;msg.textContent='';msg.className='cmsg';renderTotals();return}
  if(COUPONS[code]){activeCoupon={code,...COUPONS[code]};msg.textContent=t('coupon_ok')+couponLabel(code);msg.className='cmsg ok';}
  else{activeCoupon=null;msg.textContent=t('coupon_bad');msg.className='cmsg err';}renderTotals();}
function discount(sub){if(!activeCoupon)return 0;if(activeCoupon.type==='percent')return Math.round(sub*activeCoupon.val/100);return Math.min(sub,activeCoupon.val);}
function couponLabel(code){const c=COUPONS[code];if(!c)return'';return c.type==='percent'?(c.val+'% '+t('off')):('₪'+c.val+' '+t('off'));}

function openOrder(){renderOrder();openOv('orderModal')}
function closeOrder(){closeOv('orderModal')}
function renderOrder(){
  const keys=Object.keys(CART);window._K=keys;const body=document.getElementById('omBody');
  if(!keys.length){body.innerHTML='<p style="text-align:center;color:var(--muted);padding:20px">'+t('cart_empty')+'</p>';renderTotals();return}
  body.innerHTML=keys.map((k,idx)=>{const it=CART[k];return `<div class="om-row">
    <div class="nm">${esc(it.name)}<small>${esc(it.brand)}${it.size?' · '+esc(it.size):''}</small></div>
    <div class="qy"><button data-i="${idx}" data-a="dec">−</button><span>${it.qty}</span><button data-i="${idx}" data-a="inc">+</button></div>
    <div class="lt">₪${it.qty*it.price}</div>
    <button class="om-del" data-i="${idx}" data-a="del">✕</button></div>`}).join('');
  body.onclick=e=>{const b=e.target.closest('[data-a]');if(!b)return;const key=window._K[+b.dataset.i];if(!key)return;
    cartChange(key,b.dataset.a==='inc'?1:(b.dataset.a==='dec'?-1:-(CART[key]?CART[key].qty:0)));};
  renderTotals();
}
function renderTotals(){const {sub}=cartTotals();const d=discount(sub);const el=document.getElementById('totals');
  if(!Object.keys(CART).length){el.innerHTML='';return}
  el.innerHTML=`<div class="l"><span>${t('subtotal')}</span><span>₪${sub}</span></div>
    ${d?`<div class="l" style="color:#15803d"><span>${t('discount')} (${esc(activeCoupon.code)})</span><span>−₪${d}</span></div>`:''}
    <div class="l grand"><span>${t('grand')}</span><b>₪${sub-d}</b></div>`;}

const WA_NUMBER='972547599923';
function gv(id){var e=document.getElementById(id);return e?e.value.trim():''}
function noteText(){   // הערת הלקוח + פרטי הקופון (כדי שיישמרו ב-DB וייראו בבק אופיס)
  let n=gv('notes');
  if(activeCoupon){const d=discount(cartTotals().sub);if(d)n=(n?n+' | ':'')+`קופון ${activeCoupon.code} (−₪${d})`;}
  return n;
}
function buildOrderText(orderId){
  const keys=Object.keys(CART);if(!keys.length)return '';
  let msg='*הזמנה חדשה — Sephora Favorites*\n';
  if(orderId)msg+=`מס׳ הזמנה: #${orderId}\n`;
  const name=gv('buyer-name'),biz=gv('buyer-biz'),bid=gv('buyer-id'),addr=gv('buyer-addr'),phone=gv('buyer-phone');
  if(name)msg+=`\nשם: ${name}`;if(biz)msg+=`\nעסק: ${biz}`;if(bid)msg+=`\nעוסק/ח.פ: ${bid}`;
  if(addr)msg+=`\nכתובת: ${addr}`;if(phone)msg+=`\nטלפון: ${phone}`;msg+='\n\n';
  let sub=0;keys.forEach(k=>{const it=CART[k];const lt=it.qty*it.price;sub+=lt;
    msg+=`• ${it.name}${it.size?' ('+it.size+')':''} ×${it.qty} = ₪${lt}\n`});
  const d=discount(sub);if(d)msg+=`\nהנחה (${activeCoupon.code}): −₪${d}`;
  msg+=`\n*סה"כ: ₪${sub-d}*`;const notes=gv('notes');if(notes)msg+=`\n\nהערות: ${notes}`;return msg;
}

/* ===== חיבור Supabase (אופציונלי). ריק → fallback לוואטסאפ-טקסט בלבד ===== */
const SB=(window.SUPA&&window.SUPA.url&&window.SUPA.anon&&window.supabase)
  ? window.supabase.createClient(window.SUPA.url,window.SUPA.anon) : null;
const STOCK={};            // ברקוד-מנורמל -> מלאי חי
let STOCK_READY=false;
function nbc(x){return String(x||'').replace(/\D/g,'');}      // ברקוד → ספרות בלבד (תואם sku ב-DB)
function inDB(v){return STOCK_READY && v && STOCK[nbc(v.barcode)]!==undefined;}   // קיים ב-DB?
function isSold(v){if(!STOCK_READY)return false;const n=nbc(v&&v.barcode);return STOCK[n]===undefined||STOCK[n]<=0;}  // לא-ב-DB או אזל → לא זמין
async function loadStock(){
  if(!SB)return;
  try{
    const page=1000; let from=0;        // עוקף את תקרת 1000 השורות של PostgREST
    for(;;){
      const {data,error}=await SB.from('products').select('barcode,stock,active').range(from,from+page-1);
      if(error)throw error;
      (data||[]).forEach(p=>{const n=nbc(p.barcode);if(n)STOCK[n]=p.active?p.stock:0;});
      if(!data||data.length<page)break;
      from+=page;
    }
    STOCK_READY=true; render();    // ציור מחדש — מסמן אזל ומסתיר מוצרים שאינם ב-DB
  }catch(e){console.warn('טעינת מלאי נכשלה:',e);}
}
function cartItems(){      // [{sku, qty}] עבור create_order (sku = ברקוד מנורמל, תואם DB)
  return Object.keys(CART).map(vid=>{const m=VMAP[vid];return {sku:nbc(m&&m.v.barcode),qty:CART[vid].qty};}).filter(it=>it.sku);
}
function validateBuyer(){
  if(!Object.keys(CART).length){alert(t('alert_empty'));return false;}
  const name=gv('buyer-name'),phone=gv('buyer-phone');
  if(!name||!phone){alert(t('alert_fill'));document.getElementById(!name?'buyer-name':'buyer-phone').focus();return false;}
  return true;
}
function setBusy(btn,on){if(!btn)return;if(on){btn.dataset.l=btn.textContent;btn.disabled=true;btn.textContent=t('sending');}else{btn.disabled=false;if(btn.dataset.l)btn.textContent=btn.dataset.l;}}
async function createOrder(channel){   // קריאה אחת ל-create_order → {id,total}. המלאי לא יורד בשלב זה.
  const items=cartItems();
  if(!items.length){alert(t('err_order'));return null;}
  const {data,error}=await SB.rpc('create_order',{
    p_customer_name:gv('buyer-name'),p_customer_phone:gv('buyer-phone'),
    p_customer_email:'',p_customer_type:gv('buyer-biz')?'barber':'retail',
    p_channel:channel,p_note:noteText(),p_items:items});
  if(error){console.error(error);alert(t('err_order'));return null;}
  const row=Array.isArray(data)?data[0]:data;
  return row?{id:row.order_id,total:row.order_total}:null;
}

// א) "שלח הזמנה לאישור (וואטסאפ)" — create_order(channel='whatsapp') ואז פתיחת wa.me עם מספר ההזמנה
async function submitWhatsApp(){
  if(!validateBuyer())return;
  if(!SB){ // עוד לא חובר Supabase — שולחים טקסט בלבד (כמו קודם)
    window.open('https://wa.me/'+WA_NUMBER+'?text='+encodeURIComponent(buildOrderText()));return;
  }
  const btn=document.getElementById('sendBtn');setBusy(btn,true);
  const ord=await createOrder('whatsapp');setBusy(btn,false);
  if(!ord)return;
  window.open('https://wa.me/'+WA_NUMBER+'?text='+encodeURIComponent(buildOrderText(ord.id)));
}
// ב) "שלם עכשיו" — create_order(channel='payment') ואז create-checkout → הפניה ללינק התשלום
async function payNow(){
  if(!validateBuyer())return;
  if(!SB)return;
  const btn=document.getElementById('payBtn');setBusy(btn,true);
  const ord=await createOrder('payment');
  if(!ord){setBusy(btn,false);return;}
  try{
    const {data,error}=await SB.functions.invoke('create-checkout',{body:{order_id:ord.id}});
    if(error)throw error;
    if(data&&data.url){window.location.href=data.url;return;}
    throw new Error('no checkout url');
  }catch(e){console.error(e);alert(t('err_order'));setBusy(btn,false);}
}

function openOv(id){document.getElementById(id).classList.add('open');document.body.style.overflow='hidden'}
function closeOv(id){document.getElementById(id).classList.remove('open');document.body.style.overflow=''}
document.querySelectorAll('.ov').forEach(ov=>ov.addEventListener('click',e=>{if(e.target===ov)closeOv(ov.id)}));
document.addEventListener('touchstart',()=>{if(![...document.querySelectorAll('.ov')].some(o=>o.classList.contains('open')))document.body.style.overflow=''},{passive:true});

function goTop(){window.scrollTo(0,0);document.documentElement.scrollTop=0;document.body.scrollTop=0;}
window.addEventListener('scroll',()=>{
  var y=window.pageYOffset||document.documentElement.scrollTop||0;
  document.getElementById('toTop').classList.toggle('show',y>420);
  if(window.innerHeight+y > document.body.offsetHeight-900) loadMore();   // infinite scroll
},{passive:true});

applyStatic();
render();
if(SB){var _pb=document.getElementById('payBtn');if(_pb)_pb.style.display='';loadStock();}
</script>
</body>
</html>
"""

if __name__ == "__main__":
    main()
