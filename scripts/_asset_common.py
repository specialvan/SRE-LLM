"""Shared helpers for knowledge-base asset generation."""

from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.animation import PillowWriter

ASSET_DIR = Path(__file__).resolve().parent.parent / "docs" / "assets"
ASSET_DIR.mkdir(parents=True, exist_ok=True)

# Palette aligned with the Attention-Residuals knowledge base
COLOR_INK = "#1b2430"
COLOR_MUTE = "#6a7889"
COLOR_RULE = "#e5e0d5"
COLOR_BG_PANEL = "#fdfcf7"
COLOR_ACCENT = "#b4411b"          # SpaceX orange-red
COLOR_ACCENT_SOFT = "#f6e4db"
COLOR_KEY = "#1f5fa3"             # Blue — "after"
COLOR_KEY_SOFT = "#e0ecf8"
COLOR_GREEN = "#2f7d3a"
COLOR_WARN = "#caa96a"

# Default mpl rc so every figure looks consistent
plt.rcParams.update({
    "figure.facecolor": "#fbfaf7",
    "axes.facecolor":   "#ffffff",
    "axes.edgecolor":   COLOR_RULE,
    "axes.labelcolor":  COLOR_INK,
    "xtick.color":      COLOR_MUTE,
    "ytick.color":      COLOR_MUTE,
    "axes.spines.top":  False,
    "axes.spines.right": False,
    "font.size":        10.5,
    "font.family":      ["Microsoft YaHei", "DejaVu Sans"],
    "axes.unicode_minus": False,
    "axes.titlesize":   11.5,
    "axes.titleweight": "bold",
    "legend.frameon":   False,
    "figure.dpi":       110,
    "savefig.dpi":      110,
    "savefig.bbox":     "tight",
})


def save_png(fig, name: str) -> Path:
    path = ASSET_DIR / f"{name}.png"
    fig.savefig(path, dpi=130)
    plt.close(fig)
    return path


def save_gif(fig, update_fn, n_frames: int, name: str,
             fps: int = 12) -> Path:
    """Save a matplotlib animation as an optimised GIF."""
    path = ASSET_DIR / f"{name}.gif"
    writer = PillowWriter(fps=fps)
    with writer.saving(fig, str(path), dpi=100):
        for i in range(n_frames):
            update_fn(i)
            writer.grab_frame()
    plt.close(fig)
    return path
