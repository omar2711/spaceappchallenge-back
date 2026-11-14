"""T2: light curves per detector from the per-exposure photometry.

Each exposure sees the target at a different wavelength inside the detector's band (LVF), so raw fluxes
mix spectrum and variability. We fit, per detector, flux = S(lambda) * g(epoch): a smooth spectral shape
shared by all epochs (binned in wavelength, ~6 exposures per bin, linearly interpolated: a low-resolution
spectrum; a polynomial cannot follow brown-dwarf bands) times one brightness factor per epoch. g is the light curve;
fluxes are reported "corrected" to the detector's central wavelength.
Variability significance: chi2 of the per-epoch fluxes against a constant, with a systematic floor
(SYSTEMATIC_FLOOR, calibrated so eps Ind B, a stable brown dwarf, is consistent with constant).
"""
import numpy as np
from astropy.table import Table
from scipy.stats import chi2 as chi2_dist

SYSTEMATIC_FLOOR = 0.03   # fractional; B1 found eps Ind B stable to ~3 %
SIGNIFICANCE_P = 1e-3
MIN_POINTS_PER_EPOCH = 3
SUB_EPOCH_DAYS = 30.0
SUB_EPOCH_MIN_SPAN = 45.0
MIN_COMBINED_SNR = 5.0    # detection threshold over all usable exposures of a detector


POINTS_PER_BIN = 6
MAX_BINS = 25


