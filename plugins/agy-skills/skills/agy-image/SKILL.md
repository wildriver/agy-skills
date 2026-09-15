---
name: agy-image
description: agy(Google Antigravity CLI)の generate_image ツール(Gemini の画像生成、いわゆる Nano Banana)で画像を生成・編集する。ユーザーが「画像を作って」「イラスト」「挿絵」「図版」「アイキャッチ」「サムネイル」「アイコン」「スライド用の絵」「この画像の色を変えて」「この写真をもとに」など、ラスター画像(jpg/png)を新規生成または既存画像から編集・合成したいときは、明示的に agy や Gemini や Nano Banana と言われなくても必ずこのスキルを使う。SVG や Mermaid のような描画コード、グラフ・チャート(dataviz)、PPTX の図形は対象外。
allowed-tools: Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/*)
---

# agy-image: Gemini で画像を生成・編集する

agy(Antigravity CLI)はヘッドレスの print モードで `generate_image` という組み込みツールを持つ。
このスキルはそれを 1 回呼び出して、生成物を指定パスへコピーするラッパーを提供する。
API キーは不要で、ローカルの Antigravity アカウント認証とそのクォータで動く。

> `${CLAUDE_SKILL_DIR}` は Claude Code がスキル読み込み時にこの SKILL.md のあるディレクトリへ展開する。もし展開されずに残っていたら、スキル読み込み時に表示される「Base directory for this skill」のパスに読み替える。

## 使い方

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/agy_image.py "<英語の画像プロンプト>" \
  --out images/hero.png --aspect 16:9 [--ref base.png ...] [--name hero_image] [--timeout 6] \
  [--transparent auto|black|white|chroma|none] [--no-trim]
```

- **既定は背景透過 PNG + 切り抜き**。`--transparent` を省くと `auto` になり、プロンプトの語から抜き方を選ぶ(neon / glow / luminous などがあれば `black`、ink / pencil / sketch などがあれば `white`、それ以外は `chroma`)。ユーザーが背景込みの一枚絵(スライド全面の背景、写真風の情景)を求めているときだけ `--transparent none` を付ける。
- 切り抜きが不要(16:9 のまま位置を保ちたい)なら `--no-trim`。

- `--aspect` は `1:1`(既定) `2:3` `3:2` `3:4` `4:3` `9:16` `16:9` のみ。ピクセルサイズは指定できない。16:9 でおおよそ 1376x768 の JPEG が返る。必要な寸法があれば `sips` で後からリサイズ・トリミングする。
- `--ref` で参照画像を最大 3 枚渡すと、その画像を「編集」または「合成」するモードになる。再配色・要素追加・スタイル維持での差し替えなどに使う。
- `--transparent none` のときは `--out` の拡張子が生成物に合わせて置き換わる(agy は JPEG を返すので `.jpg` になる)。透過モードでは常に `.png`。
- 成功すると stdout に 1 行 JSON(`out`, `source`, `width`, `height`, `seconds`)を出す。失敗時は非ゼロ終了で stderr に agy の生出力が出る。
- 1 枚あたり 30〜60 秒かかる。複数枚は逐次でよいが、どうしても急ぐなら別プロセスで並列に起動できる。

## プロンプトの書き方

- 英語で書く。被写体、構図、スタイル(flat illustration / photo-realistic / isometric / line art など)、配色、背景、テキストの有無を 1〜3 文で。
- スライド用の挿絵なら文字を入れないよう明示すると、後で注釈を重ねやすい。ただし「no text」だけでは守られないことが多い(断面図の実験では GLASS / SENSOR LAYER などのラベルが勝手に付いた)。「absolutely no text, no labels, no letters, no annotations」と重ねて書き、それでも入るなら `--ref` で「remove all text and labels, keep everything else」と差分編集する。
- ラベルや文字を入れたい場合は短い英単語に限る。日本語の文字描画は崩れやすい。
- 参照画像ありのときは、変えたい点だけを書く。「keep the composition and style, change X to Y」の形が安定する。プロンプトで顔や細部を再記述しないこと(参照画像側に任せる)。
- スクリプトはプロンプトを verbatim で渡すよう agy に指示しているが、agy 側のエージェントが少し言い換えることはある。厳密さが必要なら生成物を見て再試行する。

## ワークフロー

1. 用途と保存先を決める(プロジェクト内の `images/` や `assets/` など)。既定が透過なので部品はそのままでよい。背景込みの一枚絵を求められたときだけ `--transparent none` を付ける(背景込みで作ると後から抜けない)。ファイル名は内容が分かる英小文字にすると `--name` を自動導出できる。
2. スクリプトを実行する。結果 JSON の `out` を確認し、Read ツールで画像を目視する。
3. 期待とずれていたら、プロンプトを直して再生成するか、`--ref` に今の生成物を渡して差分編集する。ゼロから作り直すより、参照編集の方が構図を保ったまま直せる。
4. 生成物のパスをユーザーに伝え、必要なら SendUserFile などで見せる。

## 背景透明の PNG が欲しいとき

agy(generate_image)はアルファ付き画像を返せない(常に JPEG)。そこでスクリプトは既定で、単色背景で生成するようプロンプトに追記し、手元で背景を抜いて透過 PNG にする。追加ライブラリは不要(Pillow があれば使い、無ければ macOS の sips と標準ライブラリで処理)。

| モード | 生成背景 | 向いている絵 | 仕組み |
|---|---|---|---|
| `black` | 純黒 | ネオン、発光、明るい線画、光のエフェクト | 明るさをアルファにする。どの背景に載せても加算発光のように見える |
| `white` | 純白 | 黒インクの線画、モノクロのスケッチ | 暗さをアルファにする |
| `chroma` | マゼンタ | フルカラーの被写体(フラットイラスト、人物、物) | 色距離でキーイングし、縁のマゼンタ被りを除去 |

- 出力は `--out` の拡張子に関係なく `.png` になる。あわせて抜く前の平坦な原本を `<stem>_flat.jpg` として残す。再編集(`--ref`)はこの原本を渡す方が安定する。
- 既定で不透明部分の外接矩形(+8px)に切り抜く(`--no-trim` で全面を保持)。auto の判定が外れたと感じたら `--transparent black|white|chroma` で明示する。
- 被写体自体に背景色と同じ色(black モードで黒い塗り、chroma でマゼンタ)が含まれていると、そこも抜ける。プロンプトで被写体の色を背景色から離すか、モードを変える。
- 半透明の影・ぼかしは chroma では欠けやすい。影が要る絵は不透明な落ち影にするか、影なしで生成してスライド側で影を付ける。
- 単体で `scripts/alpha.py in.jpg out.png --mode black [--trim] [--low N --high N]` としても使える。既存の平坦な画像を後から抜きたいときに。

## この環境で agy が動かないとき

このスキルはローカルにインストールされた agy を Python から起動する。Claude Desktop の PowerPoint / Word 連携や Cowork のようなサンドボックス環境では、`agy` コマンドが存在せず外部通信も遮断されているため実行できない。その場合は次のように振る舞う。

- 代わりにベクター図形や SVG を勝手に描いて済ませない。ユーザーはこのスキルを選んだ時点で Gemini の画像を求めている。
- 「この環境からは agy を起動できない」と一言で伝え、Claude Code(ターミナルまたは Desktop の Code タブ)で同じ依頼をすれば生成できること、生成した画像ファイルのパスを渡してもらえればこの環境で配置できることを案内する。
- 依頼内容(用途、アスペクト比、スタイル、保存先の希望)をそのまま Claude Code に貼れる 1 行の依頼文にまとめて渡す。

## 知っておくべき挙動

- 生成物の原本は `~/.gemini/antigravity-cli/brain/<会話ID>/<ImageName>_<timestamp>.jpg` に残る。スクリプトはそこから `--out` にコピーする(原本は削除しない)。
- agy のヘッドレスモードはファイル読み取り権限を自動拒否するが、`generate_image` と `ImagePaths` は権限なしで動く。`--dangerously-skip-permissions` は不要なので使わない。
- `agy` は `~/.local/bin/agy` にある。PATH に無い環境でもスクリプトはフォールバックする。
- agy のプロンプト引数は `-p=<text>` の形で渡す必要がある(`-p <text>` だと次のフラグをプロンプトと誤認する)。スクリプトは対応済み。
- 直接 agy を叩いて確認したいとき:

```bash
agy --output-format json --print-timeout 5m -p='Use the generate_image tool: <指示>. Then print the absolute path of the generated file.'
```

- モデル一覧は `agy models`。画像生成モデル自体は選べない(Antigravity 側が固定で、ツール定義にもモデル名は出てこない)。`--model` は指示を解釈するエージェントのモデルを変えるだけ。Google の公式発表では Antigravity で Nano Banana 2(Gemini 3.1 Flash Image)が利用可能とされており、出力は約 1K(16:9 で 1376x768、4:3 で 1200x896)、Google の C2PA 署名付き JPEG。2K/4K や特定バージョンの明示指定が必要なら、GEMINI_API_KEY を使う MCP サーバー経由に切り替える必要がある(本スキルの対象外)。

## 対象外

- SVG、Mermaid、HTML/CSS で描くべき図 → 直接書く。
- データのグラフ・チャート → dataviz スキル。
- PPTX 内の図形やレイアウト → pptx 系スキル。挿絵として画像が欲しい場合だけ本スキルで生成し、pptx 側で配置する。
