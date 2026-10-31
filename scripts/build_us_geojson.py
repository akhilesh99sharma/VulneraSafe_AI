"""Build web/public/geo/us-states.json: a US-states GeoJSON keyed by `postal`.

Downloads a public-domain US-states GeoJSON (FIPS id + state name) and injects a
`postal` property (2-letter USPS code) on each feature so the MapLibre risk
choropleth can join on the same region codes the risk artifacts use (TX, AK...).
Static output is bundled under web/public so the app never calls a live origin.
"""
import json, urllib.request
from pathlib import Path

ROOT = Path(r"e:\VulneraSafe_AI")
OUT = ROOT / "web" / "public" / "geo"
OUT.mkdir(parents=True, exist_ok=True)

SRC = "https://raw.githubusercontent.com/PublicaMundi/MappingAPI/master/data/geojson/us-states.json"

FIPS_TO_POSTAL = {
    "01":"AL","02":"AK","04":"AZ","05":"AR","06":"CA","08":"CO","09":"CT",
    "10":"DE","11":"DC","12":"FL","13":"GA","15":"HI","16":"ID","17":"IL",
    "18":"IN","19":"IA","20":"KS","21":"KY","22":"LA","23":"ME","24":"MD",
    "25":"MA","26":"MI","27":"MN","28":"MS","29":"MO","30":"MT","31":"NE",
    "32":"NV","33":"NH","34":"NJ","35":"NM","36":"NY","37":"NC","38":"ND",
    "39":"OH","40":"OK","41":"OR","42":"PA","44":"RI","45":"SC","46":"SD",
    "47":"TN","48":"TX","49":"UT","50":"VT","51":"VA","53":"WA","54":"WV",
    "55":"WI","56":"WY","72":"PR",
}

req = urllib.request.Request(SRC, headers={"User-Agent": "VulneraSafe-build"})
with urllib.request.urlopen(req, timeout=60) as r:
    gj = json.loads(r.read().decode("utf-8"))

n_tagged = 0
for feat in gj.get("features", []):
    fid = str(feat.get("id", "")).zfill(2)
    postal = FIPS_TO_POSTAL.get(fid)
    props = feat.setdefault("properties", {})
    if postal:
        props["postal"] = postal
        n_tagged += 1
    # drop the unused density field to keep the file lean
    props.pop("density", None)

out_path = OUT / "us-states.json"
out_path.write_text(json.dumps(gj, separators=(",", ":")), encoding="utf-8")
print(f"WROTE {out_path} features={len(gj.get('features', []))} tagged_postal={n_tagged} bytes={out_path.stat().st_size}")
