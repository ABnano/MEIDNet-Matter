"""
Minimal inline-SVG charts for the HTML reports (no JavaScript, no internet needed).

Colours are CSS classes defined in the report stylesheet, so charts follow the
reader's light/dark theme.  Every chart has a <title> for screen readers.
"""
from __future__ import annotations

import html
import math

import numpy as np


def _esc(s) -> str:
    return html.escape(str(s))


def _nice(lo, hi):
    if not np.isfinite(lo) or not np.isfinite(hi):
        return 0.0, 1.0
    if hi - lo < 1e-12:
        lo, hi = lo - 0.5, hi + 0.5
    pad = 0.04 * (hi - lo)
    return lo - pad, hi + pad


def _ticks(lo, hi, n=5):
    span = hi - lo
    step = 10 ** math.floor(math.log10(span / n)) if span > 0 else 1
    for m in (1, 2, 2.5, 5, 10):
        if span / (step * m) <= n:
            step *= m
            break
    start = math.ceil(lo / step) * step
    out = []
    v = start
    while v <= hi + 1e-12:
        out.append(round(v, 10))
        v += step
    return out


def _fmt(v):
    if abs(v) >= 1e6 or (abs(v) < 0.01 and v != 0):
        return f"{v:.2g}"
    if abs(v) >= 1000:              # axis counts read 1,000 and 1,500 rather than 1e+03 and 1.5e+03
        return f"{v:,.0f}"
    return f"{v:.3g}"


class Frame:
    def __init__(self, w=420, h=280, xlo=0.0, xhi=1.0, ylo=0.0, yhi=1.0, ml=52, mr=14, mt=14, mb=42):
        self.w, self.h, self.ml, self.mr, self.mt, self.mb = w, h, ml, mr, mt, mb
        self.xlo, self.xhi, self.ylo, self.yhi = xlo, xhi, ylo, yhi

    def x(self, v):
        return self.ml + (v - self.xlo) / (self.xhi - self.xlo) * (self.w - self.ml - self.mr)

    def y(self, v):
        return self.h - self.mb - (v - self.ylo) / (self.yhi - self.ylo) * (self.h - self.mt - self.mb)

    def axes(self, xlabel="", ylabel="", xticks=True, yticks=True):
        p = [f'<line class="ax" x1="{self.ml}" y1="{self.h - self.mb}" x2="{self.w - self.mr}" y2="{self.h - self.mb}"/>',
             f'<line class="ax" x1="{self.ml}" y1="{self.mt}" x2="{self.ml}" y2="{self.h - self.mb}"/>']
        if xticks:
            for t in _ticks(self.xlo, self.xhi):
                X = self.x(t)
                p.append(f'<line class="grid" x1="{X:.1f}" y1="{self.mt}" x2="{X:.1f}" y2="{self.h - self.mb}"/>')
                p.append(f'<text class="tick" x="{X:.1f}" y="{self.h - self.mb + 15}" text-anchor="middle">{_fmt(t)}</text>')
        if yticks:
            for t in _ticks(self.ylo, self.yhi):
                Y = self.y(t)
                p.append(f'<line class="grid" x1="{self.ml}" y1="{Y:.1f}" x2="{self.w - self.mr}" y2="{Y:.1f}"/>')
                p.append(f'<text class="tick" x="{self.ml - 6}" y="{Y + 4:.1f}" text-anchor="end">{_fmt(t)}</text>')
        if xlabel:
            p.append(f'<text class="lab" x="{(self.ml + self.w - self.mr) / 2:.1f}" y="{self.h - 6}" text-anchor="middle">{_esc(xlabel)}</text>')
        if ylabel:
            p.append(f'<text class="lab" transform="translate(13,{(self.mt + self.h - self.mb) / 2:.1f}) rotate(-90)" text-anchor="middle">{_esc(ylabel)}</text>')
        return "".join(p)

    def wrap(self, body, title):
        return (f'<svg class="chart" viewBox="0 0 {self.w} {self.h}" role="img" preserveAspectRatio="xMidYMid meet">'
                f"<title>{_esc(title)}</title>{body}</svg>")


