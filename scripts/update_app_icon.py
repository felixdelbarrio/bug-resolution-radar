from __future__ import annotations

import argparse
from pathlib import Path


def _center_crop_square(img):
    width, height = img.size
    side = min(width, height)
    left = (width - side) // 2
    top = (height - side) // 2
    return img.crop((left, top, left + side, top + side))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Normalize an input image into app icon assets (PNG + ICO)."
    )
    parser.add_argument(
        "--input",
        required=True,
        help="Input image path (PNG/JPG/etc).",
    )
    parser.add_argument(
        "--png-out",
        default="assets/app_icon/bug-resolution-radar.png",
        help="Output PNG path (default: assets/app_icon/bug-resolution-radar.png).",
    )
    parser.add_argument(
        "--ico-out",
        default="assets/app_icon/bug-resolution-radar.ico",
        help="Output ICO path (default: assets/app_icon/bug-resolution-radar.ico).",
    )
    parser.add_argument(
        "--size",
        type=int,
        default=1024,
        help="Square output size in pixels (default: 1024).",
    )
    args = parser.parse_args()

    in_path = Path(args.input).expanduser().resolve()
    png_out = Path(args.png_out)
    ico_out = Path(args.ico_out)
    size = int(args.size)

    if not in_path.exists():
        raise FileNotFoundError(str(in_path))
    if size <= 0:
        raise ValueError("--size must be positive")

    from PIL import Image

    img = Image.open(in_path)
    if getattr(img, "mode", "") != "RGBA":
        img = img.convert("RGBA")
    img = _center_crop_square(img)
    if img.size != (size, size):
        img = img.resize((size, size), Image.LANCZOS)

    png_out.parent.mkdir(parents=True, exist_ok=True)
    img.save(png_out, format="PNG", optimize=True)

    sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    ico_out.parent.mkdir(parents=True, exist_ok=True)
    img.save(ico_out, format="ICO", sizes=sizes)

    print(f"Wrote {png_out}")
    print(f"Wrote {ico_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

