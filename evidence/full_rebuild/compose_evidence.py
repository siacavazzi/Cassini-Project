# Builds the evidence images and summary.txt from render_evidence.py output. usage: compose_evidence.py RENDERS DEST
import os, sys, glob, numpy as np, cv2
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
src, dest = sys.argv[1], sys.argv[2]; os.makedirs(dest, exist_ok=True)
lines = []
def fit(img, width=1600):
    return cv2.resize(img, (width, int(img.shape[0] * width / img.shape[1])), interpolation=cv2.INTER_AREA) if img.shape[1] > width else img
def bar(text, width):
    b = np.full((50, width, 3), 255, np.uint8); cv2.putText(b, text, (10, 34), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 0), 2); return b
for old in sorted(glob.glob(f"{src}/*_old.png")):
    n = os.path.basename(old)[:-8]; a = cv2.imread(old); b = cv2.imread(f"{src}/{n}_new.png")
    d = np.abs(a.astype(int) - b.astype(int))
    mo, mn = a.reshape(-1, 3).mean(0)[::-1].round(1).tolist(), b.reshape(-1, 3).mean(0)[::-1].round(1).tolist()
    lo, ln = [len(np.unique(a[..., c])) for c in (2, 1, 0)], [len(np.unique(b[..., c])) for c in (2, 1, 0)]
    gap = np.full((a.shape[0], 16, 3), 255, np.uint8)
    pan = np.vstack([np.hstack([bar("OLD archive (cassiniprojectJAN05.zip)", a.shape[1]), np.full((50, 16, 3), 255, np.uint8), bar("NEW lut8 archive", b.shape[1])]), np.hstack([a, gap, b])])
    cv2.imwrite(f"{dest}/{n}_old_vs_new.png", fit(pan))
    lines.append(f"{n}: mean|diff| {d.mean():.2f}, max {d.max()}, pixels changed {(d.max(2) > 0).mean() * 100:.1f}%, mean RGB old {mo} new {mn}, levels RGB old {lo} new {ln}")
for one in sorted(glob.glob(f"{src}/*_single_new.png")):
    n = os.path.basename(one)[:-15]; a = cv2.imread(one)
    cv2.imwrite(f"{dest}/{n}_new_only.png", fit(np.vstack([bar("NEW lut8 archive only (not in the old archive)", a.shape[1]), a])))
    lines.append(f"{n}: new-only frame, mean {a.mean():.1f}, levels {len(np.unique(a[..., 0]))}")
for old in sorted(glob.glob(f"{src}/*_iof_old.npy")):
    n = os.path.basename(old)[:-12]; a = np.load(old); b = np.load(f"{src}/{n}_iof_new.npy")
    lo, hi = np.percentile(np.concatenate([a.ravel(), b.ravel()]), [0.5, 99.5])
    fig, ax = plt.subplots(1, 3, figsize=(16, 5.6))
    for i, (x, t) in enumerate(((a, "OLD archive: I/F"), (b, "NEW lut8 archive: I/F"))):
        im = ax[i].imshow(x, cmap="gray", vmin=lo, vmax=hi); ax[i].set_title(t); ax[i].axis("off"); fig.colorbar(im, ax=ax[i], fraction=0.046)
    bins = np.linspace(lo, hi, 300)
    ax[2].hist(a.ravel(), bins, histtype="step", label="old", color="#d55e00"); ax[2].hist(b.ravel(), bins, histtype="step", label="new", color="#0072b2")
    ax[2].set_yscale("log"); ax[2].set_xlabel("I/F"); ax[2].set_ylabel("pixels"); ax[2].legend(); ax[2].set_title("I/F histogram")
    fig.suptitle(n); fig.tight_layout(); fig.savefig(f"{dest}/{n}_iof_old_vs_new.png", dpi=100); plt.close(fig)
    r = (b[a > 0] / a[a > 0])
    lines.append(f"{n}: I/F old mean {a.mean():.5f} median {np.median(a):.5f}, new mean {b.mean():.5f} median {np.median(b):.5f}, "
                 f"distinct values old {len(np.unique(a))} new {len(np.unique(b))}, new/old ratio median {np.median(r):.4f}")
open(f"{dest}/summary.txt", "w").write("\n".join(lines) + "\n"); print("\n".join(lines))
