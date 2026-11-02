"""
uml.py - Small drawing toolkit (matplotlib) for UML and DFD notation.
Coordinates are in abstract "units"; 1 unit = U inches in the saved PNG.
"""
import math

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Circle, Ellipse, FancyBboxPatch, Polygon, Rectangle  # noqa: E402

U = 0.55
FONT = 11
INK = "#1d2420"
FILL = "#fdfdf8"
HEAD = "#e4efe8"
ACCENT = "#1f7a4d"


def canvas(w, h, title=None, u=U):
    fig = plt.figure(figsize=(w * u, h * u))
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, w)
    ax.set_ylim(0, h)
    ax.axis("off")
    ax.set_aspect("equal")
    if title:
        ax.text(w / 2, h - 0.45, title, ha="center", va="center", fontsize=FONT + 4, fontweight="bold", color=INK)
    return fig, ax


def save(fig, path):
    fig.savefig(path, dpi=200, facecolor="white", bbox_inches="tight", pad_inches=0.25)
    plt.close(fig)


def text(ax, x, y, s, size=FONT, bg=False, **kw):
    opts = dict(ha="center", va="center", fontsize=size, color=INK, zorder=6)
    opts.update(kw)
    if bg:
        opts["bbox"] = dict(boxstyle="round,pad=0.15", fc="white", ec="none", alpha=0.95)
    return ax.text(x, y, s, **opts)


# ---------------------------------------------------------------- geometry
def ellipse_edge(cx, cy, a, b, tx, ty):
    dx, dy = tx - cx, ty - cy
    t = 1 / math.sqrt((dx / a) ** 2 + (dy / b) ** 2)
    return cx + dx * t, cy + dy * t


def circle_edge(cx, cy, r, tx, ty):
    d = math.hypot(tx - cx, ty - cy)
    return cx + (tx - cx) * r / d, cy + (ty - cy) * r / d


def rect_edge(x0, y0, x1, y1, tx, ty):
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    dx, dy = tx - cx, ty - cy
    sx = (x1 - x0) / 2 / abs(dx) if dx else math.inf
    sy = (y1 - y0) / 2 / abs(dy) if dy else math.inf
    s = min(sx, sy)
    return cx + dx * s, cy + dy * s


# ---------------------------------------------------------------- connectors
def arrow(ax, p, q, head="filled", dashed=False, lw=1.3, color=INK, z=3):
    """Straight connector p -> q. head: filled | open | none | hollow (generalization) | diamond (composition at p)."""
    ls = (0, (5, 3)) if dashed else "-"
    if head in ("filled", "open"):
        style = "-|>" if head == "filled" else "->"
        ax.annotate("", xy=q, xytext=p, zorder=z,
                    arrowprops=dict(arrowstyle=style, color=color, lw=lw, linestyle=ls,
                                    shrinkA=0, shrinkB=0, mutation_scale=16))
    elif head == "hollow":
        ang = math.atan2(q[1] - p[1], q[0] - p[0])
        L, Wd = 0.42, 0.26
        base = (q[0] - L * math.cos(ang), q[1] - L * math.sin(ang))
        ax.plot([p[0], base[0]], [p[1], base[1]], color=color, lw=lw, linestyle=ls, zorder=z)
        left = (base[0] + Wd * math.sin(ang), base[1] - Wd * math.cos(ang))
        right = (base[0] - Wd * math.sin(ang), base[1] + Wd * math.cos(ang))
        ax.add_patch(Polygon([q, left, right], closed=True, fc="white", ec=color, lw=lw, zorder=z + 1))
    else:
        ax.plot([p[0], q[0]], [p[1], q[1]], color=color, lw=lw, linestyle=ls, zorder=z)


def polyline(ax, pts, head="filled", dashed=False, lw=1.3, color=INK):
    for a, b in zip(pts[:-2], pts[1:-1]):
        arrow(ax, a, b, head="none", dashed=dashed, lw=lw, color=color)
    arrow(ax, pts[-2], pts[-1], head=head, dashed=dashed, lw=lw, color=color)


def diamond(ax, p, toward, filled=True, color=INK):
    """Composition (filled) / aggregation (hollow) diamond sitting at p, pointing away from `toward`."""
    ang = math.atan2(toward[1] - p[1], toward[0] - p[0])
    L, Wd = 0.5, 0.2
    tip2 = (p[0] + L * math.cos(ang), p[1] + L * math.sin(ang))
    mid = (p[0] + L / 2 * math.cos(ang), p[1] + L / 2 * math.sin(ang))
    s1 = (mid[0] + Wd * math.sin(ang), mid[1] - Wd * math.cos(ang))
    s2 = (mid[0] - Wd * math.sin(ang), mid[1] + Wd * math.cos(ang))
    ax.add_patch(Polygon([p, s1, tip2, s2], closed=True, fc=color if filled else "white", ec=color, lw=1.3, zorder=5))
    return tip2


