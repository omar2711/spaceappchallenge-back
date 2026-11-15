"""Target specifications: named targets (pipeline/targets.yaml) and arbitrary coordinates.

A Spec bundles everything the pipeline needs about "what to image": position versus time, field of view,
and where its raw / processed / public files live. Named targets keep their historical paths
(data/raw/<id>, data/processed/<id>, public-data/targets/<id>); custom coordinates live under .../custom/<id>.
"""
import hashlib
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import astropy.units as u
import yaml
from astropy.coordinates import Distance, SkyCoord
from astropy.time import Time

TARGETS_PATH = Path(__file__).with_name("targets.yaml")
RAW_ROOT = Path("data/raw")
PROCESSED_ROOT = Path("data/processed")
PUBLIC_ROOT = Path("public-data")

CUSTOM_FOV_DEFAULT = 3.0
CUSTOM_FOV_MAX = 6.0
CUSTOM_MAX_PER_GROUP_DEFAULT = 2  # API default (team decision 2026-11-14): ~2-3 min per field
CUSTOM_MAX_PER_GROUP_LIMIT = 30


@lru_cache(maxsize=None)
def load_targets():
    return yaml.safe_load(TARGETS_PATH.read_text(encoding="utf-8"))


def get_target(target_id):
    targets = load_targets()
    if target_id not in targets:
        raise SystemExit(f"unknown target '{target_id}'; known: {', '.join(targets)}")
    return targets[target_id]


@dataclass(frozen=True)
class Spec:
    id: str
    name: str
    kind: str
    fov_arcmin: float
    astrometry: dict
    raw_dir: Path
    processed_dir: Path
    public_dir: Path
    notes: str = ""
    max_per_group: int | None = None
    extra: dict = field(default_factory=dict)

    @property
    def moving(self):
        a = self.astrometry
        return bool(a.get("pmra") or a.get("pmdec")) and a.get("plx", 0) > 0

    def reference_coord(self):
        """SkyCoord at the catalogue epoch (with space motion when the target moves)."""
        a = self.astrometry
        if not self.moving:
            return SkyCoord(ra=a["ra"] * u.deg, dec=a["dec"] * u.deg)
        return SkyCoord(
            ra=a["ra"] * u.deg, dec=a["dec"] * u.deg,
            pm_ra_cosdec=a["pmra"] * u.mas / u.yr, pm_dec=a["pmdec"] * u.mas / u.yr,
            distance=Distance(parallax=a["plx"] * u.mas),
            radial_velocity=a.get("rv", 0.0) * u.km / u.s,
            obstime=Time(a["epoch"], format="jyear"),
        )

    def position_at(self, time):
        """ICRS position at `time` (annual parallax displacement not applied: < 0.1 px for every target)."""
        c = self.reference_coord()
        if not self.moving:
            return c
        c = c.apply_space_motion(new_obstime=Time(time))
        return SkyCoord(c.ra, c.dec)


def target_spec(target_id):
    t = get_target(target_id)
    return Spec(id=target_id, name=t["name"], kind=t["kind"], fov_arcmin=float(t["fov_arcmin"]),
                astrometry=t["astrometry"], raw_dir=RAW_ROOT / target_id, processed_dir=PROCESSED_ROOT / target_id,
                public_dir=PUBLIC_ROOT / "targets" / target_id, notes=t.get("notes", ""))


def custom_id(ra, dec, fov_arcmin, max_per_group):
    """Stable id from rounded inputs (0.36" in position), so near-identical requests share the cache."""
    key = f"{round(ra % 360, 4):.4f},{round(dec, 4):.4f},{fov_arcmin:.2f},{max_per_group}"
    return "c" + hashlib.sha1(key.encode()).hexdigest()[:12]


def validate_custom(ra, dec, fov_arcmin=CUSTOM_FOV_DEFAULT, max_per_group=CUSTOM_MAX_PER_GROUP_DEFAULT):
    ra, dec, fov_arcmin, max_per_group = float(ra), float(dec), float(fov_arcmin), int(max_per_group)
    if not 0 <= ra < 360:
        raise ValueError("ra must be in [0, 360) degrees")
    if not -90 <= dec <= 90:
        raise ValueError("dec must be in [-90, 90] degrees")
    if not 0 < fov_arcmin <= CUSTOM_FOV_MAX:
        raise ValueError(f"fov_arcmin must be in (0, {CUSTOM_FOV_MAX}]")
    if not 1 <= max_per_group <= CUSTOM_MAX_PER_GROUP_LIMIT:
        raise ValueError(f"max_exposures_per_group must be in [1, {CUSTOM_MAX_PER_GROUP_LIMIT}]")
    return ra, dec, fov_arcmin, max_per_group


def custom_spec(ra, dec, fov_arcmin=CUSTOM_FOV_DEFAULT, max_per_group=CUSTOM_MAX_PER_GROUP_DEFAULT):
    ra, dec, fov_arcmin, max_per_group = validate_custom(ra, dec, fov_arcmin, max_per_group)
    cid = custom_id(ra, dec, fov_arcmin, max_per_group)
    return Spec(id=cid, name=f"RA {ra:.4f}, Dec {dec:+.4f}", kind="custom", fov_arcmin=fov_arcmin,
                astrometry={"ra": ra, "dec": dec, "epoch": 2000.0, "pmra": 0.0, "pmdec": 0.0, "plx": 0.0,
                            "source": "user coordinates (ICRS), no proper motion"},
                raw_dir=RAW_ROOT / "custom" / cid, processed_dir=PROCESSED_ROOT / "custom" / cid,
                public_dir=PUBLIC_ROOT / "custom" / cid, max_per_group=max_per_group,
                notes="Custom field from user coordinates; target_px marks the requested position.")


# Backwards-compatible helpers used by older scripts and analysis/.
def reference_coord(target_id):
    return target_spec(target_id).reference_coord()


def position_at(target_id, time):
    return target_spec(target_id).position_at(time)
