# RAGAppSample2

RAGAppSample2は、PythonおよびStreamlitを利用したRAG（Retrieval-Augmented Generation）アプリケーションのサンプルです。

## 特徴

- Pythonによるバックエンド処理
- StreamlitによるWebインターフェース
- Azure等のクラウドサービスとの連携も想定

## セットアップ

1. リポジトリをクローンします。

   ```
   git clone <このリポジトリのURL>
   cd RAGAppSample2
   ```

2. Python仮想環境を作成し、アクティベートします。

   ```
   python -m venv .venv
   # Windowsの場合
   .venv\Scripts\activate
   # macOS/Linuxの場合
   source .venv/bin/activate
   ```

3. 必要なパッケージをインストールします。

   ```
   pip install -r requirements.txt
   ```

4. Streamlitアプリを起動します。

   ```
   streamlit run <メインのPythonファイル名>.py
   ```

## フォルダ構成

```
RAGAppSample2/
├── .gitignore
├── README.md
├── requirements.txt
├── <Pythonファイル>
└── ...
```

## 注意事項

- `.env`ファイルなどの機密情報は`.gitignore`で管理されています。
- Azure等のクラウドサービスを利用する場合は、各種認証情報を適切に設定してください。

## ライセンス

このプロジェクトはMITライセンスの下で公開されています。

## GitHubへのアップロード方法

このプロジェクトを  
[https://github.com/fourleaf0613/RAGAppSample](https://github.com/fourleaf0613/RAGAppSample)  
にアップロードするには、以下の手順を実行してください。

1. リモートリポジトリを追加します。

   ```
   git remote add origin https://github.com/fourleaf0613/RAGAppSample.git
   ```

2. 変更をコミットし、プッシュします。

   ```
   git add .
   git commit -m "初回コミット"
   git push -u origin main
   ```

   ※ 既にリモートリポジトリが設定されている場合は、`git remote set-url origin ...`でURLを変更できます。
