import json
import urllib.request
import urllib.error

print("=== pyaedt 1.3.0 metadata ===")
try:
    d = json.load(urllib.request.urlopen("https://pypi.org/pypi/pyaedt/1.3.0/json", timeout=30))
    i = d["info"]
    print("name:", i["name"])
    print("version:", i["version"])
    print("requires_python:", i["requires_python"])
    print("requires_dist:")
    for r in (i.get("requires_dist") or []):
        print("    ", r)
    print("files:")
    for f in d["urls"]:
        print("    ", f["filename"], f["packagetype"], f["python_version"], f["size"])
except Exception as e:
    print("FAIL", type(e).__name__, e)

print()
print("=== github repo access ===")
for u in [
    "https://api.github.com/repos/sangdoud/wpt-coil-sim",
    "https://github.com/sangdoud/wpt-coil-sim",
    "https://api.github.com/users/sangdoud",
]:
    try:
        r = urllib.request.urlopen(u, timeout=25)
        print(u, "->", r.status)
    except urllib.error.HTTPError as e:
        print(u, "-> HTTPError", e.code, e.reason)
    except Exception as e:
        print(u, "-> FAIL", type(e).__name__, e)

print()
print("=== python version / platform ===")
import sys, platform
print(sys.version)
print(platform.platform())
print("executable:", sys.executable)
