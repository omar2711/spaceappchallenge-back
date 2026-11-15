"""Data bundle: files the API needs that are NOT in git (too heavy).

    python tools/data_bundle.py make                 # -> dist/data-bundle.tar.gz (upload it as a GitHub release asset)
    python tools/data_bundle.py fetch <url>          # download + extract into ./data (used by the Dockerfile)

Contents: data/analysis/fields/ (prepared fields for /spectrum, ~50 MB) and data/ephemeris/ (JPL DE421 + lunar
frame kernels for the Moon / Cochabamba endpoints, ~18 MB). Standard library only (runs in the Docker build).
"""
import hashlib
import sys
import tarfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTENTS = ["data/analysis/fields", "data/ephemeris"]
BUNDLE = ROOT / "dist" / "data-bundle.tar.gz"


def make():
    BUNDLE.parent.mkdir(exist_ok=True)
    with tarfile.open(BUNDLE, "w:gz", compresslevel=6) as tar:
        for rel in CONTENTS:
            path = ROOT / rel
            if not path.exists():
                sys.exit(f"missing {rel}")
            tar.add(path, arcname=rel)
    digest = hashlib.sha256(BUNDLE.read_bytes()).hexdigest()
    print(f"{BUNDLE} {BUNDLE.stat().st_size / 2**20:.1f} MB sha256={digest}")


def fetch(url, dest=ROOT, tries=4):
    tmp = dest / "data-bundle.tar.gz"
    for i in range(tries):
        try:
            urllib.request.urlretrieve(url, tmp)
            break
        except Exception as exc:  # GitHub release downloads occasionally hiccup
            print(f"download attempt {i + 1} failed: {exc}")
            time.sleep(5 * (i + 1))
    else:
        sys.exit("could not download the data bundle")
    with tarfile.open(tmp) as tar:
        names = tar.getnames()
        if any(n.startswith(("/", "..")) or ".." in Path(n).parts or not n.startswith("data/") for n in names):
            sys.exit("refusing to extract: unexpected paths in bundle")
        try:
            tar.extractall(dest, filter="data")   # Python >= 3.11.4 / 3.12
        except TypeError:
            tar.extractall(dest)                   # older Python: paths were validated above
    tmp.unlink()
    print(f"extracted {len(names)} entries into {dest / 'data'}")


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "make":
        make()
    elif len(sys.argv) >= 3 and sys.argv[1] == "fetch":
        fetch(sys.argv[2], Path(sys.argv[3]) if len(sys.argv) > 3 else ROOT)
    else:
        sys.exit(__doc__)
