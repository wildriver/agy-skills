---
name: agy-review
description: agy(Google Antigravity CLI)経由で Gemini(既定 gemini-3.8-flash-high)に文章を渡し、推敲・校正・批評・セカンドオピニオンをテキストで受け取る。ユーザーが「Gemini に推敲させて」「別のモデルの意見も」「agy で見て」「セカンドオピニオン」「他の AI にも読ませて」と言ったとき、および日本語・英語の原稿(論文、記事、スライド原稿、メール、README、申請書)の推敲・校正・レビューを頼まれて別視点が有用なときに使う。Claude 自身の推敲に加えて第二の目が欲しい場面では、明示的に Gemini と言われなくても提案・使用してよい。ファイルは編集せず、結果はテキストで返る。
allowed-tools: Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/*)
---

# agy-review: Gemini に文章を推敲・批評させる

agy(Antigravity CLI)の print モードで Gemini を呼び、文章のレビューをテキストで受け取る。
Claude とは別系統のモデルの目を入れることで、自分では見落とす表記ゆれ・論理の飛躍・読者視点の疑問を拾うのが目的。
API キー不要、ローカルの Antigravity アカウントのクォータで動く。

> `${CLAUDE_SKILL_DIR}` は Claude Code がスキル読み込み時にこの SKILL.md のあるディレクトリへ展開する。もし展開されずに残っていたら、スキル読み込み時に表示される「Base directory for this skill」のパスに読み替える。

## 使い方

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/agy_review.py <file...> \
  [--mode proofread|critique|rewrite|custom] [--context "読者・媒体・目的"] \
  [--instructions "追加指示"] [--model gemini-3.8-flash-high] [--out review.md]
```

| mode | 何が返るか | 使う場面 |
|---|---|---|
| `proofread`(既定) | 「## 指摘」(箇所→修正案: 理由)+「## 修正後全文」 | 表記・文法・冗長・用語ゆれを直したい |
| `critique` | 重大 / 改善推奨 / 良い点。書き換えなし | 論理・構成・主張と根拠の対応を見てほしい |
| `rewrite` | 修正後の全文のみ | 自分で diff を取って取捨選択したい |
| `custom` | `--instructions` の指示どおり | 翻訳チェック、査読者ロール、要約、タイトル案など |

- 入力は複数ファイル可。`-` で stdin。本文はプロンプトに埋め込まれる(agy のヘッドレスモードはファイルを読めないため)。数万字までは問題ない。
- 結果は stdout に出る。`--out` で同時にファイル保存できる。stderr に所要秒数とトークン数が出る。
- `--context` に読者・媒体・目的(例: 「情報処理学会研究報告、査読なし、読者は HCI 研究者」)を渡すと指摘の精度が上がる。
- 所要時間は数千字で 20〜40 秒、長文で数分。`--timeout` は分単位(既定 8)。

## ワークフロー

1. 対象ファイルと目的を確認する。まず自分で一読し、文体(です・ます / である)と文書の種類を把握する。
2. 目的に合う mode を選び、`--context` を付けて実行する。長い原稿は章ごとに分けると指摘の粒度が揃う。
3. 返ってきた指摘を鵜呑みにせず精査する。Gemini は「事→こと」のような表記統一や冗長削減には強いが、専門用語の言い換えや主張の弱体化を提案することがある。原文の意図・分野の慣習・ユーザーの文体を優先して取捨選択する。
4. 採用する修正だけを Edit で原稿に反映する。`rewrite` の全文をそのまま上書きしない(細部の改変が混ざる)。
5. ユーザーには、採用した点・却下した点とその理由を短く報告する。指摘の原文が必要なら `--out` で保存したファイルを示す。

## 使い分けの例

```bash
# 研究会原稿の第 2 章を推敲
python3 ${CLAUDE_SKILL_DIR}/scripts/agy_review.py sec2.md --context "IPSJ 研究報告、である調、読者はセンシング研究者"

# 論理の穴だけ見てほしい
python3 ${CLAUDE_SKILL_DIR}/scripts/agy_review.py intro.md --mode critique

# 英語アブストラクトをネイティブ査読者の目で
python3 ${CLAUDE_SKILL_DIR}/scripts/agy_review.py abstract.md --mode custom \
  --instructions "Act as a native-English CHI reviewer. Flag unidiomatic phrasing, overclaiming, and unclear contribution statements. Give corrected sentences."

# 複数モデルの意見を比べる
python3 ${CLAUDE_SKILL_DIR}/scripts/agy_review.py draft.md --mode critique --out review-flash.md
python3 ${CLAUDE_SKILL_DIR}/scripts/agy_review.py draft.md --mode critique --model claude-opus-4-6-thinking --out review-opus.md
```

## 知っておくべき挙動

- `agy models` で使えるモデル一覧が出る。既定は `gemini-3.8-flash-high`(ユーザーの指定。文章の構成を見る用途ではこれを使う)。他候補は `gemini-3.1-pro-high`、`claude-opus-4-6-thinking` など。
- agy はヘッドレスだとファイル読み取りを自動拒否する。だからスクリプトは本文を埋め込む方式にしており、`--dangerously-skip-permissions` は使わない。
- agy のプロンプト引数は `-p=<text>` の形で渡す(スクリプト対応済み)。直接叩く場合も同じ。
- 結果に Gemini が勝手にファイル編集を試みた形跡があれば、それは失敗扱い。プロンプトの「ツールを使わない」指示で通常は起きない。

## 関連スキルとの関係

- 日本語の AI 臭除去や文体規範(humanizer 系、japanese-tech-writing)は Claude 自身が適用するルール。本スキルはその前後で「別モデルの読者」を入れる用途。両方使うときは、まず本スキルで指摘を集め、採用判断と書き直しは Claude の規範に従う。
- 画像生成は agy-image スキル。
