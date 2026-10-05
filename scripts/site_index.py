"""Rebuild sites.json (the atlas's site list) from sites/*/site.json, in catalog order."""
import json
import pathlib
import re

root = pathlib.Path(__file__).resolve().parent.parent
order = re.findall(r"^  ([a-z0-9-]+):\s*$", (root / "sites.yaml").read_text(), flags=re.M)
out = []
for sid in order:
    p = root / "sites" / sid / "site.json"
    if p.exists():
        s = json.loads(p.read_text())
        out.append({k: s.get(k) for k in ("id", "name", "place", "region", "center", "blurb",
                                           "res_m", "ground_density", "stills", "video")})
(root / "sites.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
print(len(out), "sites in sites.json")
