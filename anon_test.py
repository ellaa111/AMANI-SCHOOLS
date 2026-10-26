import json
import os
import urllib.error
import urllib.request

from dotenv import load_dotenv

load_dotenv()
url = os.environ["SUPABASE_URL"].rstrip("/")
key = os.environ["SUPABASE_KEY"]

req = urllib.request.Request(
    f"{url}/rest/v1/students?select=full_name,admission_no,parent_phone",
    headers={"apikey": key, "Authorization": f"Bearer {key}"},
)

print("Requesting students with the anon key and no login...\n")
try:
    with urllib.request.urlopen(req) as r:
        rows = json.loads(r.read())
        print(f"HTTP {r.status}: {len(rows)} row(s) returned")
        print(json.dumps(rows, indent=2))
        if rows:
            print("\nRESULT: VULNERABLE - data readable without logging in")
        else:
            print("\nRESULT: PROTECTED - no data returned")
except urllib.error.HTTPError as e:
    print(f"HTTP {e.code}: {e.read().decode()}")
    print("\nRESULT: request rejected")