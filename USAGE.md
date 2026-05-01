# mplxe — 使い方ガイド

`mplxe` は **ルールベースのテキスト正規化ライブラリ** と、その薄い CLI フロントエンドです。
LLM を必須にせず、辞書 (synonyms) と rules.yaml に書かれたパターンだけで
業務テキストを canonical_name + attributes に変換します。

リポジトリ構成:

```
mplxe/
├── packages/
│   ├── mplxe-core/   # ライブラリ本体 (NormalizePipeline)
│   └── mplxe-cli/    # `mplxe` コマンド (typer + rich)
└── examples/
    ├── ingredients.yaml   # サンプル rules
    ├── input.csv
    └── input.json
```

---

## インストール

`uv` を使う場合 (推奨):

```bash
cd packages/mplxe-cli
uv sync --extra dev
```

これで `mplxe-cli/.venv/bin/mplxe` が利用可能になります。
`pip` で入れる場合は `mplxe-core` を先にインストールしてください。

依存:

* `mplxe-core` — pipeline 本体
* `typer>=0.12` — CLI
* `rich>=13.7` — 表示
* `rapidfuzz>=3.0` — `suggest` の類似度計算

---

## CLI コマンド一覧

```bash
mplxe --help
```

| サブコマンド | 用途 |
|---|---|
| `normalize` | 1 文字列を正規化して JSON で返す |
| `batch`     | CSV / JSON の指定列を一括正規化 |
| `explain`   | 1 文字列の処理過程を rich で詳細表示 |
| `suggest`   | 未分類 / 低 confidence / 表記揺れの **レビュー候補** を生成 (LLM 不使用) |

すべてのコマンドは `--rules <path>` で辞書 + ルール定義を読み込みます。
`<path>` は **単一の YAML ファイル** または **YAML ファイルが入ったディレクトリ** のどちらでも指定可能です。

```bash
# 単一ファイル
mplxe normalize "..." --rules examples/ingredients.yaml

# ディレクトリ — 配下の *.yaml / *.yml を再帰的に読み込み
# 各ファイルのパスから namespace が自動付与されます
#   examples/rules/ingredients/meat.yaml → namespace = "ingredients.meat"
#   examples/rules/common/amount.yaml    → namespace = "common.amount"
mplxe normalize "..." --rules examples/rules/
```

ディレクトリ指定は `mplxe-core` の `load_rules()` を呼び、複数 YAML を 1 つの
`PipelineConfig` にマージします。同じ dictionary 名を複数ファイルで宣言した場合は
ファイル横断で entries が連結されます。

---

## `normalize` — 1 件正規化

```bash
mplxe normalize "鶏もも肉 皮つき 30g" --rules examples/ingredients.yaml
```

出力 (JSON):

```json
{
  "original_text": "鶏もも肉 皮つき 30g",
  "canonical_name": "鶏肉",
  "category": "肉類",
  "attributes": { "skin": "あり", "amount": 30, "unit": "g", "part": "もも" },
  "confidence": 0.95,
  "warnings": []
}
```

`--pretty` でシンタックスハイライト付き、`--output FILE` でファイル書き出し。

---

## `batch` — CSV / JSON 一括正規化

```bash
mplxe batch examples/input.csv \
  --column name \
  --rules examples/ingredients.yaml \
  --output work/batched.csv
```

入力に対して以下の 4 カラムが追加されます:

* `canonical_name`
* `category`
* `attributes` (JSON 文字列)
* `confidence`

`--format csv|json` で出力フォーマット指定可。`--output` 省略時は stdout。

---

## `explain` — 1 件の処理過程を可視化

```bash
mplxe explain "鶏もも肉 皮つき 30g" --rules examples/ingredients.yaml
```

トークン分割 / 辞書マッチ / 適用ルール / 最終結果を rich のテーブルで表示します。
ルールチューニング時のデバッグに使ってください。

---

## `suggest` — レビュー候補を提案 (LLM 不使用)

`suggest` は **自動修正ではありません**。
人間が辞書 / ルールを改善するための「次に見るべき行」と「近い既存 canonical 候補」を吐き出すコマンドです。

> 重要: このコマンドは `rules.yaml` を **書き換えません**。
> canonical_name の自動確定もしません。LLM も呼びません。

### 2 つの入力モード

| mode | 用途 | 入力 |
|---|---|---|
| `raw` (default) | 未正規化の生データを与える | 任意の CSV / JSON |
| `review` | 既に `mplxe batch` 済みの結果を与える | `canonical_name` / `confidence` を含む CSV / JSON |

