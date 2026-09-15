#!/usr/bin/env python3
"""Generate text with Gemini through the agy (Antigravity CLI) and print only the text.

Unlike agy_review.py (which critiques an existing draft), this writes new text from a request:
drafts, emails, summaries, translations, title/copy ideas, outlines, FAQ, structured JSON, etc.

Usage:
  agy_text.py "依頼文"                                   # free-form generation
  agy_text.py "要約して" --input paper.md --input notes.md # use files as source material
  agy_text.py "記事タイトル案" --variants 5               # N alternatives as ## 案1..N
  agy_text.py "書誌情報を抽出" --input refs.txt --json --schema schema.json
  echo "依頼文" | agy_text.py - --out draft.md

Notes:
- Files are embedded in the prompt (agy's headless mode cannot read files itself).
- agy's own --json-schema flag is not used: in print mode it tends to fill the schema with a
  task summary instead of the content. JSON mode here asks for JSON in the prompt and validates locally.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time

GUARD = (
    "\n\n# 出力のルール\n"
    "- ツールは使わない。ファイルの読み書き、コマンド実行、作業計画や作業報告はしない。\n"
    "- 依頼された文章そのものだけを出力する。「以下が〜です」「承知しました」などの前置きや、末尾の補足・提案は付けない。\n"
    "- 指示がなければ依頼文と同じ言語で書く。\n"
)


def find_agy():
    env = os.environ.get("AGY_BIN")
    if env and os.path.exists(os.path.expanduser(env)):
        return os.path.expanduser(env)
    p = shutil.which("agy")
    if p:
        return p
    for c in ["~/.local/bin/agy", "~/.antigravity/bin/agy", "/opt/homebrew/bin/agy", "/usr/local/bin/agy",
              os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "agy", "agy.exe")]:
        c = os.path.expanduser(c)
        if c and os.path.exists(c):
            return c
    sys.exit("agy not found. Install Antigravity CLI, add it to PATH, or set AGY_BIN=/path/to/agy.")


def read_text(path):
    if path == "-":
        return sys.stdin.read()
    with open(os.path.expanduser(path), encoding="utf-8") as f:
        return f.read()


def run_agy(prompt, model, timeout_min):
    cmd = [find_agy(), "--output-format", "json", "--print-timeout", f"{timeout_min}m", "--model", model, f"-p={prompt}"]
    t0 = time.time()
    proc = subprocess.run(cmd, capture_output=True, text=True)
    elapsed = round(time.time() - t0, 1)
    try:
        data = json.loads(proc.stdout.strip().splitlines()[-1])
    except Exception:
        sys.stderr.write("agy did not return JSON.\n--- stdout ---\n" + proc.stdout[-3000:] + "\n--- stderr ---\n" + proc.stderr[-3000:] + "\n")
        sys.exit(2)
    if data.get("status") != "SUCCESS" and not data.get("response"):
        sys.stderr.write("agy reported failure:\n" + json.dumps(data, ensure_ascii=False, indent=2)[-3000:] + "\n")
        sys.exit(3)
    if data.get("status") != "SUCCESS":
        sys.stderr.write(f"warning: agy status={data.get('status')} error={data.get('error')}; using the returned text\n")
    return data, elapsed


def extract_json(text):
    """Return parsed JSON from a response that may be wrapped in ``` fences or have stray prose."""
    t = text.strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", t, re.S)
    if m:
        t = m.group(1).strip()
    try:
        return json.loads(t)
    except Exception:
        pass
    starts = [i for i in (t.find("{"), t.find("[")) if i >= 0]
    if not starts:
        raise ValueError("no JSON found")
    start = min(starts)
    end = max(t.rfind("}"), t.rfind("]"))
    return json.loads(t[start:end + 1])


def check_schema(obj, schema, path="$"):
    """Tiny structural check (type / required / properties / items / enum / minItems / maxItems). Returns a list of problems."""
    probs = []
    types = {"object": dict, "array": list, "string": str, "number": (int, float), "integer": int, "boolean": bool, "null": type(None)}
    st = schema.get("type")
    if st:
        allowed = st if isinstance(st, list) else [st]
        if not any(isinstance(obj, types.get(a, object)) and not (a in ("number", "integer") and isinstance(obj, bool)) for a in allowed):
            return [f"{path}: expected {st}, got {type(obj).__name__}"]
    if "enum" in schema and obj not in schema["enum"]:
        probs.append(f"{path}: {obj!r} not in enum")
    if isinstance(obj, dict):
        for k in schema.get("required", []):
            if k not in obj:
                probs.append(f"{path}: missing required key '{k}'")
        for k, sub in schema.get("properties", {}).items():
            if k in obj:
                probs += check_schema(obj[k], sub, f"{path}.{k}")
    if isinstance(obj, list):
        if "minItems" in schema and len(obj) < schema["minItems"]:
            probs.append(f"{path}: {len(obj)} items < minItems {schema['minItems']}")
        if "maxItems" in schema and len(obj) > schema["maxItems"]:
            probs.append(f"{path}: {len(obj)} items > maxItems {schema['maxItems']}")
        if "items" in schema:
            for i, it in enumerate(obj):
                probs += check_schema(it, schema["items"], f"{path}[{i}]")
    return probs


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("request", nargs="?", help="What to write ('-' reads the request from stdin)")
    ap.add_argument("--request-file", help="Read the request from a file")
    ap.add_argument("--input", action="append", default=[], help="Source material file to embed (repeatable)")
    ap.add_argument("--context", help="Background: audience, medium, purpose, tone, length, style guide")
    ap.add_argument("--variants", type=int, default=1, help="Produce N alternatives as '## 案1' ... '## 案N'")
    ap.add_argument("--json", action="store_true", help="Output JSON only (parsed and pretty-printed locally)")
    ap.add_argument("--schema", help="JSON schema file describing the expected JSON (implies --json)")
    ap.add_argument("--model", default="gemini-3.8-flash-high", help="agy model id (default gemini-3.8-flash-high; 'agy models' lists them)")
    ap.add_argument("--timeout", type=int, default=8, help="Minutes to wait (default 8)")
    ap.add_argument("--out", help="Also write the result to this file")
    ap.add_argument("--raw-json", action="store_true", help="Print agy's raw JSON envelope instead of the text")
    args = ap.parse_args()

    if args.request_file:
        request = read_text(args.request_file)
    elif args.request:
        request = read_text("-") if args.request == "-" else args.request
    else:
        ap.error("give a request, '-', or --request-file")

    schema = None
    if args.schema:
        with open(os.path.expanduser(args.schema), encoding="utf-8") as f:
            schema = json.load(f)
        args.json = True

    prompt = "# 依頼\n" + request.strip() + "\n"
    if args.context:
        prompt += "\n# 背景（読者・媒体・目的・トーンなど）\n" + args.context.strip() + "\n"
    total_chars = 0
    for p in args.input:
        text = read_text(p)
        total_chars += len(text)
        prompt += f"\n# 資料: {os.path.basename(p) if p != '-' else 'stdin'}\n<<<\n{text}\n>>>\n"
    if total_chars > 400_000:
        sys.stderr.write(f"warning: {total_chars} characters of input is very large; consider splitting.\n")
    if args.variants > 1 and not args.json:
        prompt += f"\n# 形式\n互いに切り口の異なる案を {args.variants} 通り書く。各案は「## 案1」「## 案2」…の見出しで始める。\n"
    if args.json:
        prompt += "\n# 形式\n有効な JSON だけを出力する。コードフェンス、説明文、コメントは付けない。\n"
        if schema:
            prompt += "次の JSON Schema に従う:\n" + json.dumps(schema, ensure_ascii=False) + "\n"
    prompt += GUARD

    data, elapsed = run_agy(prompt, args.model, args.timeout)
    text = data.get("response", "").strip()

    if args.json:
        attempts = 1
        while True:
            try:
                obj = extract_json(text)
                probs = check_schema(obj, schema) if schema else []
                if not probs:
                    break
                err = "; ".join(probs[:8])
            except Exception as e:
                err = f"invalid JSON: {e}"
            if attempts >= 2:
                sys.stderr.write(f"JSON output failed validation after retry: {err}\n--- response ---\n{text[-3000:]}\n")
                sys.exit(4)
            attempts += 1
            fix = prompt + f"\n# 前回の出力の問題\n{err}\n前回の出力:\n{text[:6000]}\n問題を直した JSON だけを出力する。\n"
            data, e2 = run_agy(fix, args.model, args.timeout)
            elapsed += e2
            text = data.get("response", "").strip()
        text = json.dumps(obj, ensure_ascii=False, indent=2)

    out_text = text + "\n"
    if args.out:
        op = os.path.abspath(os.path.expanduser(args.out))
        os.makedirs(os.path.dirname(op), exist_ok=True)
        with open(op, "w", encoding="utf-8") as f:
            f.write(out_text)
    if args.raw_json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        sys.stdout.write(out_text)
    u = data.get("usage", {})
    sys.stderr.write(f"[agy-text] model={args.model} chars_in={total_chars} seconds={elapsed} "
                     f"in={u.get('input_tokens')} out={u.get('output_tokens')}" + (f" saved={args.out}" if args.out else "") + "\n")


if __name__ == "__main__":
    main()
