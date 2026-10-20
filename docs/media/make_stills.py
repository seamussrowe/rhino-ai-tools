"""Build the README stills and the GitHub social preview from the original NIST FTC-08 images.

    python make_stills.py <folder with "STEP vs GH2 rebuild.png" and "canvas_overview.png">

Writes step-vs-gh2.png, gh2-canvas.png and social-preview.png next to this script.
"""
import os
import sys

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))


def font(size, bold=False):
    for name in (("segoeuib.ttf", "arialbd.ttf") if bold else ("segoeui.ttf", "arial.ttf")):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    return ImageFont.load_default(size)


def main(src):
    grid = Image.open(os.path.join(src, "STEP vs GH2 rebuild.png")).convert("RGB")   # 2200x1608, 2x2
    w, h = grid.size
    top = grid.crop((0, 0, w, h // 2))
    top.save(os.path.join(HERE, "step-vs-gh2.png"), optimize=True)

    canvas = Image.open(os.path.join(src, "canvas_overview.png")).convert("RGB")      # 1800x2895
    canvas.crop((0, 0, canvas.width, 1300)).save(os.path.join(HERE, "gh2-canvas.png"), optimize=True)

    # social preview 1280x640: STEP (left) | GH2 rebuild (right), caption band at the bottom
    band = 150
    label_h = 50                                     # skip the labels drawn on the source image
    halves = [top.crop((0, label_h, w // 2, h // 2)), top.crop((w // 2, label_h, w, h // 2))]
    out = Image.new("RGB", (1280, 640), (24, 26, 30))
    for i, im in enumerate(halves):
        tw, th = 640, 640 - band
        s = max(tw / im.width, th / im.height)
        im = im.resize((round(im.width * s), round(im.height * s)), Image.LANCZOS)
        x0, y0 = (im.width - tw) // 2, (im.height - th) // 2
        out.paste(im.crop((x0, y0, x0 + tw, y0 + th)), (i * 640, 0))
    d = ImageDraw.Draw(out)
    d.line((640, 0, 640, 640 - band), fill=(24, 26, 30), width=4)
    for x, text in ((24, "Imported STEP"), (664, "Parametric Grasshopper 2 rebuild")):
        d.text((x, 18), text, font=font(30, True), fill=(20, 20, 20))
    d.text((40, 640 - band + 22), "247 / 247 faces  ·  max deviation 0.0019 mm", font=font(46, True), fill=(255, 255, 255))
    d.text((40, 640 - band + 86), "rhino-ai-tools: Claude + Rhino MCP + Grasshopper 2", font=font(30), fill=(170, 176, 186))
    out.save(os.path.join(HERE, "social-preview.png"), optimize=True)


if __name__ == "__main__":
    main(sys.argv[1])
