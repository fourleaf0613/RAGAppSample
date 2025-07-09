# RAGAppSample2

RAGAppSample2は、PythonおよびStreamlitを利用したRAG（Retrieval-Augmented Generation）アプリケーションのサンプルです。Azure等のクラウドサービスとの連携も想定しています。

---

## 目次

- [特徴](#特徴)
- [サンプルアプリの制限](#サンプルアプリの制限)
- [全体の流れ](#全体の流れ)
- [セットアップ手順](#セットアップ手順)
- [インデックス作成用スクリプト実行](#インデックス作成用スクリプト実行)
- [フォルダ構成](#フォルダ構成)
- [注意事項](#注意事項)
- [ライセンス](#ライセンス)
- [GitHubへのアップロード方法](#githubへのアップロード方法)

---

## 特徴

- Pythonによるバックエンド処理
- StreamlitによるWebインターフェース
- Azure等のクラウドサービスとの連携

---

## サンプルアプリの制限

本ツールで読み込みできるファイル形式は以下の通りです。

- PDF
- TXT

Document IntelligenceではMicrosoft OfficeやHTMLファイルも読み込み可能ですが、プログラムの改修が必要です。サンプルコードを変更することで他形式にも対応できます。

---

## 全体の流れ

1. 事前準備
2. Azure OpenAIリソースの作成・モデルデプロイ（GPT-4, GPT-3.5, Embedding）
3. Azure AI Searchリソースの作成
4. Azure AI Document Intelligence（旧Form Recognizer）リソースの作成
5. Azure CosmosDBリソース/DB/コンテナの作成
6. Azure Data Lake Storage Gen2（Blob Storage）リソースの作成
7. Azure App Serviceリソースの作成
8. インデックス作成用サンプルスクリプトの実行
9. Webアプリの動作確認（ローカル実行）
10. WebアプリのAzureへのデプロイ

> ※ 本アプリケーションはAzure Data Lake Storage Gen2を利用していますが、Microsoft FabricのOneLakeも利用可能です。

---

## セットアップ手順

1. リポジトリをクローン
   ```
   git clone <このリポジトリのURL>
   cd RAGAppSample2
   ```
2. Python仮想環境の作成・アクティベート
   ```
   python -m venv .venv
   # Windows
   .venv\Scripts\activate
   # macOS/Linux
   source .venv/bin/activate
   ```
3. 必要なパッケージのインストール
   ```
   pip install -r requirements.txt
   ```
4. Streamlitアプリの起動
   ```
   streamlit run <メインのPythonファイル名>.py
   ```

---

## インデックス作成用スクリプト実行

1. dataフォルダまたはストレージに検索対象ファイルを格納
2. .envファイルの環境変数を作成したリソース内容に合わせて変更
3. preparedata.py内のチャンクサイズを必要に応じて変更
4. （済の場合スキップ）仮想環境作成・有効化・ライブラリインストール
5. スクリプト実行
   ```
   python -m preparedata <オプション>
   ```
6. AI Searchのインデックス管理画面やCosmosDBのデータエクスプローラでデータ格納を確認

### preparedata.py オプション

// ...（ここにオプションの詳細を追記してください）...

---

## フォルダ構成

```
RAGAppSample2/
├── .gitignore
├── README.md
├── requirements.txt
├── <Pythonファイル>
└── ...
```

---

## 注意事項

- `.env`ファイル等の機密情報は`.gitignore`で管理されています。
- Azure等のクラウドサービス利用時は認証情報を適切に設定してください。

---

## ライセンス

MITライセンス

---

## GitHubへのアップロード方法

1. リモートリポジトリ追加
   ```
   git remote add origin https://github.com/fourleaf0613/RAGAppSample.git
   ```
2. 変更をコミット・プッシュ
   ```
   git add .
   git commit -m "初回コミット"
   git push -u origin main
   ```
> ※ 既にリモートリポジトリが設定されている場合は、`git remote set-url origin ...`でURLを変更できます。

---

## プルリクエスト（PR）の作成手順

1. 変更内容をコミットする  
   ```
   git add README.md
   git commit -m "READMEの構成を整理"
   ```

2. 新しいブランチを作成して切り替える  
   ```
   git checkout -b update-readme
   ```

3. 変更をリモートリポジトリにプッシュする  
   ```
   git push -u origin update-readme
   ```

4. GitHubのリポジトリページにアクセスし、「Compare & pull request」ボタンからPRを作成する
