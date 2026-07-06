from pathlib import Path

import matplotlib as mpl

mpl.use("Agg")

# Column widths in inches, aligned with common IEEE/ACM two-column layouts.
COL_SINGLE = 3.3
COL_DOUBLE = 7.0

# Okabe-Ito color-blind safe palette.
OKABE_ITO = [
    "#000000",
    "#E69F00",
    "#56B4E9",
    "#009E73",
    "#F0E442",
    "#0072B2",
    "#D55E00",
    "#CC79A7",
]

mpl.rcParams.update(
    {
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
        "font.family": "serif",
        "font.serif": ["Times New Roman", "Nimbus Roman No9 L", "DejaVu Serif"],
        "font.size": 9,
        "axes.labelsize": 9,
        "axes.titlesize": 9,
        "xtick.labelsize": 8,
        "ytick.labelsize": 8,
        "legend.fontsize": 8,
        "axes.linewidth": 0.6,
        "lines.linewidth": 1.2,
        "lines.markersize": 4,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "legend.frameon": False,
        "figure.dpi": 150,
        "savefig.dpi": 300,
        "savefig.bbox": "tight",
        "savefig.pad_inches": 0.02,
    }
)

IMG_DIR = Path(__file__).resolve().parent


def save(fig, name):
    IMG_DIR.mkdir(parents=True, exist_ok=True)
    for ext in ("pdf", "png"):
        fig.savefig(IMG_DIR / f"{name}.{ext}")