class BinnedShape:
    """Piecewise-linear spectral shape from weighted means in wavelength bins (equal-count edges)."""

    def __init__(self, lam, values, errs):
        n_bins = int(np.clip(len(lam) // POINTS_PER_BIN, 1, MAX_BINS))
        edges = np.quantile(lam, np.linspace(0, 1, n_bins + 1))
        idx = np.clip(np.searchsorted(edges, lam, side="right") - 1, 0, n_bins - 1)
        centers, means = [], []
        for b in range(n_bins):
            m = idx == b
            if m.sum() == 0:
                continue
            w = 1 / errs[m] ** 2
            centers.append(float(np.sum(w * lam[m]) / np.sum(w)))
            means.append(float(np.sum(w * values[m]) / np.sum(w)))
        self.centers, self.means = np.array(centers), np.array(means)

    def __call__(self, lam):
        return np.interp(lam, self.centers, self.means)


def fit_shape_and_epochs(lam, flux, err, epoch, iters=6):
    """flux ~ S(lam) * g[epoch]. Returns (shape, lam0, g dict). g normalised to mean 1."""
    lam0 = float(np.median(lam))
    epochs = sorted(set(epoch), key=lambda e: int(e[1:]) if e[1:].isdigit() else 0)
    g = {e: 1.0 for e in epochs}
    for _ in range(iters):
        ge = np.array([g[e] for e in epoch])
        shape = BinnedShape(lam, flux / ge, err / ge)
        S = shape(lam)
        for e in epochs:
            m = epoch == e
            w = (S[m] / err[m]) ** 2
            g[e] = float(np.sum(w * flux[m] / S[m]) / np.sum(w))
        norm = np.mean(list(g.values()))
        g = {e: v / norm for e, v in g.items()}
    return shape, lam0, g


def _weighted_mean(values, errs):
    w = 1 / errs ** 2
    mean = float(np.sum(w * values) / np.sum(w))
    formal = float(1 / np.sqrt(np.sum(w)))
    scatter = float(np.std(values, ddof=1) / np.sqrt(len(values))) if len(values) > 1 else formal
    return mean, max(formal, scatter)


def _group(points, keyfunc, min_n):
    groups = {}
    for p in points:
        groups.setdefault(keyfunc(p), []).append(p)
    out = []
    for key, ps in groups.items():
        if len(ps) < min_n:
            continue
        f = np.array([p["flux_corrected"] for p in ps])
        e = np.array([p["err_corrected"] for p in ps])
        mean, err = _weighted_mean(f, e)
        out.append({"key": key, "mjd": float(np.mean([p["mjd"] for p in ps])), "flux": mean, "err": err, "n": len(ps)})
    return out


def variability(per_epoch, lower_limit=False):
    if len(per_epoch) < 2:
        return {"amplitude_mag": None, "chi2_reduced": None, "p_value": None, "systematic_floor": SYSTEMATIC_FLOOR,
                "significant": False, "lower_limit": lower_limit, "note": "fewer than 2 epochs"}
    f = np.array([p["flux"] for p in per_epoch])
    e = np.array([p["err"] for p in per_epoch])
    e_tot = np.hypot(e, SYSTEMATIC_FLOOR * np.abs(f))
    w = 1 / e_tot ** 2
    mean = np.sum(w * f) / np.sum(w)
    chi2 = float(np.sum(((f - mean) / e_tot) ** 2))
    dof = len(f) - 1
    p = float(chi2_dist.sf(chi2, dof))
    amp = float(2.5 * np.log10(f.max() / f.min())) if f.min() > 0 else None
    sig = bool(p < SIGNIFICANCE_P)
    note = "constant within errors" if not sig else "significant variability"
    if lower_limit:
        note += "; based on saturated (lower-limit) fluxes, amplitude unreliable"
    return {"amplitude_mag": None if amp is None else round(amp, 3), "chi2_reduced": round(chi2 / dof, 2),
            "p_value": float(f"{p:.3g}"), "systematic_floor": SYSTEMATIC_FLOOR, "significant": sig,
            "lower_limit": lower_limit, "note": note}


def light_curves(phot: Table, detector_ranges):
    curves = []
    for det in sorted(set(int(d) for d in phot["detector"])):
        t = phot[phot["detector"] == det]
        ok = t["flag"] == "ok"
        lower_limit = False
        use = ok
        if ok.sum() < 2 * MIN_POINTS_PER_EPOCH and np.sum(t["flag"] == "saturated") >= 2 * MIN_POINTS_PER_EPOCH:
            use = np.isin(t["flag"], ["ok", "saturated"])   # bright star: only lower limits available
            lower_limit = True
        base = {"detector": det, "wavelength_um": detector_ranges[det], "units": "mJy"}
        points = [{"mjd": round(float(r["mjd"]), 5), "epoch": str(r["epoch"]), "wavelength_um": round(float(r["wavelength_um"]), 4),
                   "flux": round(float(r["flux"]), 5), "err": round(float(r["err"]), 5), "flux_corrected": None,
                   "flag": str(r["flag"])} for r in t]
        fit_rows = t[use]
        if len(fit_rows) >= 2:
            w = 1 / np.asarray(fit_rows["err"], float) ** 2
            combined_snr = float(np.sum(w * fit_rows["flux"]) / np.sqrt(np.sum(w)))
        else:
            combined_snr = 0.0
        if len(fit_rows) < 2 * MIN_POINTS_PER_EPOCH or combined_snr < MIN_COMBINED_SNR:
            curves.append({**base, "usable": False, "combined_snr": round(combined_snr, 1), "points": points,
                           "per_epoch": [], "sub_epochs": [],
                           "variability": {"significant": False, "systematic_floor": SYSTEMATIC_FLOOR,
                                           "note": "all exposures blended with another source in the aperture"
                                           if np.all(t["flag"] != "ok") and np.any(t["flag"] == "blended") else
                                           f"not enough usable exposures or target not detected "
                                           f"(combined S/N {combined_snr:.1f} < {MIN_COMBINED_SNR})"}})
            continue
        lam = np.asarray(fit_rows["wavelength_um"], float)
        flux = np.asarray(fit_rows["flux"], float)
        err = np.asarray(fit_rows["err"], float)
        ep = np.asarray(fit_rows["epoch"]).astype(str)
        shape, lam0, g = fit_shape_and_epochs(lam, flux, err, ep)
        s_all = shape(np.array([p["wavelength_um"] for p in points]))
        s0 = float(shape(np.array([lam0]))[0])
        used = set(np.flatnonzero(use))
        corrected = []
        for i, p in enumerate(points):
            if i in used and s_all[i] > 0:
                p["flux_corrected"] = round(p["flux"] / s_all[i] * s0, 5)
                corrected.append({**p, "err_corrected": p["err"] / s_all[i] * s0})
        per_epoch = [{"epoch": x["key"], "mjd": round(x["mjd"], 4), "flux": round(x["flux"], 5), "err": round(x["err"], 5),
                      "n": x["n"], "lower_limit": lower_limit}
                     for x in sorted(_group(corrected, lambda p: p["epoch"], MIN_POINTS_PER_EPOCH), key=lambda x: x["mjd"])]
        subs = []
        for e in sorted({p["epoch"] for p in corrected}):
            ps = [p for p in corrected if p["epoch"] == e]
            t0 = min(p["mjd"] for p in ps)
            if max(p["mjd"] for p in ps) - t0 < SUB_EPOCH_MIN_SPAN:
                continue
            for x in _group(ps, lambda p: int((p["mjd"] - t0) // SUB_EPOCH_DAYS), MIN_POINTS_PER_EPOCH):
                subs.append({"epoch": e, "bin": x["key"], "mjd": round(x["mjd"], 4), "flux": round(x["flux"], 5),
                             "err": round(x["err"], 5), "n": x["n"]})
        curves.append({**base, "usable": True, "combined_snr": round(combined_snr, 1), "reference_wavelength_um": round(lam0, 4),
                       "spectral_shape_bins": int(len(shape.centers)), "points": points, "per_epoch": per_epoch,
                       "sub_epochs": sorted(subs, key=lambda s: s["mjd"]), "variability": variability(per_epoch, lower_limit)})
    return curves
