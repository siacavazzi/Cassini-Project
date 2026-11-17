#!/usr/bin/env python3
"""The Moments window's mosaics stay mosaics: every pass of a Moments observation (web/replay/moments.csv) that the
windows draw as a mosaic or a mosaic movie (obs_mosaic.units: kind "mosaic" or "mosaic_movie") is still judged one.
A rule added after the judge (a ring strip played as a movie, _strip) once turned the 2009 Equinox mosaic
(116RI_EQXMOSAIC001) into a movie and nothing caught it (Sam 11-16). The list is the passes judged so on 2026-11-16
with the Equinox fix (#480); a pass that should change kind is taken off it on purpose.

Needs the archive index and the geometry cache (CASSINI_DATA, CASSINI_GEOMETRY_CACHE, as prebuild runs); without
them it says so and stops. Run: python web/test_moment_mosaics.py"""
import collections, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "frames"))

MOSAICS = [
    "DIONE_ISS_165DI_REGMAP001_PIE_N_0",
    "DIONE_ISS_165DI_REGMAP001_PIE_N_1",
    "DIONE_ISS_165DI_REGMAP001_PIE_N_2",
    "DIONE_ISS_165DI_REGMAP001_PIE_N_3",
    "DIONE_ISS_165DI_REGMAP001_PIE_W_0",
    "DIONE_ISS_221DI_REGMAP001_PIE_N_0",
    "DIONE_ISS_221DI_REGMAP001_PIE_N_2",
    "ENCELADUS_ISS_004EN_NGNPOL001_PRIME_N_0",
    "ENCELADUS_ISS_004EN_REGEO002_PRIME_N_0",
    "ENCELADUS_ISS_004EN_REGEO002_PRIME_N_1",
    "ENCELADUS_ISS_136EN_HIRES001_CIRS_N_0",
    "ENCELADUS_ISS_136EN_HIRES001_CIRS_N_1",
    "ENCELADUS_ISS_136EN_HIRES001_CIRS_N_5",
    "ENCELADUS_ISS_136EN_HIRES001_CIRS_N_6",
    "ENCELADUS_ISS_136EN_HIRES001_CIRS_N_7",
    "ENCELADUS_ISS_136EN_HIRES001_CIRS_N_8",
    "ENCELADUS_ISS_136EN_HIRES001_CIRS_N_9",
    "ENCELADUS_ISS_136EN_HIRES001_CIRS_W_0",
    "ENCELADUS_ISS_142EN_ORSCA001_PIE_N_0",
    "ENCELADUS_ISS_154EN_PLMHPHR001_PIE_N_3",
    "ENCELADUS_ISS_155EN_ENCEL002_PIE_N_0",
    "ENCELADUS_ISS_155EN_ENCEL002_PIE_N_1",
    "EPIMETHEUS_ISS_259EP_EPIMETHEU001_PIE_N_4",
    "IAPETUS_ISS_00BIA_GLOBCOLA001_PRIME_N_0",
    "IAPETUS_ISS_00CIA_LIMBTOPOD001_PRIME_N_0",
    "JUPITER_CIRS_C23JU_NSMAP101_PRIME_N_0",
    "JUPITER_ISS_C23JU_PORTRAIT_PRIME_N_0",
    "JUPITER_ISS_C23RI_RMOV001_PRIME_N_0",
    "JUPITER_ISS_C23RI_RMOV020_PRIME_N_0",
    "MIMAS_ISS_126MI_GEOLOG002_PRIME_N_0",
    "PANDORA_ISS_253PA_PANDORA001_PIE_N_2",
    "RHEA_ISS_049RH_CRESCENT001_PRIME_N_0",
    "RHEA_ISS_049RH_HIGHRES001_PRIME_N_0",
    "RHEA_ISS_049RH_HIGHRES001_PRIME_N_1",
    "RHEA_ISS_049RH_REGMAP001_PRIME_N_0",
    "RHEA_ISS_049RH_RHEA002_VIMS_N_0",
    "RHEA_ISS_049RH_RHEA002_VIMS_W_0",
    "RHEA_ISS_102RH_GEOLOG001_PRIME_N_0",
    "RHEA_ISS_102RH_GEOLOG002_PRIME_N_0",
    "SATURN_IOSIC_066RI_SHADULCAS001_SI_W_1",
    "SATURN_ISS_003SA_3X3MOVIEB001_PRIME_N_0",
    "SATURN_ISS_00ARI_RADCOLOR001_PRIME_N_0",
    "SATURN_ISS_00ASA_2X2MOVIEA001_PRIME_N_0",
    "SATURN_ISS_00BSA_CYLMAP002_VIMS_W_1",
    "SATURN_ISS_028RI_HIPHWAC001_PRIME_W_0",
    "SATURN_ISS_048SA_STRMOVIEC001_PRIME_N_0",
    "SATURN_ISS_116RI_EQXMOSAIC001_PRIME_W_0",
    "SATURN_ISS_132RI_PROPELLR001_PRIME_N_0",
    "SATURN_ISS_132RI_PROPELLR001_PRIME_W_0",
    "SATURN_ISS_146SA_HIRESGLOB001_PRIME_N_0",
    "SATURN_ISS_173RI_HIPHWAC001_PIE_W_0",
    "SATURN_ISS_175SA_NPOLMAP001_VIMS_W_0",
    "SATURN_ISS_181RI_HIPHASE001_VIMS_W_0",
    "SATURN_ISS_193SA_NPOLMOV001_VIMS_W_0",
    "SATURN_ISS_195RI_HIPHASEC001_VIMS_W_0",
    "SATURN_ISS_198SA_SATURN001_PRIME_W_0",
    "SATURN_ISS_221SA_EQUAMAP001_VIMS_W_0",
    "SATURN_ISS_251SA_NPOLMOV001_VIMS_W_0",
    "SATURN_ISS_260RI_HIPHASEFA001_PRIME_W_0",
    "SATURN_ISS_269RI_HIPHASEFB001_PIE_W_0",
    "SATURN_ISS_289SA_SHEMMAP001_VIMS_W_0",
    "SATURN_ISS_293SA_FAREWELL001_PRIME_W_0",
    "SATURN_ISS_293SA_IMPACTOBS001_VIMS_W_0",
    "TELESTO_ISS_016TL_MORPHO001_PRIME_N_0",
    "TETHYS_ISS_214TE_TETHYS001_PIE_N_0",
    "TITAN_ISS_003TI_FIRNADCMP002_CIRS_W_1",
    "TITAN_ISS_019TI_HDAC001_UVIS_W_2",
    "TITAN_ISS_122TI_GLOBMAPC001_PRIME_N_0",
    "TITAN_ISS_165TI_LRMONITOR001_PRIME_N_3",
    "TITAN_ISS_235TI_MONITORNA001_PRIME_N_0",
    "TITAN_ISS_292TI_CLOUD002_PIE_N_0",
]


def key(k):
    """(target, observation, camera, pass) of a pass name TARGET_OBSERVATION_CAMERA_PASS"""
    p = k.split("_")
    return p[0], "_".join(p[1:-2]), p[-2], int(p[-1])


def main():
    if not os.environ.get("CASSINI_DATA") or not os.environ.get("CASSINI_GEOMETRY_CACHE"):
        print("needs CASSINI_DATA and CASSINI_GEOMETRY_CACHE (the archive and its geometry): not run")
        return
    import obs_mosaic as om
    by = collections.defaultdict(list)
    for k in MOSAICS:
        t, o, c, n = key(k)
        by[(t, o, c)].append(n)
    bad = []
    for (t, o, c), ns in sorted(by.items()):
        us = {u["key"][3]: u for u in om.units(t, o, c)}
        for n in ns:
            u = us.get(n)
            if u is None or u["kind"] not in ("mosaic", "mosaic_movie"):
                bad.append((t, o, c, n, None if u is None else u["kind"]))
    assert not bad, f"Moments mosaics no longer mosaics: {bad}"
    print(f"{len(MOSAICS)} Moments mosaics of {len(by)} observations still mosaics: ok")


if __name__ == "__main__":
    main()