`review` モードで必要列が欠けていれば自動的に `raw` にフォールバックします。

### 基本実行

```bash
# raw mode
mplxe suggest examples/input.csv \
  --column name \
  --rules examples/ingredients.yaml \
  --output work/suggestions.csv \
  --min-score 78 \
  --low-confidence 0.75

# review mode (batch 済みファイルを入力)
mplxe batch data.csv -c name -r rules.yaml -o batched.csv
mplxe suggest batched.csv \
  -c name \
  -r rules.yaml \
  -o suggestions.json \
  -f json \
  --mode review
```

### オプション

| オプション | 既定値 | 説明 |
|---|---|---|
| `--column / -c`        | (必須) | 解析対象のカラム名 |
| `--rules / -r`         | なし | rules YAML ファイル または ディレクトリ。`raw` mode では必須、`review` では任意 (辞書類似度を有効化) |
| `--output / -o`        | stdout | 出力先 |
| `--format / -f`        | output 拡張子から推論 | `csv` / `json` |
| `--mode / -m`          | `raw`  | `raw` / `review` |
| `--min-score`          | `75`   | クラスタリング & 辞書類似度の最小スコア (0-100) |
| `--low-confidence`     | `0.7`  | この値未満の confidence をレビュー対象に含める |
| `--top-k`              | `3`    | 1 行あたりに残す辞書候補の最大件数 |
| `--verbose / -v`       | `false`| 行単位の進捗を stderr に出力 |

### 出力カラム

CSV / JSON とも以下のカラムを持ちます。

| カラム | 内容 |
|---|---|
| `cluster_id`               | 表記揺れクラスタの ID (1-based) |
| `text`                     | 対象テキスト |
| `count`                    | 入力中の出現回数 |
| `current_canonical_name`   | 現在解決されている canonical (なければ空) |
| `current_category`         | 現在の category |
| `current_confidence`       | 現在の confidence (0.0–1.0) |
| `suggestion_type`          | 該当するタグの CSV (例 `unmatched,nearest_dictionary`) |
| `nearest_canonical_name`   | 最近傍候補の canonical |
| `nearest_matched_term`     | マッチした synonym / canonical 文字列 |
| `nearest_score`            | 類似度 (0–100) |
| `candidate_json`           | 上位 K 候補の JSON 配列 |
| `reason`                   | 自然言語による理由 |

`suggestion_type` の候補:

* `unmatched` — 既存辞書にマッチしなかった
* `low_confidence` — confidence が閾値未満
* `nearest_dictionary` — 既存辞書に近い候補がある
* `possible_synonym` — synonym として追加すべき可能性
* `similar_cluster` — 同クラスタに別の未分類表現がある
* `unknown_token` — 辞書もルールも当たらない頻出トークン
* `possible_rule` — warning 付きで出ており新規 rule 候補

### サマリ表示の例

```
Suggestions generated

  Input rows            1,000
  Suggestion targets    183
  Clusters              42
  Unmatched             98
  Low confidence        85

Top clusters:
  1. 鶏もも皮付き / 鶏もも皮つき / 鶏もも皮付  (cluster #1, 43 occurrences)
  2. チキンボイル / ボイルチキン               (cluster #3, 18 occurrences)
  ...

Frequent unknown tokens:
  - 謎の食材A (12x)
  - レアカット (5x)
```

### ワークフロー例

1. `mplxe batch` で全データを正規化する
2. `mplxe suggest --mode review` で結果のレビュー候補を出力
3. `cluster_id` でグルーピングしてクラスタ単位で人間が判断
4. `nearest_canonical_name` を見て synonym を追加するか、新規 canonical を立てるか決める
5. `Frequent unknown tokens` を見て、新規 rule 候補を発見する
6. `rules.yaml` を編集して再度 batch → 改善ループ

---

## エラーハンドリング

| 状況 | 動作 |
|---|---|
| 入力ファイルが無い | exit 2、明確なエラー |
| `--column` が存在しない | exit 2、利用可能カラム一覧を表示 |
| `--rules` のパスが無い | exit 2、`rules path not found` を表示 |
| `--rules` が無い (raw mode) | exit 2、必要である旨を案内 |
| `--rules` が無い (review mode) | 辞書類似度を無効化して実行 |
| `rapidfuzz` 未インストール | exit 2、`pip install rapidfuzz` を案内 |
| `mplxe batch` で 1 行失敗 | warning を出して継続 (`suggest` も同様) |

---