# ---------------------------------------------------------------- UML shapes
def actor(ax, x, y, label, size=FONT):
    """Stick figure whose feet are at (x, y); label below."""
    ax.add_patch(Circle((x, y + 1.25), 0.25, fc="white", ec=INK, lw=1.5, zorder=4))
    kw = dict(color=INK, lw=1.5, zorder=4)
    ax.plot([x, x], [y + 1.0, y + 0.45], **kw)
    ax.plot([x - 0.4, x + 0.4], [y + 0.8, y + 0.8], **kw)
    ax.plot([x, x - 0.32], [y + 0.45, y], **kw)
    ax.plot([x, x + 0.32], [y + 0.45, y], **kw)
    text(ax, x, y - 0.35, label, size=size, va="top", fontweight="bold")
    return {"x": x, "y": y, "top": (x, y + 1.5), "mid": (x, y + 0.8)}


def usecase(ax, x, y, label, w=3.4, h=1.0, size=FONT - 0.5):
    ax.add_patch(Ellipse((x, y), w, h, fc=FILL, ec=INK, lw=1.3, zorder=4))
    text(ax, x, y, label, size=size)
    return {"c": (x, y), "a": w / 2, "b": h / 2}


def uc_edge(uc, toward):
    return ellipse_edge(uc["c"][0], uc["c"][1], uc["a"], uc["b"], *toward)


def uml_class(ax, x, ytop, w, name, attrs, methods, stereo=None, lh=0.38, size=FONT - 1):
    head_h = lh * (2 if stereo else 1) + 0.25
    attr_h = lh * max(len(attrs), 1) + 0.2
    meth_h = lh * max(len(methods), 1) + 0.2
    y0 = ytop - head_h - attr_h - meth_h
    ax.add_patch(Rectangle((x, y0), w, ytop - y0, fc=FILL, ec=INK, lw=1.4, zorder=4))
    ax.add_patch(Rectangle((x, ytop - head_h), w, head_h, fc=HEAD, ec=INK, lw=1.4, zorder=4))
    ax.plot([x, x + w], [ytop - head_h - attr_h] * 2, color=INK, lw=1.2, zorder=5)
    cy = ytop - head_h / 2
    if stereo:
        text(ax, x + w / 2, cy + lh / 2, f"«{stereo}»", size=size - 0.5, style="italic")
        cy -= lh / 2
    text(ax, x + w / 2, cy, name, size=size + 0.5, fontweight="bold", style="italic" if stereo == "abstract" else "normal")
    for i, a in enumerate(attrs):
        text(ax, x + 0.15, ytop - head_h - 0.1 - lh * (i + 0.5), a, size=size, ha="left", family="monospace")
    for i, m in enumerate(methods):
        text(ax, x + 0.15, ytop - head_h - attr_h - 0.1 - lh * (i + 0.5), m, size=size, ha="left", family="monospace")
    return {"x0": x, "x1": x + w, "y0": y0, "y1": ytop, "cx": x + w / 2, "cy": (y0 + ytop) / 2}


def state(ax, x, y, label, w=3.0, h=1.1, size=FONT):
    ax.add_patch(FancyBboxPatch((x - w / 2, y - h / 2), w, h, boxstyle="round,pad=0,rounding_size=0.35",
                                fc=FILL, ec=INK, lw=1.5, zorder=4))
    text(ax, x, y, label, size=size, fontweight="bold")
    return {"x0": x - w / 2, "x1": x + w / 2, "y0": y - h / 2, "y1": y + h / 2, "c": (x, y)}


def initial(ax, x, y, r=0.28):
    ax.add_patch(Circle((x, y), r, fc=INK, ec=INK, zorder=4))
    return {"c": (x, y), "r": r}


def final(ax, x, y, r=0.32):
    ax.add_patch(Circle((x, y), r, fc="white", ec=INK, lw=1.6, zorder=4))
    ax.add_patch(Circle((x, y), r * 0.6, fc=INK, ec=INK, zorder=5))
    return {"c": (x, y), "r": r}


