from pathlib import Path
from PIL import Image

SIZE = (128, 128)
DELAY_MS = 180


def load_base(path: Path) -> Image.Image:
    im = Image.open(path).convert('RGBA')
    return im.resize(SIZE, Image.Resampling.NEAREST)


def shift(im: Image.Image, dx: int = 0, dy: int = 0) -> Image.Image:
    bg = Image.new('RGBA', SIZE, (245, 245, 245, 255))
    bg.alpha_composite(im, (dx, dy))
    return bg


def darken_band(im: Image.Image, top: int, height: int, alpha: int = 110) -> Image.Image:
    out = im.copy()
    overlay = Image.new('RGBA', (SIZE[0], height), (20, 20, 20, alpha))
    out.alpha_composite(overlay, (0, top))
    return out


def brighten(im: Image.Image, amount: int = 18) -> Image.Image:
    out = im.copy()
    px = out.load()
    for y in range(SIZE[1]):
        for x in range(SIZE[0]):
            r, g, b, a = px[x, y]
            px[x, y] = (min(255, r + amount), min(255, g + amount), min(255, b + amount), a)
    return out


def make_frames(idx: int, base: Image.Image):
    if idx == 1:  # angry: jitter
        return [shift(base, -1, 0), shift(base, 1, 0), shift(base, 0, -1)]
    if idx == 2:  # happy: bounce+sparkle feel
        return [brighten(shift(base, 0, 0), 16), brighten(shift(base, 0, -2), 24), brighten(shift(base, 0, 0), 16)]
    if idx == 3:  # blank/confused: subtle blink
        return [shift(base, 0, 0), darken_band(shift(base, 0, 0), 55, 10, 120), shift(base, 0, 0)]
    if idx == 4:  # sleepy: stronger blink + droop
        return [shift(base, 0, 0), darken_band(shift(base, 0, 1), 54, 14, 140), shift(base, 0, 2)]
    if idx == 5:  # thinking: tilt
        return [shift(base, -1, 0), shift(base, 1, 0), shift(base, 0, -1)]
    return [base]


def main():
    in_dir = Path('input_images')
    out_dir = Path('output_gifs')
    out_dir.mkdir(parents=True, exist_ok=True)

    for idx in range(1, 6):
        src = in_dir / f'{idx}.png'
        if not src.exists():
            print(f'SKIP: missing {src}')
            continue
        base = load_base(src)
        frames = make_frames(idx, base)
        dst = out_dir / f'{idx}.gif'
        frames[0].save(
            dst,
            save_all=True,
            append_images=frames[1:],
            optimize=False,
            duration=DELAY_MS,
            loop=0,
            disposal=2,
        )
        print(f'OK: {dst}')


if __name__ == '__main__':
    main()