## 設計思想

* **LLM を必須にしない** — `rapidfuzz` の deterministic な類似度計算と簡単な greedy clustering で実用的な提案を得られる構成。
* **自動修正しない** — `suggest` は提案生成のみ。`rules.yaml` の更新や canonical の自動確定は意図的に行わない。
* **拡張ポイントを明示** — 将来 LLM / embedding / TF-IDF を差し込めるよう、`similarity.py` / `clustering.py` にコメントで明記。

---

## `mplxe-core` への移送提案

現状 `suggest` 関連ロジックはすべて `mplxe-cli` に閉じています (`mplxe_cli/utils/similarity.py`, `mplxe_cli/utils/clustering.py`, `mplxe_cli/commands/suggest.py`)。
これは「最小スコープでまず CLI からの利用を成立させる」ための初期配置です。

ただし以下のいずれかが見えてきた段階で、コア API として `mplxe-core` 側へ昇格させることを推奨します。

### 移送候補と移送先

| 現在の場所 | 移送候補 | 移送先 (案) | 移送理由 |
|---|---|---|---|
| `mplxe_cli/utils/similarity.py`<br/>`Candidate` / `ScoredCandidate` / `find_nearest` / `build_candidates_from_config` | コア化 | `mplxe.suggest.similarity` (新モジュール) | 「PipelineConfig に対する類似度問い合わせ」は CLI でなくとも有用。Python から直接呼ぶ需要が出る。 |
| `mplxe_cli/utils/clustering.py`<br/>`greedy_cluster` | コア化 | `mplxe.suggest.clustering` | スコアラを差し替え可能にすれば backend-agnostic。CLI 以外でも使える。 |
| `mplxe_cli/commands/suggest.py` の `_enrich_rows` / `_is_target` / `_suggestion_types` / `_find_unknown_tokens` | コア化 | `mplxe.suggest.engine.SuggestEngine` | I/O と CLI 表示を分離すると Python API として `engine.suggest(rows, ...) -> list[Suggestion]` を提供できる。 |
| `mplxe_cli/commands/suggest.py` の typer 引数定義 / `_render_summary` / write_table 周り | CLI に残す | `mplxe-cli` | rich / typer / CSV-IO は CLI 固有。コア側に持ち込まない。 |

### 移送するタイミングの目安

以下のいずれかが起きたら昇格を検討してください。

1. **CLI 以外から呼びたくなった** — Web UI / バッチジョブ / Jupyter から `suggest` を Python API として直接呼びたい要望が出たとき。
2. **`LLMSuggestionProvider` と統合したくなった** — `mplxe.extensions.LLMSuggestionProvider` (既にコア側に存在) と同じ抽象境界に揃える価値が出たとき。`SuggestionProvider` プロトコルとして、deterministic provider と LLM provider を切り替えられる構造に進化させる。
3. **複数の類似度バックエンドが必要になった** — embedding / TF-IDF / rapidfuzz を差し替える需要が出たとき。`Scorer` プロトコルをコア側に置き、CLI からは default 実装を選ぶだけにする。
4. **永続化された `Suggestion` データ構造が欲しくなった** — `pydantic.BaseModel` ベースの `Suggestion` を `mplxe.models` に置き、API レスポンス / RPC で共有できるようにしたいとき。

### 推奨される移送後の構成

```
mplxe-core/src/mplxe/suggest/
├── __init__.py          # public re-exports
├── models.py            # Suggestion, Cluster, Candidate, ScoredCandidate (pydantic)
├── similarity.py        # Scorer protocol + RapidFuzzScorer 実装
├── clustering.py        # greedy_cluster + 将来の TF-IDF/embedding clustering
└── engine.py            # SuggestEngine: pipeline + scorer + clusterer の合成
```

`mplxe-cli/mplxe_cli/commands/suggest.py` 側は CLI シェル (引数パース + I/O + rich 表示) だけを担当し、ビジネスロジックは `from mplxe.suggest import SuggestEngine` で呼び出す形になります。

### 今は移送しない理由

* 利用者が CLI のみ。コア API として固める前にユースケースを観察したい。
* `Suggestion` のフィールドが安定していない。コアに持ち込むと semver 上の負債になりやすい。
* `LLMSuggestionProvider` との統合方針が未確定。先にプロトコルを決めてから移送する方が手戻りが少ない。

---

## テスト

```bash
cd packages/mplxe-cli
uv run pytest -q
```

`mplxe-core` 側にも `tests/` があるので、変更時は両方走らせてください。
