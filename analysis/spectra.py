"""T3: forced spectrophotometry. Every exposure gives one (wavelength, flux) point at the target, because
each pixel of SPHEREx's linear-variable filters sees a different wavelength (WCS-WAVE). Points are binned at
SPHEREx's native resolution into one spectrum per epoch and one combined spectrum.

Band measurements are reported with their significance; the reference bands are MARKERS for the plot, not
automatic detections.
"""
import numpy as np

SYSTEMATIC_FLOOR = 0.03       # fractional, as in the light curves (eps Ind B stable to ~3 %)
D5_START_UM = 3.82            # detectors 1-4 have R~40, detectors 5-6 R~120
MIN_POINTS_WINDOW = 2

# Plot markers. 'verified' = value checked against a source during this work (see docs/analysis_t3_t4.md).
REFERENCE_BANDS = [
    {"label": "H2O", "phase": "gas", "wavelength_um": 1.15, "range_um": [1.10, 1.17],
     "source": "Burgasser et al. 2006 (H2O-J index window 1.140-1.165)", "verified": True},
    {"label": "H2O", "phase": "gas", "wavelength_um": 1.4, "range_um": [1.33, 1.52],
     "source": "Burgasser et al. 2006 (H2O-H index window 1.48-1.52, red wing of the 1.4 um band)", "verified": True},
    {"label": "CH4", "phase": "gas", "wavelength_um": 1.65, "range_um": [1.635, 1.675],
     "source": "Burgasser et al. 2006 (CH4-H index window)", "verified": True},
    {"label": "H2O", "phase": "gas", "wavelength_um": 1.9, "range_um": [1.80, 2.00],
     "source": "standard H2O band; Burgasser et al. 2006 H2O-K window 1.975-1.995 (not re-checked online)", "verified": False},
    {"label": "CH4", "phase": "gas", "wavelength_um": 2.3, "range_um": [2.215, 2.35],
     "source": "standard CH4 band; Burgasser et al. 2006 CH4-K window 2.215-2.255 (not re-checked online)", "verified": False},
    {"label": "H2O", "phase": "gas", "wavelength_um": 2.7, "range_um": [2.5, 2.9],
     "source": "standard H2O fundamental region (not re-checked online)", "verified": False},
    {"label": "H2O ice", "phase": "ice", "wavelength_um": 3.05, "range_um": [2.95, 3.15],
     "source": "SPHEREx mission page (H2O, CO2, CO ices at 3.05, 4.27, 4.67 um)", "verified": True},
    {"label": "CH4", "phase": "gas", "wavelength_um": 3.3, "range_um": [3.2, 3.4],
     "source": "Cushing et al. 2005 (CH4 nu3 fundamental band at ~3.3 um)", "verified": True},
    {"label": "CO2 ice", "phase": "ice", "wavelength_um": 4.27, "range_um": [4.22, 4.32],
     "source": "SPHEREx mission page", "verified": True},
    {"label": "CO", "phase": "ice/gas", "wavelength_um": 4.67, "range_um": [4.62, 4.72],
     "source": "SPHEREx mission page (CO ice); gas-phase CO fundamental also absorbs near 4.6-4.7 um", "verified": True},
]

# Brown-dwarf style ratio indices: mean flux in the band window / mean flux in a reference (peak) window.
# Windows from Burgasser et al. 2006 where available; CH4-3.3 is our own definition for SPHEREx.
RATIO_INDICES = [
    {"name": "H2O-J", "band": [1.140, 1.165], "ref": [1.260, 1.285], "molecule": "H2O", "source": "Burgasser+2006"},
    {"name": "H2O-H", "band": [1.480, 1.520], "ref": [1.560, 1.600], "molecule": "H2O", "source": "Burgasser+2006"},
    {"name": "CH4-H", "band": [1.635, 1.675], "ref": [1.560, 1.600], "molecule": "CH4", "source": "Burgasser+2006"},
    {"name": "H2O-K", "band": [1.975, 1.995], "ref": [2.080, 2.100], "molecule": "H2O", "source": "Burgasser+2006 (not re-checked online)"},
    {"name": "CH4-K", "band": [2.215, 2.255], "ref": [2.080, 2.120], "molecule": "CH4", "source": "Burgasser+2006 (not re-checked online)"},
    {"name": "CH4-3.3", "band": [3.250, 3.400], "ref": [3.900, 4.100], "molecule": "CH4", "source": "this work (SPHEREx-specific)"},
]

