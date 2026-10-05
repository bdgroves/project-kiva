#!/usr/bin/env bash
# Copy built sites from downloaded artifacts (incoming/site-*) into sites/,
# rebuild sites.json, commit and push. Used by the Build sites and Publish
# sites workflows.
set -euxo pipefail
mkdir -p logs sites
for d in incoming/site-*; do
  [ -d "$d" ] || continue
  id=${d#incoming/site-}
  if [ -f "$d/build.log" ]; then mv "$d/build.log" "logs/$id.log"; fi
  if [ -f "$d/site.json" ]; then
    rm -rf "sites/$id" && mkdir -p "sites/$id" && cp -r "$d/." "sites/$id/"
  fi
done
if [ -f lock/pixi.lock ]; then cp lock/pixi.lock pixi.lock; fi
python3 scripts/site_index.py
git config user.name  "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
git add -A sites sites.json logs
if [ -f pixi.lock ]; then git add pixi.lock; fi
if git diff --cached --quiet; then echo "nothing new"; exit 0; fi
git commit -q -m "sites: lidar relief and forge3d renders [skip ci]"
for i in 1 2 3; do
  if git pull --rebase origin main && git push origin HEAD:main; then exit 0; fi
  sleep 5
done
exit 1