# ---------------------------------------------------------------- DFD shapes
def process(ax, x, y, num, label, r=1.25, size=FONT - 0.5):
    ax.add_patch(Circle((x, y), r, fc=HEAD, ec=INK, lw=1.5, zorder=4))
    ax.plot([x - r * 0.82, x + r * 0.82], [y + r * 0.45] * 2, color=INK, lw=1, zorder=5)
    text(ax, x, y + r * 0.68, num, size=size, fontweight="bold")
    text(ax, x, y - r * 0.12, label, size=size)
    return {"c": (x, y), "r": r}


def entity(ax, x, y, label, w=3.2, h=1.2, size=FONT):
    ax.add_patch(Rectangle((x - w / 2, y - h / 2), w, h, fc="white", ec=INK, lw=1.8, zorder=4))
    text(ax, x, y, label, size=size, fontweight="bold")
    return {"x0": x - w / 2, "x1": x + w / 2, "y0": y - h / 2, "y1": y + h / 2, "c": (x, y)}


def datastore(ax, x, y, ident, label, w=3.4, h=0.75, size=FONT - 1):
    x0, x1, y0, y1 = x - w / 2, x + w / 2, y - h / 2, y + h / 2
    ax.add_patch(Rectangle((x0, y0), w, h, fc=FILL, ec="none", zorder=4))
    kw = dict(color=INK, lw=1.5, zorder=5)
    ax.plot([x0, x1], [y1, y1], **kw)
    ax.plot([x0, x1], [y0, y0], **kw)
    ax.plot([x0, x0], [y0, y1], **kw)
    ax.plot([x0 + 0.7, x0 + 0.7], [y0, y1], **kw)
    text(ax, x0 + 0.35, y, ident, size=size, fontweight="bold")
    text(ax, x0 + 0.7 + (w - 0.7) / 2, y, label, size=size)
    return {"x0": x0, "x1": x1, "y0": y0, "y1": y1, "c": (x, y)}


def edge(shape, toward):
    """Boundary point of any shape dict in the direction of `toward`."""
    if "r" in shape:
        return circle_edge(*shape["c"], shape["r"], *toward)
    if "a" in shape:
        return uc_edge(shape, toward)
    return rect_edge(shape["x0"], shape["y0"], shape["x1"], shape["y1"], *toward)


def exit_point(shape, p, u):
    """Where a ray starting inside `shape` at p, heading along unit vector u, leaves the shape."""
    if "r" in shape:
        cx, cy = shape["c"]
        dx, dy = p[0] - cx, p[1] - cy
        b = dx * u[0] + dy * u[1]
        c = dx * dx + dy * dy - shape["r"] ** 2
        t = -b + math.sqrt(max(b * b - c, 0))
    elif "a" in shape:
        return edge(shape, (p[0] + u[0] * 100, p[1] + u[1] * 100))
    else:
        tx = ((shape["x1"] - p[0]) / u[0] if u[0] > 0 else (shape["x0"] - p[0]) / u[0]) if u[0] else math.inf
        ty = ((shape["y1"] - p[1]) / u[1] if u[1] > 0 else (shape["y0"] - p[1]) / u[1]) if u[1] else math.inf
        t = min(tx, ty)
    return p[0] + u[0] * t, p[1] + u[1] * t


def flow(ax, a, b, label=None, offset=0.0, lpos=0.5, lw=1.3, size=FONT - 1.5, head="filled", dashed=False,
         loff=0.0):
    """
    Labelled arrow between two shapes. `offset` shifts the arrow sideways so two-way flows don't overlap;
    `loff` moves the label sideways off the arrow.
    """
    ca = a["c"] if "c" in a else ((a["x0"] + a["x1"]) / 2, (a["y0"] + a["y1"]) / 2)
    cb = b["c"] if "c" in b else ((b["x0"] + b["x1"]) / 2, (b["y0"] + b["y1"]) / 2)
    ang = math.atan2(cb[1] - ca[1], cb[0] - ca[0])
    ox, oy = -math.sin(ang) * offset, math.cos(ang) * offset
    u = (math.cos(ang), math.sin(ang))
    p = exit_point(a, (ca[0] + ox, ca[1] + oy), u)
    q = exit_point(b, (cb[0] + ox, cb[1] + oy), (-u[0], -u[1]))
    arrow(ax, p, q, head=head, dashed=dashed, lw=lw)
    if label:
        mx, my = p[0] + (q[0] - p[0]) * lpos, p[1] + (q[1] - p[1]) * lpos
        text(ax, mx - math.sin(ang) * loff, my + math.cos(ang) * loff, label, size=size, bg=True)
    return p, q