# Ice absorption depth: 1 - F(band) / continuum interpolated (log-log) between two windows.
DEPTH_BANDS = [
    {"name": "H2O ice 3.05", "band": [2.95, 3.15], "cont": [[2.45, 2.65], [3.75, 3.95]], "molecule": "H2O ice"},
    {"name": "CO2 ice 4.27", "band": [4.22, 4.32], "cont": [[4.10, 4.18], [4.36, 4.44]], "molecule": "CO2 ice"},
    {"name": "CO 4.67", "band": [4.62, 4.72], "cont": [[4.50, 4.58], [4.78, 4.86]], "molecule": "CO"},
]


def _resolution(lam):
    return np.where(lam < D5_START_UM, 40.0, 120.0)


def _wmean(f, e):
    w = 1 / e ** 2
    m = float(np.sum(w * f) / np.sum(w))
    formal = float(1 / np.sqrt(np.sum(w)))
    scatter = float(np.std(f, ddof=1) / np.sqrt(len(f))) if len(f) > 1 else formal
    return m, float(np.hypot(max(formal, scatter), SYSTEMATIC_FLOOR * abs(m)))


def bin_spectrum(lam, flux, err, lower_limit=None):
    """Bin points at SPHEREx native resolution (one bin per resolution element)."""
    lower_limit = np.zeros(len(lam), bool) if lower_limit is None else np.asarray(lower_limit, bool)
    order = np.argsort(lam)
    lam, flux, err, lower_limit = lam[order], flux[order], err[order], lower_limit[order]
    edges = [0.74]
    while edges[-1] < 5.02:
        edges.append(edges[-1] * (1 + 1 / _resolution(np.array([edges[-1]]))[0]))
    edges = np.array(edges)
    idx = np.searchsorted(edges, lam) - 1
    out = []
    for b in np.unique(idx):
        m = idx == b
        f, e = flux[m], err[m]
        mean, unc = _wmean(f, e)
        out.append({"wavelength_um": round(float(np.average(lam[m], weights=1 / e ** 2)), 4),
                    "flux": round(mean, 5), "err": round(unc, 5), "n": int(m.sum()),
                    "lower_limit": bool(lower_limit[m].any())})
    return out


def _window(lam, flux, err, lo, hi):
    """Weighted mean in [lo, hi], widened to one resolution element if it holds too few points."""
    half_res = (lo + hi) / 2 / _resolution(np.array([(lo + hi) / 2]))[0] / 2
    for pad in (0.0, half_res):
        m = (lam >= lo - pad) & (lam <= hi + pad)
        if m.sum() >= MIN_POINTS_WINDOW:
            return (*_wmean(flux[m], err[m]), int(m.sum()), pad > 0)
    return None


