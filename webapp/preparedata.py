import json
import re
import os
import hashlib
import argparse
from base64 import urlsafe_b64encode
from openai import AzureOpenAI
from dotenv import load_dotenv
# 環境変数を読み込む
load_dotenv()
import requests
from dococr.parse_doc import get_content_from_document
from dococr.create_chunks import chunk_content
from azure.core.exceptions import ResourceNotFoundError
from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from azure.cosmos import PartitionKey
from azure.cosmos.cosmos_client import CosmosClient
from azure.storage.blob import BlobServiceClient, ContainerClient

max_chunk_token_size = 2048
overlap_token_rate = 0
overlap_type = "NONE"  # PREPOST | PRE | POST | NONE

# envファイルから環境変数を取得
client = AzureOpenAI(
    azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
    api_key=os.getenv("AZURE_OPENAI_API_KEY"),
    api_version=os.getenv("AZURE_OPENAI_API_VERSION")
)

# Azure OpenAI Service の情報を環境変数から取得する
AZURE_OPENAI_CHAT_MODEL = os.getenv("AZURE_OPENAI_CHAT_MODEL")
AZURE_OPENAI_EMBED_MODEL = os.getenv("AZURE_OPENAI_EMBED_MODEL")
AZURE_OPENAI_CHAT_MAX_TOKENS = int(os.getenv("AZURE_OPENAI_CHAT_MAX_TOKENS", "1000"))

# Azure AI Search の情報を環境変数から取得する
AI_SEARCH_ENDPOINT = os.getenv("AI_SEARCH_ENDPOINT")
AI_SEARCH_KEY = os.getenv("AI_SEARCH_KEY")
AI_SEARCH_API_VERSION = os.getenv("AI_SEARCH_API_VERSION", "2023-10-01-Preview")

# Azure AI Search のクライアントを作成する
credential = AzureKeyCredential(AI_SEARCH_KEY)
index_client = SearchIndexClient(
    endpoint=AI_SEARCH_ENDPOINT,
    credential=credential,
)

# 環境変数から Azure Cosmos DB の接続文字列とデータベース名を取得する
COSMOS_CONNECTION_STRING = os.getenv("COSMOS_CONNECTION_STRING")
COSMOS_DB_NAME = os.getenv("COSMOS_DB_NAME")
COSMOS_CONTAINER_NAME_KB = os.getenv("COSMOS_CONTAINER_NAME_KB")

# Cosmos DB クライアントを生成する
cosmos_client = CosmosClient.from_connection_string(COSMOS_CONNECTION_STRING)
database = cosmos_client.get_database_client(COSMOS_DB_NAME)
database.create_container_if_not_exists(
    id=COSMOS_CONTAINER_NAME_KB,
    partition_key=PartitionKey(path=f"/id"),
)
container = database.get_container_client(COSMOS_CONTAINER_NAME_KB)

# Azure Blob Storage の情報を環境変数から取得する
BLOB_STORAGE_CONNECTION_STRING = os.getenv("BLOB_STORAGE_CONNECTION_STRING")
BLOB_CONTAINER_NAME = os.getenv("BLOB_CONTAINER_NAME")
USE_BLOB_STORAGE = os.getenv("USE_BLOB_STORAGE")

# Blob Storage クライアントを作成
blob_service_client = BlobServiceClient.from_connection_string(BLOB_STORAGE_CONNECTION_STRING)
blob_container_client = blob_service_client.get_container_client(BLOB_CONTAINER_NAME)

# ドキュメントの要約、キーワードを抽出する関数
def get_info(context):

    # systemコンテキストを定義
    system_context = """あなたは優秀なアシスタントです。社内にあるドキュメントの内容を読み解き、わかりやすく要約し、キーワードを抽出します。\
ナレッジベースを作成して、RAGに活用していきます。以下の制約条件と形式を守って、JSON形式で出力してください。\
###制約条件\
- 与えられるコンテキストは、ドキュメントをチャンクした文章です。与えられたチャンクの部分を要約し、summaryの値として出力します。要約した内容には、重要なキーワードは含めるようにしてください。\
- 与えられたチャンクの文章に対して1文でタイトルを付与します。titleの値として出力します。 \
- 本チャンク内で検索に活用する重要なキーワードを抽出する。キーワードは25個以内とします \
- 出力形式を守ります \
###出力形式\
summary: <チャンクした部分を要約した内容>\
title: <チャンクした部分のタイトル>\
Keywords: ["keyword1", "Keyword2", ...]  """

    # ユーザリクエストを定義
    user_request = "以下のコンテキストから制約条件と出力形式を必ず守って、JSON形式で出力をしてください。最初から最後まで注意深く読み込んでください。\
最高の仕事をしましょう。あなたならできる！\
###コンテキスト" + str(context)

    #Json配列を作成
    messages = []
 
    #messagesに要素を追加
    messages.append({"role": "system", "content": system_context})
    messages.append({"role": "user", "content": user_request})

    response = client.chat.completions.create(
        model=AZURE_OPENAI_CHAT_MODEL, 
        messages=messages,
        temperature=0.0,
        max_tokens=AZURE_OPENAI_CHAT_MAX_TOKENS,
        response_format={ "type": "json_object" },
    )

    print(response.choices[0].message.content)
 
    # Convert the content from JSON string to dictionary
    content = json.loads(response.choices[0].message.content)
    
    # Extract information from the content
    doc_info = {}
    doc_info['title'] = content['title']
    doc_info['summary'] = content['summary']
    doc_info['Keywords'] = content['Keywords']
    
    
    return doc_info

