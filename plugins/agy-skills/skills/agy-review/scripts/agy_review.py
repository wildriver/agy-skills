#!/usr/bin/env python3
"""Ask Gemini (via the agy / Antigravity CLI) to proofread, critique, or otherwise review text.

The text is embedded in the prompt (agy in headless mode cannot read files), so this works
for any file the caller can read. Nothing is edited on disk; the review comes back as text.

Usage:
  agy_review.py draft.md                          # proofread (default mode)
  agy_review.py draft.md --mode critique          # logic/structure review, no rewrite
  agy_review.py draft.md --mode rewrite           # rewritten full text only
  agy_review.py a.md b.md --mode custom --instructions "..."   # your own instructions
  cat draft.md | agy_review.py - --out review.md  # stdin, save the response

Modes:
  proofread  指摘一覧 + 修正後全文 (表記・文法・冗長・用語ゆれ)
  critique   論理の飛躍・構成・主張と根拠の対応を指摘。書き換えはしない
  rewrite    修正後の全文のみ返す(差分を自分で取りたいとき)
  custom     --instructions / --instructions-file の内容をそのまま指示にする
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time

MODES = {
    "proofread": (
        "あなたは日本語・英語の技術文書に精通した編集者です。以下の文章を推敲してください。\n"
        "観点: 誤字脱字、文法、表記ゆれ(漢字/かな、用語の統一)、冗長な表現、一文の長さ、主述のねじれ、"
        "曖昧語、段落内の論理のつながり。文体(です・ます/である)は原文に合わせ、内容や主張は変えないこと。\n\n"
        "出力形式(この見出しを必ず使う):\n"
        "## 指摘\n- 「原文の箇所」→「修正案」: 理由(1文)\n"
        "## 修正後全文\n(修正を反映した全文。マークダウン構造は保つ)\n"
    ),
    "critique": (
        "あなたは厳密だが建設的な査読者です。以下の文章について、表現ではなく内容と構成を批評してください。"
        "書き換えはせず、指摘のみ返してください。\n"
        "観点: 論理の飛躍、主張と根拠の対応、前提の未説明、用語定義の欠落、段落順序、読者が最初に抱く疑問、過大な主張。\n\n"
        "出力形式(この見出しを必ず使う):\n"
        "## 重大(読者が納得できない箇所)\n- 箇所: 問題点 → 直し方の方向性\n"
        "## 改善推奨\n- 箇所: 問題点 → 直し方の方向性\n"
        "## 良い点\n- (2〜3点、短く)\n"
    ),
    "rewrite": (
        "あなたは日本語・英語の技術文書に精通した編集者です。以下の文章を推敲し、修正後の全文だけを返してください。"
        "前置きや説明、コードフェンスは付けないこと。文体と構造(見出し・箇条書き・引用)は原文を保ち、"
        "内容や主張は変えないこと。\n"
    ),
}

GUARD = (
    "\n注意: ツールは使わないでください。ファイルの読み書きや編集は行わず、テキストのみで回答してください。\n"
)


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


def read_inputs(paths):
    chunks = []
    for p in paths:
        if p == "-":
            chunks.append(("stdin", sys.stdin.read()))
        else:
            with open(os.path.expanduser(p), encoding="utf-8") as f:
                chunks.append((p, f.read()))
    return chunks


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("inputs", nargs="+", help="Text/markdown files to review ('-' for stdin)")
    ap.add_argument("--mode", default="proofread", choices=list(MODES) + ["custom"])
    ap.add_argument("--instructions", help="Instructions for --mode custom (or extra notes for other modes)")
    ap.add_argument("--instructions-file", help="Read instructions from a file")
    ap.add_argument("--context", help="Background for the reviewer: audience, venue, purpose, style guide, etc.")
    ap.add_argument("--model", default="gemini-3.8-flash-high", help="agy model id (default gemini-3.8-flash-high; run 'agy models' to list)")
    ap.add_argument("--timeout", type=int, default=8, help="Minutes to wait (default 8)")
    ap.add_argument("--out", help="Also write the response to this file")
    ap.add_argument("--raw-json", action="store_true", help="Print agy's raw JSON instead of the response text")
    args = ap.parse_args()

    extra = ""
    if args.instructions_file:
        with open(os.path.expanduser(args.instructions_file), encoding="utf-8") as f:
            extra = f.read()
    elif args.instructions:
        extra = args.instructions

    if args.mode == "custom":
        if not extra:
            sys.exit("--mode custom requires --instructions or --instructions-file")
        head = extra + "\n"
    else:
        head = MODES[args.mode]
        if extra:
            head += "\n追加の指示: " + extra + "\n"
    if args.context:
        head += "\n背景情報(読者・媒体・目的など): " + args.context + "\n"

    chunks = read_inputs(args.inputs)
    total = sum(len(c[1]) for c in chunks)
    if total > 400_000:
        sys.stderr.write(f"warning: {total} characters is very large; consider splitting.\n")

    body = ""
    for label, text in chunks:
        body += f"\n=== 対象文章: {label} ===\n{text}\n=== ここまで: {label} ===\n"

    prompt = head + GUARD + body
    cmd = [find_agy(), "--output-format", "json", "--print-timeout", f"{args.timeout}m",
           "--model", args.model, f"-p={prompt}"]

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

    response = data.get("response", "").rstrip() + "\n"
    if args.out:
        outp = os.path.abspath(os.path.expanduser(args.out))
        os.makedirs(os.path.dirname(outp), exist_ok=True)
        with open(outp, "w", encoding="utf-8") as f:
            f.write(response)
    if args.raw_json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        sys.stdout.write(response)
    u = data.get("usage", {})
    sys.stderr.write(f"[agy-review] model={args.model} mode={args.mode} chars={total} "
                     f"seconds={elapsed} in={u.get('input_tokens')} out={u.get('output_tokens')}"
                     + (f" saved={args.out}" if args.out else "") + "\n")


if __name__ == "__main__":
    main()