def band_measurements(lam, flux, err):
    """Ratio indices and ice depths with 1-sigma errors and significance of absorption (sigma)."""
    out = []
    for ix in RATIO_INDICES:
        b, r = _window(lam, flux, err, *ix["band"]), _window(lam, flux, err, *ix["ref"])
        entry = {"name": ix["name"], "type": "ratio", "molecule": ix["molecule"], "band_um": ix["band"],
                 "ref_um": ix["ref"], "source": ix["source"]}
        if b and r and r[0] > 0:
            val = b[0] / r[0]
            e = abs(val) * np.hypot(b[1] / b[0] if b[0] else np.inf, r[1] / r[0])
            entry.update(value=round(val, 4), err=round(float(e), 4), n_band=b[2], n_ref=r[2],
                         widened=bool(b[3] or r[3]), absorption_sigma=round(float((1 - val) / e), 1) if e > 0 else None)
        else:
            entry.update(value=None, err=None, note="no data in window")
        out.append(entry)
    for db in DEPTH_BANDS:
        b = _window(lam, flux, err, *db["band"])
        c1, c2 = (_window(lam, flux, err, *w) for w in db["cont"])
        entry = {"name": db["name"], "type": "depth", "molecule": db["molecule"], "band_um": db["band"],
                 "continuum_um": db["cont"]}
        if b and c1 and c2 and c1[0] > 0 and c2[0] > 0:
            l1, l2, lb = (np.mean(w) for w in (*db["cont"], db["band"]))
            t = np.log(lb / l1) / np.log(l2 / l1)
            cont = float(np.exp(np.log(c1[0]) * (1 - t) + np.log(c2[0]) * t))
            cont_rel = float(np.hypot((1 - t) * c1[1] / c1[0], t * c2[1] / c2[0]))
            depth = 1 - b[0] / cont
            e = (b[0] / cont) * np.hypot(b[1] / b[0] if b[0] else np.inf, cont_rel)
            entry.update(value=round(float(depth), 4), err=round(float(e), 4), n_band=b[2],
                         absorption_sigma=round(float(depth / e), 1) if e > 0 else None)
        else:
            entry.update(value=None, err=None, note="no data in band or continuum windows")
        out.append(entry)
    for e in out:
        s = e.get("absorption_sigma")
        e["significant"] = bool(s is not None and s >= 3)
    return out


INTERPRETATION = {
    "brown_dwarf": {"depth": "In a brown dwarf this window traces gas-phase absorption (CH4/H2O/CO), not ice."},
    "high_proper_motion_star": {"ratio": "M dwarf: no methane expected (control).",
                                "depth": "Stellar photosphere: no ice expected (control)."},
    "variable_star": {"ratio": "Not a brown dwarf: indices are reported for completeness only.",
                      "depth": "Circumstellar dust/ice possible in young stars; check per-epoch spectra."},
}


def interpret(measurements, kind):
    notes = INTERPRETATION.get(kind, {})
    for m in measurements:
        if m["type"] in notes:
            m["interpretation"] = notes[m["type"]]
    return measurements


def spectra_from_photometry(phot, label=None, position=None, combine_note=None, kind=None):
    """Per-epoch and combined spectra + band measurements from a photometry table (analysis/photometry.py).
    Uses flag 'ok' points; if a detector has no 'ok' points, its 'saturated' points are used as lower limits."""
    use = np.asarray(phot["flag"]) == "ok"
    for det in set(int(d) for d in phot["detector"]):
        d = np.asarray(phot["detector"]) == det
        if not (use & d).any():
            use |= d & (np.asarray(phot["flag"]) == "saturated")
    t = phot[use]
    lam = np.asarray(t["wavelength_um"], float)
    flux = np.asarray(t["flux"], float)
    err = np.asarray(t["err"], float)
    ll = np.asarray(t["flag"]) == "saturated"
    base = {"units": "mJy", "binning": "native resolution (R~40 below 3.82 um, R~120 above)"}
    if label:
        base["label"] = label
    if position:
        base["position"] = position
    spectra = []
    for ep in sorted(set(np.asarray(t["epoch"]).astype(str)), key=lambda e: int(e[1:])):
        m = np.asarray(t["epoch"]).astype(str) == ep
        spectra.append({"epoch": ep, **base, "n_exposures": int(m.sum()),
                        "mjd_mean": round(float(np.mean(t["mjd"][m])), 3),
                        "points": bin_spectrum(lam[m], flux[m], err[m], ll[m])})
    combined = {"epoch": "combined", **base, "n_exposures": int(len(t)),
                "points": bin_spectrum(lam, flux, err, ll),
                "band_measurements": interpret(band_measurements(lam[~ll], flux[~ll], err[~ll]), kind)}
    if combine_note:
        combined["note"] = combine_note
    spectra.append(combined)
    return spectra