# Azure OpenAI Service によるベクトル生成
def get_vector(content):
    resp = client.embeddings.create(model=AZURE_OPENAI_EMBED_MODEL, input=content)
    return resp.data[0].embedding

# インデックスが存在するか確認する
def check_index_exists(name):
    try:
        index_client.get_index(name)
        return True
    except ResourceNotFoundError:
        return False

# インデックスを削除する
def delete_index(name):
    index_client.delete_index(name)

# インデックスを作成する
def create_index(name, json_file_path):
    with open(json_file_path, "r", encoding='utf-8') as f:
        data = json.load(f)
    data["name"] = name
    resp = requests.post(
        f"{AI_SEARCH_ENDPOINT}/indexes?api-version={AI_SEARCH_API_VERSION}",
        data=json.dumps(data),
        headers={"Content-Type": "application/json", "api-key": AI_SEARCH_KEY},
    )
    if not str(resp.status_code).startswith("2"):
        raise Exception(resp.text)  # 2xx 以外の場合はエラー
    return resp.status_code

# インデックスにドキュメントを追加する
def add_documents(index_name, docs):
    search_client = SearchClient(
        endpoint=AI_SEARCH_ENDPOINT,
        credential=credential,
        index_name=index_name,
    )
    search_client.upload_documents(documents=docs)

# Cosmos DB にドキュメントを追加する
def add_to_cosmos(item):
    container.upsert_item(item)

def process_file(file_path, index_name=None, args=None):
    print("process file:", file_path)

    if index_name is None:
        index_name = os.getenv("AI_SEARCH_INDEX_NAME")

    # ファイルがBlob Storageに存在するか確認。--blobオプションが指定されている場合のみ
    print("use_blob_storage:", USE_BLOB_STORAGE)
    download_file_path = file_path
    if USE_BLOB_STORAGE and args.blob:
        # ファイル名からBlobを取得
        blob_client = blob_container_client.get_blob_client(os.path.basename(file_path))
        download_file_path = os.path.join(os.getcwd(), os.path.basename(file_path))
        with open(download_file_path, "wb") as download_file:
            download_data = blob_client.download_blob()
            download_data.readinto(download_file)
        print(f"Downloaded {file_path} from Blob Storage to {download_file_path}.")

    # PDFファイルの場合、ドキュメントからテキストを抽出
    if download_file_path.endswith(".pdf"):
        # ドキュメントから Document Intelligence でテキストを抽出する
        print("extract content from document: ", download_file_path)
        content = get_content_from_document(download_file_path)

        # 抽出したテキストをチャンク分割
        print("chunk content:")
        chunks = chunk_content(content, max_chunk_token_size, overlap_token_rate, overlap_type)
    # txtファイルの場合、テキストを読み込む
    elif download_file_path.endswith(".txt"):
        with open(download_file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        chunks = [content]
    # その他のファイルの場合、エラーメッセージを表示
    else:
        print("unsupported file format:", download_file_path)
        return

    # ダウンロードした一時ファイルを削除。--blobオプションの場合のみ削除
    if USE_BLOB_STORAGE and args.blob:
        os.remove(download_file_path)


    # 各チャンクに対して情報を付与
    file_name = os.path.basename(file_path)
    index_docs = []
    for chunk_no, chunk in enumerate(chunks):
        print("enrichment chunk:", f"{chunk_no+1}/{len(chunks)}")
        docinfo = get_info(chunk)
        id_base = f"{file_name}_{chunk_no}"
        id_hash = hashlib.sha256(id_base.encode('utf-8')).hexdigest()
        index_doc = {
            "id": id_hash,
            "fileName": os.path.basename(file_path),
            "chunkNo": chunk_no,
            "content": chunk,
            "title": docinfo['title'],
            "summary": docinfo['summary'],
            "keywords": docinfo['Keywords'],
            "contentVector": get_vector(docinfo['summary']),
        }

        index_docs.append(index_doc)

        # Cosmos DB にドキュメントを追加
        print("add to cosmos db")
        add_to_cosmos(index_doc)

    # Azure AI Search にインデックスを作成
    if not check_index_exists(index_name):
        print("create index:", index_name)
        create_index(index_name, "index.json")

    # インデックスにドキュメントを追加
    print("upload documents to index:", index_name)
    add_documents(index_name, index_docs) 

def main():
    parser = argparse.ArgumentParser(description='Process files for RAG application.')
    parser.add_argument('--file', type=str, help='Path to the file to process.')
    parser.add_argument('--dir', type=str, help='Path to the directory containing files to process.')
    parser.add_argument('--blob', action='store_true', help='Process all files in Blob Storage.')
    parser.add_argument('--index', type=str, help='Name of the Azure Cognitive Search index.')

    args = parser.parse_args()

    index_name = args.index if args.index else os.getenv("AI_SEARCH_INDEX_NAME")

    if args.file:
        process_file(args.file, index_name, args)
    elif args.dir:
        for root, dirs, files in os.walk(args.dir):
            for file in files:
                file_path = os.path.join(root, file)
                process_file(file_path, index_name, args)
    elif args.blob:
        # Blob Storage内の全てのファイルを処理
        print("Processing all files in Blob Storage...")
        blob_list = blob_container_client.list_blobs()
        for blob in blob_list:
            process_file(blob.name, index_name, args)
    else:
        print("Please specify a file, directory, or use --blob to process files from Blob Storage.")
        parser.print_help()

if __name__ == "__main__":
    main()
