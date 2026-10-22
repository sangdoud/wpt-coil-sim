import json
import urllib.request
import urllib.error

print("=== public repos of user sangdoud ===")
try:
    req = urllib.request.Request(
        "https://api.github.com/users/sangdoud/repos?per_page=100",
        headers={"User-Agent": "dsh-probe", "Accept": "application/vnd.github+json"},
    )
    data = json.load(urllib.request.urlopen(req, timeout=30))
    if not data:
        print("(no public repos)")
    for r in data:
        print(f"  {r['full_name']}  private={r['private']}  size={r['size']}KB  pushed={r['pushed_at']}")
except Exception as e:
    print("FAIL", type(e).__name__, e)

print()
print("=== probe candidate repo names ===")
names = [
    "wpt-coil-sim",
    "wpt",
    "wpt_coupling_optimization",
    "WPT",
    "wpt-sim",
    "maxwell-wpt",
]
for n in names:
    u = f"https://api.github.com/repos/sangdoud/{n}"
    try:
        req = urllib.request.Request(u, headers={"User-Agent": "dsh-probe"})
        r = urllib.request.urlopen(req, timeout=20)
        print(f"  {n}: {r.status}")
    except urllib.error.HTTPError as e:
        print(f"  {n}: HTTP {e.code}")
    except Exception as e:
        print(f"  {n}: FAIL {type(e).__name__}")
