import os
import re
import json
import logging
import random
import string
import tempfile
from datetime import datetime
from openai import AzureOpenAI
from dotenv import load_dotenv
# 環境変数を読み込む
load_dotenv()

import streamlit as st
from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.models import VectorizedQuery
from azure.cosmos import PartitionKey
from azure.cosmos.cosmos_client import CosmosClient
from azure.storage.blob import BlobServiceClient

# 他のスクリプトから関数をインポート
from preparedata import process_file

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

# 環境変数から Azure Cosmos DB の接続文字列とデータベース名を取得する
COSMOS_CONNECTION_STRING = os.getenv("COSMOS_CONNECTION_STRING")
COSMOS_DB_NAME = os.getenv("COSMOS_DB_NAME")
COSMOS_CONTAINER_NAME_CHAT = os.getenv("COSMOS_CONTAINER_NAME_CHAT")

# Cosmos DB クライアントを生成する
cosmos_client = CosmosClient.from_connection_string(COSMOS_CONNECTION_STRING)
database = cosmos_client.get_database_client(COSMOS_DB_NAME)
database.create_container_if_not_exists(
    id=COSMOS_CONTAINER_NAME_CHAT,
    partition_key=PartitionKey(path=f"/id"),
)
container = database.get_container_client(COSMOS_CONTAINER_NAME_CHAT)

# Azure AI Search の情報を環境変数から取得する
AI_SEARCH_ENDPOINT = os.getenv("AI_SEARCH_ENDPOINT")
AI_SEARCH_KEY = os.getenv("AI_SEARCH_KEY")
AI_SEARCH_API_VERSION = os.getenv("AI_SEARCH_API_VERSION", "2023-10-01-Preview")
AI_SEARCH_INDEX_NAME = os.getenv("AI_SEARCH_INDEX_NAME")
AI_SEACH_SEMANTIC = os.getenv("AI_SEACH_SEMANTIC")
top_k_temp = 10  # 検索結果の上位何件を表示するか

# Azure Blob Storage の情報を環境変数から取得する
BLOB_STORAGE_CONNECTION_STRING = os.getenv("BLOB_STORAGE_CONNECTION_STRING")
BLOB_CONTAINER_NAME = os.getenv("BLOB_CONTAINER_NAME")

# Blob Storage クライアントを作成
blob_service_client = BlobServiceClient.from_connection_string(BLOB_STORAGE_CONNECTION_STRING)
blob_container_client = blob_service_client.get_container_client(BLOB_CONTAINER_NAME)
# コンテナが存在しない場合は作成
try:
    blob_container_client.get_container_properties()
except Exception:
    blob_container_client.create_container()

# OpenAIへのプロンプト設計を行う。
SystemPrompt = """あなたは、会社の従業員が社内のナレッジやドキュメントに対する質問をする際に支援する優秀なアシスタントです。
以下の制約を必ず守ってユーザの質問に回答してください。
ハルシネーションは起こさないでください。
魅力的で丁寧な回答をする必要があります。
最初から最後までじっくり読んで回答を作ってください。最高の仕事をしましょう

# 制約 
・以下のSources(情報源)に記載されたコンテキストのみを使用して回答してください。必ず情報源に記載されたコンテキストを基に回答を作ってください
・十分な情報がない場合は、わからないと回答してください。
・以下のSources(情報源)を使用しない回答は生成しないでください 。回答には役割(userやassistantなど)の情報を含めないでください。
・ユーザーの質問が不明瞭な場合は、明確化のためにユーザに質問してください。
・Sourcesには、名前の後にコロンと実際の情報が続きます。回答で使用する各事実について、常にSourcesの情報を含めてください。
  情報源を参照するには、各Content情報の前段にあるfilenameの情報を反映してください。角かっこを使用してください。
  Sources参照ルール：[filename] 　Sources出力例：[info1.txt]
・Sourcesを組み合わせないでください。各Sourcesを個別にリストしてください。例：[info1.txt],[info1.txt]
・日本語の質問の場合は、日本語で回答を作成してください。英語での質問の場合は、英語で回答を作成し回答してください。    
"""

