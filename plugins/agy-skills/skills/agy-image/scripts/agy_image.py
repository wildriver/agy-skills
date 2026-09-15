#!/usr/bin/env python3
"""Generate or edit an image through the agy (Antigravity CLI) built-in generate_image tool.

Usage:
  agy_image.py "prompt text" --out path/to/file.jpg [--aspect 16:9] [--ref img.png ...]

Prints a JSON summary on stdout: {"out": ..., "source": ..., "width": ..., "height": ..., "seconds": ...}
Exit code 0 on success, non-zero on failure (raw agy output is dumped to stderr).
"""
import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import time

ASPECTS = ["1:1", "2:3", "3:2", "3:4", "4:3", "9:16", "16:9"]
# Where agy keeps generated artifacts. Override with AGY_BRAIN_DIR if your install differs.
BRAIN_DIR = os.environ.get("AGY_BRAIN_DIR") or os.path.expanduser("~/.gemini/antigravity-cli/brain")


def find_agy():
    """Locate the agy binary: $AGY_BIN, then PATH, then common install locations."""
    env = os.environ.get("AGY_BIN")
    if env and os.path.exists(os.path.expanduser(env)):
        return os.path.expanduser(env)
    p = shutil.which("agy")
    if p:
        return p
    candidates = [
        "~/.local/bin/agy",
        "~/.antigravity/bin/agy",
        "/opt/homebrew/bin/agy",
        "/usr/local/bin/agy",
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "agy", "agy.exe"),
    ]
    for c in candidates:
        c = os.path.expanduser(c)
        if c and os.path.exists(c):
            return c
    sys.exit("agy not found. Install Antigravity CLI, add it to PATH, or set AGY_BIN=/path/to/agy.")


def image_name_from(out_path):
    stem = os.path.splitext(os.path.basename(out_path))[0].lower()
    words = re.findall(r"[a-z0-9]+", stem)
    if not words:
        return "generated_image"
    return "_".join(words[:3])


def image_dims(path):
    """Best-effort (width, height). Pillow if installed, else macOS sips, else (None, None)."""
    try:
        from PIL import Image  # type: ignore
        with Image.open(path) as im:
            return im.size
    except Exception:
        pass
    if shutil.which("sips"):
        try:
            r = subprocess.run(["sips", "-g", "pixelWidth", "-g", "pixelHeight", path],
                               capture_output=True, text=True, timeout=20)
            w = re.search(r"pixelWidth:\s*(\d+)", r.stdout)
            h = re.search(r"pixelHeight:\s*(\d+)", r.stdout)
            if w and h:
                return (int(w.group(1)), int(h.group(1)))
        except Exception:
            pass
    return (None, None)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("prompt", help="Image description (passed verbatim to generate_image)")
    ap.add_argument("--out", required=True, help="Where to save the image (jpg/png). Directories are created.")
    ap.add_argument("--aspect", default="1:1", choices=ASPECTS, help="Aspect ratio (default 1:1)")
    ap.add_argument("--ref", action="append", default=[],
                    help="Reference/base image to edit or combine (repeatable, max 3)")
    ap.add_argument("--name", help="ImageName for the tool (lowercase_with_underscores, max 3 words). Derived from --out if omitted.")
    ap.add_argument("--timeout", type=int, default=6, help="Minutes to wait (default 6)")
    ap.add_argument("--model", help="agy model id, e.g. gemini-3.8-flash-high (optional)")
    args = ap.parse_args()

    if len(args.ref) > 3:
        sys.exit("generate_image accepts at most 3 reference images.")
    refs = []
    for r in args.ref:
        p = os.path.abspath(os.path.expanduser(r))
        if not os.path.exists(p):
            sys.exit(f"reference image not found: {p}")
        refs.append(p)

    name = args.name or image_name_from(args.out)
    out_path = os.path.abspath(os.path.expanduser(args.out))
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    lines = [
        "Call the generate_image tool exactly once with these parameters and do nothing else.",
        f"Prompt (pass it verbatim, do not rewrite or embellish it): {args.prompt}",
        f"ImageName: {name}",
        f"AspectRatio: {args.aspect}",
    ]
    if refs:
        lines.append("ImagePaths: " + json.dumps(refs))
        lines.append("The images in ImagePaths are the base/reference images to edit or combine.")
    lines.append("After the tool returns, reply with only the absolute path of the generated image file, nothing else.")
    instruction = "\n".join(lines)

    cmd = [find_agy(), "--output-format", "json", "--print-timeout", f"{args.timeout}m"]
    if args.model:
        cmd += ["--model", args.model]
    cmd.append(f"-p={instruction}")

    t0 = time.time()
    proc = subprocess.run(cmd, capture_output=True, text=True)
    elapsed = round(time.time() - t0, 1)

    try:
        data = json.loads(proc.stdout.strip().splitlines()[-1])
    except Exception:
        sys.stderr.write("agy did not return JSON.\n--- stdout ---\n" + proc.stdout[-3000:] + "\n--- stderr ---\n" + proc.stderr[-3000:] + "\n")
        sys.exit(2)

    if data.get("status") != "SUCCESS":
        sys.stderr.write("agy reported failure:\n" + json.dumps(data, ensure_ascii=False, indent=2)[-3000:] + "\n")
        sys.exit(3)

    response = data.get("response", "")
    m = re.search(r"((?:/|[A-Za-z]:\\)[^\s\)\]\"'>]+?\.(?:jpe?g|png|webp))", response)
    src = m.group(1) if m else None

    if not src or not os.path.exists(src):
        # Fallback: newest image in this conversation's brain directory.
        cid = data.get("conversation_id", "")
        cands = []
        for ext in ("jpg", "jpeg", "png", "webp"):
            cands += glob.glob(os.path.join(BRAIN_DIR, cid, f"*.{ext}"))
        cands = [c for c in cands if os.path.getmtime(c) >= t0 - 5]
        src = max(cands, key=os.path.getmtime) if cands else None

    if not src:
        sys.stderr.write("Could not locate generated image. agy response was:\n" + response + "\n")
        sys.exit(4)

    # Keep the source extension if --out has none or differs (we do not transcode).
    src_ext = os.path.splitext(src)[1].lower()
    if os.path.splitext(out_path)[1].lower() != src_ext:
        out_path = os.path.splitext(out_path)[0] + src_ext
    shutil.copy2(src, out_path)
    w, h = image_dims(out_path)
    print(json.dumps({"out": out_path, "source": src, "width": w, "height": h,
                      "seconds": elapsed, "aspect": args.aspect, "refs": refs}, ensure_ascii=False))


if __name__ == "__main__":
    main()
