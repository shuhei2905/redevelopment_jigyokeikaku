# 事業計画シミュレーター

不動産開発プロジェクトの事業収支をシミュレーションするStreamlitアプリです。

## デプロイ手順

### 1. GitHubリポジトリの作成

1. [GitHub](https://github.com/)にログイン
2. 新しいリポジトリを作成（例: `biz-plan-simulator`）
3. 以下のファイルをアップロード:
   - `zigyokeikaku.py`
   - `requirements.txt`
   - `.gitignore`

### 2. Streamlit Community Cloudでデプロイ

1. [Streamlit Community Cloud](https://share.streamlit.io/)にアクセス
2. 「Continue with GitHub」でログイン
3. 「Create app」をクリック
4. リポジトリを選択
5. Main file path に `zigyokeikaku.py` を指定
6. 「Deploy!」をクリック

### 注意事項

- SQLiteデータベースを使用しているため、アプリ再起動時にデータが消える可能性があります
- 本番運用する場合は、外部データベース（Streamlit Postgres、Google Sheetsなど）への移行を検討してください

## ローカルでの実行方法

```bash
# 必要なライブラリをインストール
pip install -r requirements.txt

# アプリを起動
streamlit run zigyokeikaku.py
```

## 機能

- 地権者データの入力・編集
- 事業収支の自動計算
- 利益率や出口グロスの可視化
- プロジェクトの保存・読込機能
