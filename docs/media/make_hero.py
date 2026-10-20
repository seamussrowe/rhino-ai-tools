"""Compose the README hero animation from viewport captures and encode it as GIF + MP4.

    python make_hero.py <frames folder>

The frames come from Rhino 9 over the Rhino MCP (CaptureToBitmap at 1200x675, Shaded):
  b1_###.png   imported STEP, orbiting
  b2s_###.png  / b2g_###.png   STEP and GH2 rebuild from the same cameras (cross-faded here)
  b3a_###.png  camera moves in to the square hole; the last frames show the FeatureContext pick
  b3b_###.png  live GH2 solves while SquareSize goes 1.1 -> 1.5 (every solve checked: 247 faces, valid solid)
Writes hero.gif and hero.mp4 next to this script. Needs Pillow and ffmpeg on PATH.
"""
import glob
import os
import shutil
import subprocess
import sys
import tempfile

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
W, H = 1200, 675
FPS = 12.5
FACES = 247
PICK = 4                       # b3a frames at the end that show the pick
SQ0, SQ1 = 1.1, 1.5            # SquareSize sweep in b3b (eased, same as the capture script)


def font(size, bold=False, mono=False):
    names = ("consolab.ttf", "consola.ttf") if mono else (("segoeuib.ttf", "arialbd.ttf") if bold else ("segoeui.ttf", "arial.ttf"))
    for name in names:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    return ImageFont.load_default(size)


F_CAP, F_SUB, F_MONO = font(34, True), font(24), font(21, mono=True)


def ease(x):
    return x * x * (3 - 2 * x)


def caption(im, title, sub=None):
    d = ImageDraw.Draw(im, "RGBA")
    d.rectangle((0, H - 96, W, H), fill=(20, 22, 26, 215))
    d.text((32, H - 86), title, font=F_CAP, fill=(255, 255, 255))
    if sub:
        d.text((32, H - 42), sub, font=F_SUB, fill=(190, 196, 206))
    return im


def packet(im, lines):
    d = ImageDraw.Draw(im, "RGBA")
    pad, lh = 16, 28
    w = max(d.textlength(t, font=F_MONO) for t in lines) + 2 * pad
    d.rounded_rectangle((24, 24, 24 + w, 24 + 2 * pad + lh * len(lines) - 6), 10, fill=(20, 22, 26, 225),
                        outline=(255, 230, 0, 255), width=2)
    for i, t in enumerate(lines):
        d.text((24 + pad, 24 + pad + i * lh), t, font=F_MONO, fill=(255, 230, 0) if i == 0 else (235, 238, 242))
    return im


def load(folder, pattern):
    return [Image.open(p).convert("RGB").resize((W, H), Image.LANCZOS) for p in sorted(glob.glob(os.path.join(folder, pattern)))]


def build(folder):
    b1, b2s, b2g = load(folder, "b1_*.png"), load(folder, "b2s_*.png"), load(folder, "b2g_*.png")
    b3a, b3b = load(folder, "b3a_*.png"), load(folder, "b3b_*.png")
    seq = []

    # 1. the STEP: no history
    for im in b1:
        seq.append(caption(im.copy(), "Imported STEP", "A dead solid: no history, no parameters"))
    seq += [seq[-1]] * 4

    # 2. cross-fade to the rebuild, then count the verified faces
    n = len(b2s)
    for i in range(n):
        t = ease(min(1.0, i / (n * 0.5)))
        im = Image.blend(b2s[i], b2g[i], t)
        k = round(FACES * ease(max(0.0, (i - n * 0.4) / (n * 0.6))))
        sub = "Verified face by face: %d / %d" % (k, FACES) if k else "Claude measures it and rebuilds it with native components"
        seq.append(caption(im, "Rebuilt as a parametric Grasshopper 2 model", sub))
    hold = caption(b2g[-1].copy(), "%d / %d faces  ·  max deviation 0.0019 mm" % (FACES, FACES),
                   "Deterministic check against the original STEP (NIST FTC-08)")
    seq += [hold] * 22

    # 3a. move in; the pick appears
    for i, im in enumerate(b3a):
        im = im.copy()
        if i >= len(b3a) - PICK:
            packet(im, ['FeatureContext: face 166', 'Group  "4 Deck: square hole"', 'Slider SquareSize = 1.100 in'])
        seq.append(caption(im, "Pick a face", "FeatureContext traces it to the component and slider that made it"))
    seq += [seq[-1]] * 10

    # 3b. the AI changes the slider; every frame is a live GH2 solve
    m = len(b3b)
    for i, im in enumerate(b3b):
        s = SQ0 + (SQ1 - SQ0) * ease(i / (m - 1.0))
        im = packet(im.copy(), ['FeatureContext: face 166', 'Group  "4 Deck: square hole"', 'Slider SquareSize = %.3f in' % s])
        seq.append(caption(im, "Claude edits the parameter, not the pixels", "Live re-solve: still %d faces, valid solid" % FACES))
    seq += [seq[-1]] * 20
    return seq


def main(folder):
    if shutil.which("ffmpeg") is None:
        sys.exit("ffmpeg not found on PATH")
    seq = build(folder)
    tmp = tempfile.mkdtemp()
    try:
        for i, im in enumerate(seq):
            im.save(os.path.join(tmp, "%04d.png" % i))
        src = ["-framerate", str(FPS), "-i", os.path.join(tmp, "%04d.png")]
        gif, mp4 = os.path.join(HERE, "hero.gif"), os.path.join(HERE, "hero.mp4")
        vf = "scale=960:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=160:stats_mode=diff[p];[b][p]paletteuse=dither=sierra2_4a:diff_mode=rectangle"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error"] + src + ["-vf", vf, "-loop", "0", gif], check=True)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error"] + src +
                       ["-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", "-movflags", "+faststart", mp4], check=True)
        print("%d frames, %.1f s" % (len(seq), len(seq) / FPS))
        for p in (gif, mp4):
            print("%s  %.2f MB" % (p, os.path.getsize(p) / 1e6))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main(sys.argv[1])
