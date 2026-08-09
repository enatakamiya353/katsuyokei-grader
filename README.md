# 活用形マークシート採点サイト

国語「活用の種類・活用形」マークシートテスト（20問・4/5/6択混在）の採点ウェブアプリ。
解答用紙のスキャン画像（またはPDF）をアップロードすると、自動で採点し、
○×付きの採点済み画像と点数を返す。

## ローカルで動かす

```bash
pip install -r requirements.txt
python app.py
```

ブラウザで http://127.0.0.1:8016 を開く。

## Renderへのデプロイ

このリポジトリには `render.yaml` を同梱済み。Renderダッシュボードで
「New +」→「Blueprint」からこのGitHubリポジトリを選ぶと、
`render.yaml` の内容に沿って自動設定される。

手動でWeb Serviceを作る場合は以下を設定する。

| 項目 | 値 |
|---|---|
| Runtime | Python 3 |
| Build Command | `pip install -r requirements.txt` |
| Start Command | `gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --timeout 120` |
| Plan | Free |

## 構成

- `app.py` — Flask APIサーバー（`/`でindex.html配信、`/api/grade`で採点、`/api/answer_key`で解答一覧）
- `grade_katsuyokei20.py` — 採点ロジック本体（マーク位置検出・濃さ判定など）
- `mark.pdf` — 解答用紙のマーク位置座標を抽出するための基準PDF（採点時に必要、実行時に読み込む）
- `answer_key.json` — 正解データ
- `index.html` — フロントエンド（アップロード・結果表示・CSV出力）

## 注意

`/api/answer_key` は認証なしで正解を返すエンドポイント。採点済み答案の確認用途を想定しており、
現状はアクセス制限を設けていない。

## バージョン管理

サイトは常に最新バージョンの問題のみを採点する（旧バージョンとの併用はしない）。
問題を更新したら `mark.pdf` と `answer_key.json` を新しいものに差し替えてコミットし、
差し替え前の状態には `vX.Y` のgitタグを付けてから上書きする。過去バージョンの復元は
`git checkout vX.Y` で可能。

- `v1.0` — 初版（20問）
- 現行（タグなし = HEAD） — Ver.2.0（20問、同一形式で問題内容を刷新）
