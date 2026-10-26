import glob, re, shutil

PATTERN = re.compile(r'(<form\b[^>]*\bmethod\s*=\s*["\']?post["\']?[^>]*>)', re.I)
TOKEN = '\n    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">'

for path in glob.glob("templates/**/*.html", recursive=True):
    html = open(path, encoding="utf-8").read()
    if "csrf_token" in html:
        print("skipped (already has a token):", path)
        continue
    new_html, count = PATTERN.subn(lambda m: m.group(1) + TOKEN, html)
    if count:
        shutil.copy(path, path + ".bak")
        open(path, "w", encoding="utf-8").write(new_html)
        print(f"updated {count} form(s): {path}")