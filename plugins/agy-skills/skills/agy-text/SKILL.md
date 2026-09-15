---
name: agy-text
description: agy(Google Antigravity CLI)経由で Gemini(既定 gemini-3.8-flash-high)に文章を新しく書かせ、テキストだけを受け取る。ユーザーが「Gemini に書かせて」「agy で文章を作って」「別のモデルで下書きを」「Gemini 版の案も」「タイトル案を Gemini に何本か出させて」と言ったとき、および文章の下書き・メール文面・要約・翻訳・タイトルやキャッチコピーの複数案・FAQ・構造化 JSON を Gemini で生成したいときに使う。既存原稿の推敲・批評は agy-review、画像は agy-image を使う。ユーザーが Gemini や agy を指定していない普段の文章作成は Claude 自身が書くので、このスキルは使わない。
allowed-tools: Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/*)
---

# agy-text: Gemini に文章を書かせる

agy(Antigravity CLI)の print モードで Gemini を呼び、依頼に対する文章だけを受け取る。
agy-review が「今ある原稿を読んで指摘する」のに対し、こちらは「白紙から書く」。
API キー不要、ローカルの Antigravity アカウントのクォータで動く。

> `${CLAUDE_SKILL_DIR}` は Claude Code がスキル読み込み時にこの SKILL.md のあるディレクトリへ展開する。もし展開されずに残っていたら、スキル読み込み時に表示される「Base directory for this skill」のパスに読み替える。

## 使い方

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/agy_text.py "<依頼文>" \
  [--input 資料.md ...] [--context "読者・媒体・目的・トーン・長さ"] \
  [--variants N] [--json [--schema schema.json]] [--model gemini-3.8-flash-high] [--out out.md]
```

| オプション | 意味 |
|---|---|
| `--input` | 下敷きにする資料ファイル。複数可。本文はプロンプトに埋め込まれる |
| `--context` | 読者、媒体、目的、文体、分量など |
| `--variants N` | 切り口の違う案を N 通り、「## 案1」…の見出し付きで返す |
| `--json` | JSON だけを返す。手元で解析して整形する |
| `--schema` | 期待する JSON の形(JSON Schema)。満たさなければ 1 回だけ自動で再依頼する |
| `--request-file` / `-` | 依頼文をファイルや標準入力から読む(長い依頼向け) |
| `--model` | 既定 `gemini-3.8-flash-high`。`agy models` で一覧 |
| `--out` | 結果をファイルにも保存 |

stdout には生成された文章だけが出る。stderr に所要秒数とトークン数が出る。所要時間は 20〜40 秒程度。

## いちばん大事な注意：事実は資料で渡す

資料を渡さずに研究・製品・人物などの説明を書かせると、Gemini はもっともらしい中身を作る。
実例：「Webアンケートの操作ログ研究を紹介する文章」とだけ頼んだら、実際の研究にない「マウス軌跡」「機械学習」を含む紹介文が返ってきた。

- 事実を含む文章は、必ず `--input` で元の資料(論文要旨、メモ、スライドの文字など)を渡す。
- 生成物は Claude が資料と突き合わせて確認し、資料にない主張や数値が混ざっていたら指摘する。
- ユーザーに見せるときは「Gemini が書いた案」であることを明示する。Claude が書いたように装わない。

## ワークフロー

1. 目的・読者・分量・文体を確認する。足りなければ一般的な想定で補い、`--context` に書く。
2. 事実に基づく文章なら、元になる資料をファイルにして `--input` で渡す。会話中の情報しかなければ、Claude がそれをメモファイルにまとめてから渡す。
3. 案出し(タイトル、見出し、コピー、言い回し)は `--variants` で複数案を出させる。
4. 返ってきた文章を資料と照合し、事実の誤り・資料外の主張・指示違反(分量、文体)を確認する。
5. ユーザーには Gemini の出力をそのまま示し、確認で見つけた問題があれば併記する。Claude が手を入れた場合は、どこを直したかを分けて伝える。ファイルに反映するのはユーザーが望んだときだけ。

## 使用例

```bash
# 資料を元にメール本文
python3 ${CLAUDE_SKILL_DIR}/scripts/agy_text.py "資料を、共同研究の相談メールの本文(200字程度)にまとめて" \
  --input abstract.md --context "宛先は他分野の教授。丁寧な敬語"

# タイトル案を 5 本
python3 ${CLAUDE_SKILL_DIR}/scripts/agy_text.py "この研究の一般向け記事タイトル案" --input abstract.md --variants 5

# 構造化 JSON(スライド 1 枚分の要点)
python3 ${CLAUDE_SKILL_DIR}/scripts/agy_text.py "資料から発表スライド1枚分の要点を抽出して" \
  --input abstract.md --schema slide_schema.json --out slide.json

# 翻訳
python3 ${CLAUDE_SKILL_DIR}/scripts/agy_text.py "Translate into natural academic English" --input abstract_ja.md
```

## 知っておくべき挙動

- agy はヘッドレスモードでファイルを読めない。資料はスクリプトがプロンプトに埋め込む。`--dangerously-skip-permissions` は使わない。
- agy 自身の `--json-schema` フラグは使わない。print モードではスキーマに本文ではなく「作業完了」の要約が入って返ってくるため。`--json` / `--schema` はプロンプトで JSON を指示し、手元で解析・検証する。
- 「前置きや補足を付けない」とプロンプトで指示しているが、まれに「以下が〜です」が混ざる。気になる場合は取り除いてから使う。
- agy のプロンプト引数は `-p=<text>` の形で渡す(スクリプト対応済み)。
- 資料が数十万字を超えると警告を出す。長い資料は章ごとに分ける。

## この環境で agy が動かないとき

Claude Desktop の PowerPoint / Word 連携や Cowork のようなサンドボックスには `agy` が無く、外部通信もできない。その場合は Claude が代わりに書いて「Gemini の文章」と装わないこと。「この環境からは agy を起動できない」と伝え、Claude Code で同じ依頼をすれば実行できると案内する。Claude 自身が書くことを提案するのは構わないが、その場合は Claude の文章だと明示する。

## 関連スキル

- 既存の原稿を読んで直す・批評する → agy-review
- 画像を描く → agy-image
