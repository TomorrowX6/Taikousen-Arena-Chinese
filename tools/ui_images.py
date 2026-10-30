"""Redraw the Japanese label baked into a UI texture with a Chinese one.

The text pixels are found in one of three ways:
  diff   - against the Korean twin (`<name>_kr`), which differs only where the text is
  plate  - inside `text_box`, everything that is not the colour of the plate behind the text
  bright - inside `text_box`, near-white pixels (white text on a patterned panel)
They are erased row by row from the neighbouring background (the plates and banners are built
from horizontal bands, so this keeps their edges straight), then the Chinese label is drawn in
the style of the original and centred where the Japanese text was.
"""
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

STYLES = {
    # gray page-title banners: blue italic text
    "title": dict(fill="sample", shear=0.22, height=1.0, width=1.15),
    # bottom navigation buttons: blue italic text with a thick white outline
    "nav": dict(fill="sample", stroke=0.16, stroke_fill=(255, 255, 255, 255), shear=0.22, height=1.25, width=1.2),
    # large battle-mode buttons: white text on a translucent patterned panel
    "panel": dict(fill=(255, 255, 255, 255), shear=0.18, height=1.3, width=0.95,
                  glow=(110, 190, 255, 170), glow_radius=0.05),
    # small two-line phase badges: white text with a soft blue glow
    "badge": dict(fill=(255, 255, 255, 255), shear=0.15, height=1.0, width=1.15,
                  glow=(70, 150, 255, 255), glow_radius=0.07),
    # plain labels inside windows
    "label": dict(fill="sample", shear=0.12, height=1.0, width=1.1),
}


def _dilate(mask, r):
    if r <= 0:
        return mask
    img = Image.fromarray(mask.astype(np.uint8) * 255)
    return np.asarray(img.filter(ImageFilter.MaxFilter(2 * r + 1))) > 0


def _box_mask(shape, box):
    m = np.zeros(shape[:2], bool)
    if box is None:
        m[:] = True
    else:
        m[box[1]:box[3], box[0]:box[2]] = True
    return m


def fill_rows(img, mask, direction="both"):
    """Replace masked pixels using the unmasked pixels of the same row."""
    out = img.astype(np.float32).copy()
    xs = np.arange(img.shape[1])
    for y in np.nonzero(mask.any(1))[0]:
        hole = mask[y]
        known = ~hole
        if not known.any():
            continue
        kx = xs[known]
        if direction == "right":
            idx = np.searchsorted(kx, xs[hole])
            idx = np.clip(idx, 0, len(kx) - 1)
            out[y, hole] = out[y, kx[idx]]
        else:
            for c in range(img.shape[2]):
                out[y, hole, c] = np.interp(xs[hole], kx, out[y, known, c])
    return out


def _icon_pixels(jp):
    """Saturated pixels whose hue is not the blue (~213 deg) of the label text."""
    rgb = jp[..., :3].astype(np.float32) / 255
    mx, mn = rgb.max(-1), rgb.min(-1)
    sat = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1e-6), 0)
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    d = np.maximum(mx - mn, 1e-6)
    hue = np.where(mx == r, (g - b) / d % 6, np.where(mx == g, (b - r) / d + 2, (r - g) / d + 4)) * 60
    return (sat > 0.4) & ((hue < 203) | (hue > 228)) & (jp[..., 3] > 200)


def find_mask(jp, kr, mode, text_box, threshold):
    area = _box_mask(jp.shape, text_box)
    if mode == "diff":
        diff = np.abs(jp.astype(np.int16) - kr.astype(np.int16)).max(-1) > threshold
        return diff & area
    if mode == "bright":
        return (jp[..., :3].min(-1) > threshold) & (jp[..., 3] > 150) & area
    if mode == "nav":
        # The plate is translucent white (alpha 230); text and its outline are opaque. Keep the
        # coloured icon (anything saturated that is not the blue of the text) and its outline.
        icon = _dilate(_icon_pixels(jp), 8)
        return (jp[..., 3] >= threshold) & area & ~icon
    if mode == "plate":
        opaque = area & (jp[..., 3] > 230)
        plate = np.median(jp[opaque][:, :3], axis=0)
        far = np.abs(jp[..., :3].astype(np.int16) - plate).max(-1) > threshold
        return far & (jp[..., 3] > 20) & area
    raise ValueError(mode)


def sample_text_color(jp, bg, mask):
    d = np.abs(jp.astype(np.float32) - bg).max(-1)
    sel = mask & (jp[..., 3] > 200)
    if sel.sum() < 5:
        return (255, 255, 255, 255)
    sel &= d >= np.percentile(d[sel], 75)
    return tuple(int(v) for v in np.median(jp[sel], axis=0))


