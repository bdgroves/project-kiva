"""Rebuild sites.json (the atlas's site list) from sites/*/site.json, in catalog order.

The words about each place (name, place, blurb, about, links) live in sites.yaml, so
they're copied into each sites/<id>/site.json here too: editing the text doesn't
need a lidar rebuild.
"""
import json
import pathlib

import yaml

root = pathlib.Path(__file__).resolve().parent.parent
catalog = yaml.safe_load((root / "sites.yaml").read_text())["sites"]
out = []
for sid, cat in catalog.items():
    p = root / "sites" / sid / "site.json"
    if not p.exists():
        continue
    s = json.loads(p.read_text())
    words = {"name": cat["name"], "place": cat["place"],
             "blurb": " ".join(cat.get("blurb", "").split()),
             "about": " ".join(cat.get("about", "").split()),
             "links": cat.get("links", [])}
    if any(s.get(k) != v for k, v in words.items()):
        s.update(words)
        p.write_text(json.dumps(s, indent=1, ensure_ascii=False))
    out.append({k: s.get(k) for k in ("id", "name", "place", "region", "center", "blurb",
                                       "res_m", "ground_density", "stills", "video")})
(root / "sites.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
print(len(out), "sites in sites.json")
