#!/bin/bash
# ============================================================
#  Sephora Favorites — פרסום הקטלוג ל-GitHub Pages
#  הרצה:  bash push_catalog.sh
#  צריך:  חשבון GitHub + Personal Access Token עם הרשאת "repo".
#         (יצירת טוקן: github.com → Settings → Developer settings →
#          Personal access tokens → Tokens (classic) → Generate new token,
#          סמן את התיבה "repo", צור והעתק.)
# ============================================================
set -e
cd "$(dirname "$0")"   # תיקיית catalog

echo "──────────────────────────────────────────"
echo "  פרסום קטלוג Sephora Favorites ל-GitHub"
echo "──────────────────────────────────────────"

# --- פרטי משתמש ---
read -r -p "שם משתמש GitHub: " GH_USER
read -r -p "שם ה-repo [sephora-favorites]: " GH_REPO
GH_REPO="${GH_REPO:-sephora-favorites}"
read -r -s -p "Personal Access Token (לא יוצג): " GH_TOKEN
echo ""

if [ -z "$GH_USER" ] || [ -z "$GH_TOKEN" ]; then
  echo "❌ חסר שם משתמש או טוקן. ביטול."; exit 1
fi

SITE="https://${GH_USER}.github.io/${GH_REPO}"

# --- 1. עדכון כתובת התצוגה המקדימה (og:image) ובנייה מחדש ---
echo "→ מעדכן כתובת אתר ל-${SITE} ובונה מחדש…"
python3 - "$SITE" << 'PY'
import re, sys
site = sys.argv[1]
p = "build_catalog.py"
s = open(p, encoding="utf-8").read()
s = re.sub(r'^SITE_URL = ".*"', f'SITE_URL = "{site}"', s, count=1, flags=re.M)
open(p, "w", encoding="utf-8").write(s)
PY
python3 build_catalog.py

# --- 2. אתחול git נקי (init מחדש בכל פעם — push מהיר ונקי) ---
echo "→ מכין repo מקומי…"
rm -rf .git
git init -q
git checkout -q -b main
git add index.html images og-image.png build_catalog.py og-template.html
git -c user.email="catalog@local" -c user.name="catalog" commit -q -m "catalog update $(date +%Y-%m-%d)"

# --- 3. יצירת ה-repo ב-GitHub (אם לא קיים) ---
echo "→ יוצר/מאמת repo ב-GitHub…"
curl -s -o /dev/null -w "%{http_code}" -H "Authorization: token ${GH_TOKEN}" \
  https://api.github.com/user/repos \
  -d "{\"name\":\"${GH_REPO}\",\"private\":false,\"description\":\"Sephora Favorites — קטלוג דיגיטלי\"}" >/dev/null || true

# --- 4. דחיפה ---
echo "→ דוחף ל-GitHub…"
git remote remove origin 2>/dev/null || true
git remote add origin "https://${GH_USER}:${GH_TOKEN}@github.com/${GH_USER}/${GH_REPO}.git"
git push -f -q origin main

# --- 5. הפעלת GitHub Pages (branch main, שורש) ---
echo "→ מפעיל GitHub Pages…"
curl -s -o /dev/null -X POST -H "Authorization: token ${GH_TOKEN}" \
  -H "Accept: application/vnd.github+json" \
  "https://api.github.com/repos/${GH_USER}/${GH_REPO}/pages" \
  -d '{"source":{"branch":"main","path":"/"}}' || true

echo ""
echo "✅ הסתיים!"
echo "   הקטלוג: ${SITE}/"
echo "   (לוקח ~1 דקה עד שה-Pages עולה בפעם הראשונה.)"
echo ""
echo "   לשיתוף בוואטסאפ — שלח את הקישור:  ${SITE}/"
echo "   תמונת התצוגה תופיע אחרי שה-Pages פעיל."
