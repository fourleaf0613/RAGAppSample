import os
import re
import json
from base64 import b64encode
from azure.core.credentials import AzureKeyCredential
from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.ai.documentintelligence.models import DocumentAnalysisFeature, ContentFormat
from dotenv import load_dotenv  
# 環境変数を読み込む  
load_dotenv() 

# 環境変数から Azure Document Intelligence のエンドポイントとキーを取得する
DOCUMENT_INTELLIGENCE_ENDPOINT = os.getenv("DOCUMENT_INTELLIGENCE_ENDPOINT")
DOCUMENT_INTELLIGENCE_KEY = os.getenv("DOCUMENT_INTELLIGENCE_KEY")

# Document Intelligence クライアントを生成する
credential = AzureKeyCredential(DOCUMENT_INTELLIGENCE_KEY)
client = DocumentIntelligenceClient(DOCUMENT_INTELLIGENCE_ENDPOINT, credential)


# 指定したドキュメントを Document Intelligence で OCR 処理してHTML変換して返す
def get_content_from_document(file_path):
    result = __get_ocr_result(file_path)
    result = result.as_dict()
    return __get_content_from_ocr_result(result)


# 指定したドキュメントを Document Intelligence で OCR 処理して結果を返す
def __get_ocr_result(file_path):
    with open(file_path, "rb") as f:
        poller = client.begin_analyze_document(
            "prebuilt-layout",
            analyze_request=f,
            locale="ja-JP",
            features=[DocumentAnalysisFeature.OCR_HIGH_RESOLUTION],
            output_content_format="markdown",
            content_type="application/octet-stream",
        )
    return poller.result()


# Document Intelligence で処理した結果を変換する
def __get_content_from_ocr_result(result):
    content = result['content']

    # <!--PageHeader-->、<!--PageFooter-->を削除
    content = re.sub(r'<!-- PageHeader.*?-->', '', content)
    content = re.sub(r'<!-- PageFooter.*?-->', '', content)

    return content
