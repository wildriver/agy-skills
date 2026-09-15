# agy-skills

Claude Code から Google **Antigravity CLI(`agy`)** を使うためのスキル集です。

| スキル | 何をするか |
|---|---|
| `agy-image` | agy の `generate_image`(Gemini の画像生成、Nano Banana 系)で画像を生成・編集し、指定パスに保存する。既定で背景透過 PNG |
| `agy-review` | 原稿を Gemini(既定 `gemini-3.8-flash-high`)に渡し、推敲・校正・批評・セカンドオピニオンをテキストで受け取る |

どちらも API キー不要で、ローカルにログイン済みの agy とそのクォータで動きます。ファイルを勝手に編集することはありません。

*English: Claude Code skills that drive Google's Antigravity CLI (`agy`): `agy-image` generates or edits raster images through agy's built-in `generate_image` tool and copies the result to a path you choose; `agy-review` sends a draft to Gemini for proofreading, critique, or a second opinion and returns text only. No API key is needed; both use your local, authenticated agy install.*

## 前提条件

- [Antigravity CLI](https://antigravity.google/docs/cli/) がインストールされ、ログイン済みであること。`agy models` が一覧を返せば OK。
- `generate_image` が使えるアカウント(Antigravity で画像生成が有効なプラン)。
- Python 3.8 以上(標準ライブラリのみ。Pillow があれば画像寸法の取得に使う)。
- 検証環境: macOS 15 / agy 1.2.3 / Claude Code 2.1.x。Linux・Windows は未検証。

## インストール

### プラグインとして(推奨)

Claude Code のセッション内で:

```
/plugin marketplace add wildriver/agy-skills
/plugin install agy-skills@agy-skills
```

シェルからなら:

```bash
claude plugin marketplace add wildriver/agy-skills
claude plugin install agy-skills@agy-skills
```

スキルは `/agy-skills:agy-image`、`/agy-skills:agy-review` として登録されます(短縮形 `/agy-image` も衝突がなければ使えます)。更新は `claude plugin marketplace update agy-skills` です。

### 手動で

```bash
git clone https://github.com/wildriver/agy-skills.git
ln -s "$PWD/agy-skills/plugins/agy-skills/skills/agy-image" ~/.claude/skills/
ln -s "$PWD/agy-skills/plugins/agy-skills/skills/agy-review" ~/.claude/skills/
```

## 使い方

自然文で頼めば Claude がスキルを選びます。

- 「スライド用にタッチセンサの断面イラストを 16:9 で作って」
- 「この画像の配色を暖色系にして」(参照画像として渡され、差分編集になります)
- 「intro.md を Gemini に推敲させて」「別のモデルの意見も聞きたい」

スクリプトを直接叩くこともできます。

```bash
# 画像生成。既定で背景透過 PNG(被写体で切り抜き)になる。アスペクト比は 1:1 2:3 3:2 3:4 4:3 9:16 16:9
python3 plugins/agy-skills/skills/agy-image/scripts/agy_image.py \
  "Clean flat vector illustration of a capacitive touch sensor cross-section, no text" \
  --out images/sensor.png --aspect 16:9

# 抜き方はプロンプトから自動選択(neon/glow → black、ink/sketch → white、他は chroma)。明示も可
python3 plugins/agy-skills/skills/agy-image/scripts/agy_image.py \
  "Neon line-art smartphone with a glowing scroll trajectory, no text" \
  --out images/phone_neon.png --aspect 1:1 --transparent black

# 背景込みの一枚絵が欲しいとき(スライド全面の背景など)
python3 plugins/agy-skills/skills/agy-image/scripts/agy_image.py \
  "Dark navy abstract background with faint constellation lines" \
  --out images/bg.jpg --aspect 16:9 --transparent none

# 既存画像を編集(参照は最大 3 枚)
python3 plugins/agy-skills/skills/agy-image/scripts/agy_image.py \
  "Keep the composition; change the palette to warm orange tones" \
  --ref images/sensor.jpg --out images/sensor_warm.jpg --aspect 16:9

# 推敲(指摘 + 修正後全文)/ 批評のみ / 全文のみ / 自由指示
python3 plugins/agy-skills/skills/agy-review/scripts/agy_review.py draft.md
python3 plugins/agy-skills/skills/agy-review/scripts/agy_review.py draft.md --mode critique --context "研究会原稿、である調"
python3 plugins/agy-skills/skills/agy-review/scripts/agy_review.py draft.md --mode rewrite --out draft.rewritten.md
python3 plugins/agy-skills/skills/agy-review/scripts/agy_review.py abstract.md --mode custom --instructions "Act as a CHI reviewer..."
```

## 動く環境・動かない環境

スクリプトはローカルの `agy` を起動するため、**シェルが使える Claude Code(ターミナル、または Claude Desktop の Code タブ)でのみ動きます**。Claude Desktop の PowerPoint / Word 連携や Cowork のようなサンドボックスでは `agy` が無く外部通信もできないため実行できません。その場合は Claude Code で画像を生成・原稿を推敲し、生成物のファイルパスをサンドボックス側の Claude に渡して配置してもらう二段階の運用になります。SKILL.md にはこの状況で代替物を勝手に作らずユーザーへ案内するよう書いてあります。

## 挙動と制限

- agy はヘッドレス(`-p`)モードだとファイル読み取り権限を自動拒否します。そのため `agy-review` は本文をプロンプトに埋め込み、`agy-image` の参照画像は `generate_image` の `ImagePaths` で渡します。`--dangerously-skip-permissions` は使いません。
- 画像モデルは Antigravity 側で固定され、選択できません。出力は約 1K(16:9 で 1376x768 程度)、Google の C2PA 署名付き JPEG です。2K/4K や特定バージョンの指定が必要なら Gemini API を直接使う別の手段が必要です。
- 生成画像の原本は `~/.gemini/antigravity-cli/brain/<会話ID>/` に残り、スクリプトはそこから `--out` にコピーします。場所が違う環境では `AGY_BRAIN_DIR` で上書きできます。
- `agy` が PATH に無いときは `~/.local/bin/agy` などを探します。見つからなければ `AGY_BIN=/path/to/agy` を設定してください。
- 「no text」と書いても英語ラベルが入ることがあります。強めに否定するか、`--ref` で「remove all text」と差分編集してください。
- 既定で単色背景で生成し、手元で背景を抜いて透過 PNG にします(agy 自体はアルファを返せません)。`--transparent auto|black|white|chroma|none` で抜き方を選べ、`none` で背景込みの JPEG になります。切り抜きは `--no-trim` で無効化できます。Pillow は任意で、無ければ macOS の `sips` と標準ライブラリで処理します。Linux で Pillow が無い場合はこの機能だけ使えません。
- `--transparent none` のときは `--out` の拡張子が生成物に合わせて `.jpg` になります。透過モードでは常に `.png` です。
- 所要時間の目安: 画像 1 枚 30〜70 秒、推敲は数千字で 20〜50 秒。

## リポジトリ構成

```
.claude-plugin/marketplace.json      # マーケットプレイス定義
plugins/agy-skills/
  .claude-plugin/plugin.json         # プラグイン定義
  skills/agy-image/{SKILL.md,scripts/agy_image.py}
  skills/agy-review/{SKILL.md,scripts/agy_review.py}
```

## ライセンス

MIT