# Function to generate embeddings for title and content fields, also used for query embeddings
def generate_embeddings(text, text_limit=7000):
    # Clean up text (e.g. line breaks, )
    text = re.sub(r'\s+', ' ', text).strip()
    text = re.sub(r'[\n\r]+', ' ', text).strip()
    # Truncate text if necessary
    if len(text) > text_limit:
        logging.warning("Token limit exceeded maximum length, truncating...")
        text = text[:text_limit]

    response = client.embeddings.create(model=AZURE_OPENAI_EMBED_MODEL, input=text)
    embeddings = response.data[0].embedding
    return embeddings

def query_vector_index(index_name, query, searchtype, top_k_parameter):
    vector = generate_embeddings(query)
    search_client = SearchClient(AI_SEARCH_ENDPOINT, index_name, AzureKeyCredential(AI_SEARCH_KEY))
    vector_query = VectorizedQuery(vector=vector, fields="contentVector")
    # searchtypeがvector_onlyの場合は、search_textをNoneにする
    if searchtype == "Vector_only":
        search_text = None
    # searchtypeがvector_only以外の場合は、search_textにqueryを設定する
    else:
        search_text = query

    # searchtypeがvector_onlyもしくはHybridの場合
    if searchtype == "Vector_only" or searchtype == "Hybrid":
        results = search_client.search(search_text=search_text, vector_queries=[vector_query], top=int(top_k_parameter))
    # searchtypeがFullの場合
    else:
        results = search_client.search(search_text=search_text, vector_queries=[vector_query], top=int(top_k_parameter),
                                       query_type='semantic', semantic_configuration_name=AI_SEACH_SEMANTIC)

    return results

# chat履歴を Cosmos DB に保存する
def add_to_cosmos(item):
    container.upsert_item(item)

def randomname(n):
    randlst = [random.choice(string.ascii_letters + string.digits) for i in range(n)]
    return ''.join(randlst)

def upload_file_to_blob_storage(uploaded_file):
    blob_client = blob_container_client.get_blob_client(uploaded_file.name)
    blob_client.upload_blob(uploaded_file.getbuffer(), overwrite=True)
    print(f"Uploaded {uploaded_file.name} to Blob Storage.")

def download_file_from_blob_storage(file_name):
    blob_client = blob_container_client.get_blob_client(file_name)
    download_file_path = os.path.join(tempfile.gettempdir(), file_name)
    with open(download_file_path, "wb") as download_file:
        download_data = blob_client.download_blob()
        download_data.readinto(download_file)
    print(f"Downloaded {file_name} from Blob Storage to {download_file_path}.")
    return download_file_path

def process_uploaded_file(uploaded_file, index_name):
    # ファイルをBlob Storageにアップロード
    upload_file_to_blob_storage(uploaded_file)

    # Blob Storageからファイルをダウンロード
    downloaded_file_path = download_file_from_blob_storage(uploaded_file.name)

    # Args クラスを定義
    class Args:
        def __init__(self):
            self.blob = None

    # args をインスタンス化し、blob を設定
    args = Args()
    args.blob = 1  # または適切な値

    # ファイルを処理
    process_file(downloaded_file_path, index_name, args)

    # ダウンロードした一時ファイルを削除
    os.remove(downloaded_file_path)

    # アップロード済みフラグを設定
    st.session_state['file_processed'] = True