def histogram(values, title, xlabel, bins=30, marks=None, window=None, w=420, h=230):
    """Distribution of a property; ``marks`` = {label: value} draws vertical target lines; ``window`` shades a range."""
    v = np.asarray(values, dtype=float)
    v = v[np.isfinite(v)]
    if len(v) == 0:
        return "<p class='muted'>no data</p>"
    lo, hi = float(v.min()), float(v.max())
    for m in (marks or {}).values():
        lo, hi = min(lo, m), max(hi, m)
    lo, hi = _nice(lo, hi)
    counts, edges = np.histogram(v, bins=bins, range=(lo, hi))
    f = Frame(w, h, lo, hi, 0, max(1, counts.max()) * 1.08)
    body = []
    if window:
        a = f.x(max(lo, window[0] if window[0] is not None else lo))
        b = f.x(min(hi, window[1] if window[1] is not None else hi))
        body.append(f'<rect class="win" x="{a:.1f}" y="{f.mt}" width="{max(0, b - a):.1f}" height="{h - f.mt - f.mb}"/>')
    body.append(f.axes(xlabel, "count"))
    for c, a, b in zip(counts, edges[:-1], edges[1:]):
        if c:
            body.append(f'<rect class="bar" x="{f.x(a) + 0.5:.1f}" y="{f.y(c):.1f}" width="{max(0.5, f.x(b) - f.x(a) - 1):.1f}" '
                        f'height="{f.y(0) - f.y(c):.1f}"><title>{_fmt(a)}–{_fmt(b)}: {c}</title></rect>')
    for i, (lab, m) in enumerate((marks or {}).items()):
        X = f.x(m)
        body.append(f'<line class="mark" x1="{X:.1f}" y1="{f.mt}" x2="{X:.1f}" y2="{h - f.mb}"/>'
                    f'<text class="marklab" x="{X + 4:.1f}" y="{f.mt + 12 + 12 * i}">{_esc(lab)}</text>')
    return f.wrap("".join(body), title)


def hbars(items, title, value_fmt="{:,}", w=420, bar_class="bar", max_items=14):
    """Horizontal bar chart of (label, value) pairs, largest first."""
    items = sorted(items, key=lambda kv: -kv[1])[:max_items]
    if not items:
        return "<p class='muted'>nothing to show</p>"
    row = 22
    h = 10 + row * len(items)
    ml = 10 + 7 * max(len(str(k)) for k, _ in items)
    ml = min(ml, 230)
    vmax = max(v for _, v in items) or 1
    body = []
    for i, (k, v) in enumerate(items):
        y = 6 + i * row
        width = (w - ml - 70) * v / vmax
        body.append(f'<text class="tick" x="{ml - 6}" y="{y + 14}" text-anchor="end">{_esc(k)}</text>'
                    f'<rect class="{bar_class}" x="{ml}" y="{y + 3}" width="{max(1, width):.1f}" height="{row - 8}"/>'
                    f'<text class="val" x="{ml + width + 5:.1f}" y="{y + 14}">{_esc(value_fmt.format(v))}</text>')
    return f'<svg class="chart" viewBox="0 0 {w} {h}" role="img"><title>{_esc(title)}</title>{"".join(body)}</svg>'


def scatter(x, y, title, xlabel, ylabel, diagonal=False, highlight=None, labels=None, w=420, h=320, classes=None):
    x = np.asarray(x, float)
    y = np.asarray(y, float)
    ok = np.isfinite(x) & np.isfinite(y)
    if not ok.any():
        return "<p class='muted'>no data</p>"
    if diagonal:
        lo, hi = _nice(min(x[ok].min(), y[ok].min()), max(x[ok].max(), y[ok].max()))
        f = Frame(w, h, lo, hi, lo, hi)
    else:
        xl, xh = _nice(x[ok].min(), x[ok].max())
        yl, yh = _nice(y[ok].min(), y[ok].max())
        if highlight:
            for hx, hy, _ in highlight:
                xl, xh = min(xl, hx), max(xh, hx)
                yl, yh = min(yl, hy), max(yh, hy)
            xl, xh = _nice(xl, xh)
            yl, yh = _nice(yl, yh)
        f = Frame(w, h, xl, xh, yl, yh)
    body = [f.axes(xlabel, ylabel)]
    if diagonal:
        body.append(f'<line class="mark" x1="{f.x(f.xlo):.1f}" y1="{f.y(f.ylo):.1f}" x2="{f.x(f.xhi):.1f}" y2="{f.y(f.yhi):.1f}"/>')
    idx = np.where(ok)[0]
    if len(idx) > 3000:
        idx = np.random.RandomState(0).choice(idx, 3000, replace=False)
    for i in idx:
        cls = classes[i] if classes is not None else "pt"
        tip = f"<title>{_esc(labels[i])}</title>" if labels is not None else ""
        body.append(f'<circle class="{cls}" cx="{f.x(x[i]):.1f}" cy="{f.y(y[i]):.1f}" r="2.6">{tip}</circle>')
    for hx, hy, lab in highlight or []:
        body.append(f'<path class="star" d="M{f.x(hx):.1f},{f.y(hy) - 7:.1f} l2,5 5,0 -4,3 2,5 -5,-3 -5,3 2,-5 -4,-3 5,0z">'
                    f'<title>{_esc(lab)}</title></path>')
    return f.wrap("".join(body), title)


