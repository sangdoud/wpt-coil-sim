import hashlib
import os

p = r"C:\wpt\Projecttonight.aedt"
h = hashlib.md5()
with open(p, "rb") as f:
    for chunk in iter(lambda: f.read(1 << 20), b""):
        h.update(chunk)

size = os.path.getsize(p)
digest = h.hexdigest()
print(size, digest)
print("expected_size :", 25155997, "->", "MATCH" if size == 25155997 else "MISMATCH")
print("expected_md5  :", "9bb98917d803ca42191a6abee8360d82",
      "->", "MATCH" if digest == "9bb98917d803ca42191a6abee8360d82" else "MISMATCH")