def render_text(text, font_path, px, style):
    font = ImageFont.truetype(font_path, px)
    stroke = int(round(px * style.get("stroke", 0)))
    spacing = int(px * 0.1)
    probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    box = [int(round(v)) for v in probe.multiline_textbbox(
        (0, 0), text, font=font, spacing=spacing, align="center", stroke_width=stroke)]
    pad = px
    w, h = box[2] - box[0] + 2 * pad, box[3] - box[1] + 2 * pad
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(layer).multiline_text(
        (pad - box[0], pad - box[1]), text, font=font, fill=style["fill"], spacing=spacing, align="center",
        stroke_width=stroke, stroke_fill=style.get("stroke_fill"))
    if style.get("glow"):
        alpha = layer.getchannel("A").filter(ImageFilter.GaussianBlur(px * style["glow_radius"]))
        glow = Image.new("RGBA", layer.size, style["glow"])
        glow.putalpha(alpha.point(lambda a: min(255, a * 2)))
        layer = Image.alpha_composite(glow, layer)
    shear = style.get("shear", 0)
    if shear:
        extra = int(abs(shear) * h)
        layer = layer.transform((w + extra, h), Image.AFFINE, (1, shear, -shear * h, 0, 1, 0), Image.BICUBIC)
    bbox = layer.getbbox()
    return layer.crop(bbox) if bbox else layer


def _draw(out, text, style, font_path, fit_box, offset=(0, 0)):
    bw, bh = fit_box[2] - fit_box[0], fit_box[3] - fit_box[1]
    lines = text.count("\n") + 1
    label = render_text(text, font_path, max(16, int(bh / lines * 4)), style)
    scale = min(bh * style["height"] / label.height, bw * style["width"] / label.width)
    label = label.resize((max(1, round(label.width * scale)), max(1, round(label.height * scale))), Image.LANCZOS)
    cx = (fit_box[0] + fit_box[2]) / 2 + offset[0]
    cy = (fit_box[1] + fit_box[3]) / 2 + offset[1]
    layer = Image.new("RGBA", out.size, (0, 0, 0, 0))
    layer.paste(label, (round(cx - label.width / 2), round(cy - label.height / 2)), label)
    return Image.alpha_composite(out, layer)


def _draw_ring(out, ring, ss=4):
    """Redraw a ring icon (part of it was hidden under the Japanese text)."""
    (cx, cy), (r_in, r_out), o = ring["center"], ring["r"], ring["outline"]
    size = (out.width * ss, out.height * ss)
    for r0, r1, color in ((r_in - o, r_out + o, (255, 255, 255, 255)), (r_in, r_out, tuple(ring["color"]))):
        layer = Image.new("RGBA", size, (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        d.ellipse([(cx - r1) * ss, (cy - r1) * ss, (cx + r1) * ss, (cy + r1) * ss], fill=color)
        d.ellipse([(cx - r0) * ss, (cy - r0) * ss, (cx + r0) * ss, (cy + r0) * ss], fill=(0, 0, 0, 0))
        out = Image.alpha_composite(out, layer.resize(out.size, Image.LANCZOS))
    return out


def relabel(jp_img, spec, font_path, kr_img=None):
    """Return a copy of `jp_img` with its label(s) replaced as described by `spec`.

    spec keys: text | items[{text, fit_box}], style, mask (diff|nav|plate|bright), text_box,
    threshold, grow, fill (both|right), fit_box, offset, glow.
    """
    style = dict(STYLES[spec["style"]])
    if "glow" in spec:
        style["glow"] = tuple(spec["glow"])
    mode = spec.get("mask", "diff")
    jp = np.asarray(jp_img.convert("RGBA"))
    kr = np.asarray(kr_img.convert("RGBA")) if kr_img is not None else None
    if mode == "diff" and (kr is None or kr.shape != jp.shape):
        raise ValueError("diff mask needs a Korean twin of the same size")
    text_box = spec.get("text_box")
    mask = find_mask(jp, kr, mode, text_box, spec.get("threshold", 24 if mode == "diff" else 12))
    if mask.sum() < 10:
        raise ValueError("no text found")
    hole = _dilate(mask, spec.get("grow", 2)) & _box_mask(jp.shape, text_box)
    bg = fill_rows(jp, hole, spec.get("fill", "both"))
    # where the Japanese text itself is (the diff mask also covers the Korean text)
    jp_text = hole & (np.abs(jp.astype(np.float32) - bg).max(-1) > 30)
    core = jp_text
    if style["fill"] == "sample":
        style["fill"] = sample_text_color(jp, bg, jp_text)
        near = np.abs(jp.astype(np.int16) - np.array(style["fill"], np.int16)).max(-1) < 50
        if (jp_text & near).sum() > 20:
            core = jp_text & near  # the glyphs without their outline
    out = Image.fromarray(np.clip(bg, 0, 255).astype(np.uint8), "RGBA")
    for ring in spec.get("rings", ()):
        out = _draw_ring(out, ring)
    items = spec.get("items") or [{"text": spec["text"], "fit_box": spec.get("fit_box")}]
    for item in items:
        fit_box = item.get("fit_box")
        if fit_box is None:
            ys, xs = np.nonzero(core if core.sum() > 20 else mask)
            fit_box = (xs.min(), ys.min(), xs.max() + 1, ys.max() + 1)
        out = _draw(out, item["text"], style, font_path, fit_box, item.get("offset", spec.get("offset", (0, 0))))
    return out