def lines(series: dict, title, xlabel, ylabel, w=420, h=250, log=False):
    """``series`` = {name: (xs, ys)}; up to 5 series, each with its own class s0..s4."""
    xs_all = np.concatenate([np.asarray(v[0], float) for v in series.values()])
    ys_all = np.concatenate([np.asarray(v[1], float) for v in series.values()])
    ok = np.isfinite(ys_all) & ((ys_all > 0) if log else True)
    if not ok.any():
        return "<p class='muted'>no data</p>"
    tr = (lambda v: np.log10(np.maximum(v, 1e-12))) if log else (lambda v: v)
    xl, xh = _nice(xs_all.min(), xs_all.max())
    yl, yh = _nice(tr(ys_all[ok]).min(), tr(ys_all[ok]).max())
    f = Frame(w, h, xl, xh, yl, yh)
    body = [f.axes(xlabel, ylabel + (" (log10)" if log else ""))]
    for k, (name, (xs, ys)) in enumerate(series.items()):
        pts = " ".join(f"{f.x(a):.1f},{f.y(tr(b)):.1f}" for a, b in zip(xs, ys) if np.isfinite(b) and (b > 0 or not log))
        body.append(f'<polyline class="s{k % 5}" fill="none" points="{pts}"/>')
        body.append(f'<text class="leg s{k % 5}t" x="{f.ml + 8}" y="{f.mt + 12 + 13 * k}">{_esc(name)}</text>')
    return f.wrap("".join(body), title)


def funnel(stages, title, w=560):
    """``stages`` = [(label, count, note)], drawn as shrinking bars."""
    row = 34
    h = 8 + row * len(stages)
    top = max(c for _, c, _ in stages) or 1
    body = []
    for i, (lab, c, note) in enumerate(stages):
        width = max(2, (w - 250) * c / top)
        y = 4 + i * row
        body.append(f'<text class="tick" x="8" y="{y + 19}">{_esc(lab)}</text>'
                    f'<rect class="{"ok" if i == len(stages) - 1 else "bar"}" x="200" y="{y + 5}" width="{width:.1f}" height="{row - 12}"/>'
                    f'<text class="val" x="{200 + width + 6:.1f}" y="{y + 19}">{c:,}{(" · " + _esc(note)) if note else ""}</text>')
    return f'<svg class="chart wide" viewBox="0 0 {w} {h}" role="img"><title>{_esc(title)}</title>{"".join(body)}</svg>'


def target_bar(label, value, target, lo, hi, kind="l2", w=300, unit=""):
    """A tiny gauge: training range as a track, target as a tick, prediction as a dot."""
    lo2, hi2 = _nice(min(lo, value, target), max(hi, value, target))
    f = Frame(w, 34, lo2, hi2, 0, 1, ml=6, mr=6, mt=4, mb=4)
    a, b = f.x(lo), f.x(hi)
    body = (f'<rect class="track" x="{a:.1f}" y="13" width="{max(1, b - a):.1f}" height="8" rx="4"/>'
            f'<line class="mark" x1="{f.x(target):.1f}" y1="6" x2="{f.x(target):.1f}" y2="28"/>'
            f'<circle class="dot" cx="{f.x(value):.1f}" cy="17" r="5.5"/>')
    unit = _esc(unit)
    return (f'<svg class="gauge" viewBox="0 0 {w} 34" role="img"><title>{_esc(label)}: predicted {value:.3g}{unit}, '
            f'target {target:.3g}{unit}, training range {lo:.3g}–{hi:.3g}</title>{body}</svg>')