def main():
    # Set page title and icon
    st.set_page_config(page_title="RAG App", page_icon="💬", layout="wide")

    # Display title
    st.markdown("# RAG App")

    # Display explanation in sidebar
    st.sidebar.header("Sample RAG App")
    st.sidebar.markdown("RAGを検証するサンプルアプリケーション")

    # セッションIDの初期化
    if "session_id" not in st.session_state:
        st.session_state['session_id'] = randomname(10)

    # チャット履歴の初期化
    if "messages" not in st.session_state:
        st.session_state['messages'] = []

    # ファイル処理済みフラグの初期化
    if 'file_processed' not in st.session_state:
        st.session_state['file_processed'] = False

    # クリアボタンを押した場合、チャットとst.text_input,promptallをクリアする。
    if st.sidebar.button("Clear Chat"):
        st.session_state['messages'] = []
        promptall = ""
        # 新しいセッションIDを生成して保存
        st.session_state['session_id'] = randomname(10)
        # ファイル処理済みフラグをリセット
        st.session_state['file_processed'] = False
        # アプリを再実行してウィジェットをリセット
        st.rerun()
        
    # インデックスの名前をテキストボックスで指定する。indexnameの設定
    indexname = st.sidebar.text_input("インデックス名", AI_SEARCH_INDEX_NAME)

    # ファイルアップロード機能を追加
    st.sidebar.markdown("### ファイルアップロード")
    file_uploader_placeholder = st.sidebar.empty()

    if not st.session_state['file_processed']:
        with file_uploader_placeholder:
            uploaded_file = st.file_uploader("ファイルをアップロードしてください", type=['pdf', 'txt'])
            if uploaded_file is not None:
                with st.spinner('ファイルを処理しています...'):
                    process_uploaded_file(uploaded_file, indexname)
                st.success(f"ファイル '{uploaded_file.name}' の処理が完了しました")
                st.session_state['file_processed'] = True
                # ファイルアップローダーを削除
                file_uploader_placeholder.empty()
                st.rerun()
    else:
        st.sidebar.write("ファイルは処理済みです。'Clear Chat'ボタンを押してリセットできます。")

    # Set Search parameters in sidebar
    st.sidebar.markdown("### Search Parameters")

    # 検索結果の上位何件を対象とするかを設定する。top_k_parameterの設定。テキストボックスで指定する。
    top_k_parameter = st.sidebar.text_input("検索結果対象ドキュメント数", str(top_k_temp))

    # 検索のタイプを選択する。vector_only or Hybrid or Fullの選択。1つの選択可能
    search_type = st.sidebar.radio("検索タイプ", ("Semantic_Hybrid", "Vector_only", "Hybrid"))


    # Set ChatGPT parameters in sidebar
    st.sidebar.markdown("### ChatGPT Parameters")
    Temperature_temp = st.sidebar.slider("Temperature", 0.0, 1.0, 0.0, 0.01)

    # SystemRoleを入力ボックスで指定する
    SystemRole = st.sidebar.text_area("System Role", SystemPrompt)

    # チャット履歴の表示
    messages = st.session_state.get('messages', [])
    for message in messages:
        # roleがassistantだったら、assistantのchat_messageを使う
        if message['role'] == 'assistant':
            with st.chat_message('assistant'):
                st.markdown(message['content'])
        # roleがuserだったら、userのchat_messageを使う
        elif message['role'] == 'user':
            with st.chat_message('user'):
                st.markdown(message['content'])
        else:  # 何も出力しない
            pass

    # Add system role to session state
    if SystemRole:
        # 既にroleがsystemのメッセージがある場合は、追加しない。ない場合は追加する。
        if not any(message["role"] == "system" for message in st.session_state.messages):
            st.session_state.messages.append({"role": "system", "content": SystemRole})

    # Azure AI Search のクライアントを作成する
    credential = AzureKeyCredential(AI_SEARCH_KEY)
    index_client = SearchIndexClient(
        endpoint=AI_SEARCH_ENDPOINT,
        credential=credential,
        api_version=AI_SEARCH_API_VERSION,
    )

    # ユーザからの入力を取得する
    if user_input := st.chat_input("プロンプトを入力してください"):
        # 検索する。search_fieldsはcontentを対象に検索する
        results = query_vector_index(indexname, user_input, search_type, top_k_parameter)

        # 変数を初期化する
        prompt_source = ""
        sourcetemp = []

        with st.chat_message("user"):
            st.markdown(user_input)

        # st.session_state.messagesの内容を平文にして、conversion_historyに代入する。RoleがSystemの場合は、代入しない。
        # 各messageのcontentを改行して表示する。roleもわかるように代入する
        conversion_history = ""
        for message in st.session_state.messages:
            if message['role'] == 'system':
                pass
            else:
                conversion_history += message['role'] + ": " + message['content'] + "\n\n"

        # resultsから各resultの結果を変数prompt_sourceに代入する。filepathとcontentの情報を代入する。
        for result in results:
            Score = result['@search.score']
            filename = result['fileName'] + "-" + str(result['chunkNo'])
            chunkNo = result['chunkNo']
            content = result['content']
            title = result['title']
            Keywords = result['keywords']

            # 変数prompt_sourceに各変数の値を追加する
            prompt_source += f"## filename: {filename}\n\n  ### score: {Score}\n\n  ### content: \n\n {content}\n\n"

            # filename, title, contentの内容をmarkdown形式でsourcetemp配列に格納する
            # sourcetempはresultの内容が変わる度に配列を変更する
            sourcetemp.append(f"## filename: {filename}\n\n  ### title: {title}\n\n  ### content: \n\n {content}\n\n")

        # プロンプトを作成する
        promptall = SystemRole + "\n\n# Sources(情報源): \n\n" + prompt_source + "# 今までの会話履歴：\n\n" + conversion_history + "# 回答の生成\n\nそれでは、制約を踏まえて最高の回答をしてください。あなたならできる！"
        st.session_state.messages.append({"role": "user", "content": user_input})

        # expanderを作成する
        with st.sidebar.expander("プロンプトの表示"):
            # マークダウンを表示する
            st.markdown(promptall)

        #Json形式のmessagestemp変数にroleをuserとして、promptallを代入する
        messagestemp = []
        messagestemp.append({"role": "system", "content": promptall})
        messagestemp.append({"role": "user", "content": user_input})

        with st.chat_message("assistant"):
            output = client.chat.completions.create(
                model=AZURE_OPENAI_CHAT_MODEL,
                messages=messagestemp,
                temperature=Temperature_temp,
                max_tokens=AZURE_OPENAI_CHAT_MAX_TOKENS,
                stream=True,
            )
            response = st.write_stream(output)


            #output内に[]形式がある場合は、[]内のファイル名を取得し、sourcetemp内のfilenameと一致するものを探索する
            #一致するものがあれば、sourcetemp内の内容を表示する。既に1回表示されている場合は、2回目以降は表示しない
            with st.expander("参照元"):
                displayed_files = []  # 既に表示されたファイル名を追跡するためのリスト
                if "[" in response:
                    filename = re.findall(r'\[(.*?)\]', response)
                    for i in range(len(filename)):
                        for j in range(len(sourcetemp)):
                            if filename[i] in sourcetemp[j] and filename[i] not in displayed_files:  # ファイル名が既に表示されていないことを確認
                                with st.popover(filename[i]):
                                    st.write(sourcetemp[j])
                                displayed_files.append(filename[i])  # ファイル名を追跡リストに追加
                else:
                    pass

        # Add ChatGPT response to conversation
        st.session_state.messages.append({"role": "assistant", "content": response})

        # idにはランダム値を挿入する
        id1 = randomname(20)
        id2 = randomname(20)
        id3 = randomname(20)
        id4 = randomname(20)
        

        # チャット履歴を Cosmos DB に保存する。
        add_to_cosmos({"id": id1, "session": st.session_state['session_id'], "role": "user", "content": user_input})
        add_to_cosmos({"id": id2, "session": st.session_state['session_id'], "role": "assistant", "content": response})
        add_to_cosmos({"id": id3, "session": st.session_state['session_id'], "role": "context", "content": prompt_source}) 
        add_to_cosmos({"id": id4, "session": st.session_state['session_id'], "role": "eval", "question": user_input, "answer": response, "context": prompt_source, "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}) 
        
if __name__ == '__main__':
    main()
