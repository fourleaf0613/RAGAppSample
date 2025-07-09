import re
import tiktoken

# TikTokenの初期化
tiktoken_encoding = tiktoken.encoding_for_model("gpt-4")


# コンテンツをチャンクに分割する
def chunk_content(
    content: str,
    max_chunk_token_size: int,  # ex) 4096
    overlap_token_rate: float,  # ex) 0.1
    overlap_type: str,  # PREPOST | PRE | POST | NONE
):

    # 見出しでチャンクを分割する
    chunks = [content]
    for tag in ["##", "#"]:
        staging_chunks = []
        for chunk in chunks:
            if __calc_tokens(chunk) > max_chunk_token_size:
                # tagを残したままチャンクを分割
                split_chunks = __split_content_by_markdown_tag(chunk, tag)
                staging_chunks += split_chunks
            else:
                staging_chunks.append(chunk)
        chunks = staging_chunks

    # chunksの内容とそのナンバーを表示
    for i, chunk in enumerate(chunks):
        print(f"Chunk Number: {i}, Content: {chunk}")

    # 改行、句読点、スペースでチャンクを分割する
    for tag in ["\n", "。", "、", " "]:
        staging_chunks = []
        for chunk in chunks:
            if __calc_tokens(chunk) > max_chunk_token_size:
                staging_chunks += __split_content_by_delimiter(chunk, tag)
            else:
                staging_chunks.append(chunk)
        chunks = staging_chunks


    # 分割したチャンクを定義したチャンクサイズとオーバラップ設定に合わせて結合する
    chunks = __merge_chunks(chunks, max_chunk_token_size, overlap_token_rate, overlap_type)

    return chunks


# 指定したMarkdownタグでコンテンツを分割する
def __split_content_by_markdown_tag(content, tag):
    split_content = content.split(tag)
    split_content = [tag + chunk for chunk in split_content]
    return split_content

# 指定した文字列でコンテンツを分割する
def __split_content_by_delimiter(content, delimiter):
    # delimiterでテキストを分割するが、区切り文字も結果に含める
    parts = content.split(delimiter)

    # 最後の要素以外、分割された各部分の末尾にdelimiterを再度追加
    result = [part + delimiter for part in parts[:-1] if len(part) > 0]  # 最後の要素を除いた全ての要素に対して実行

    # 最後の要素が空でなければ、それも結果リストに追加
    if parts[-1]:
        result.append(parts[-1])

    return result


# 分割したチャンク同士を指定した chunk_token_size に合わせて適切なサイズに結合する
def __merge_chunks(chunks, max_chunk_token_size, overlap_token_rate, overlap_type="PREPOST"):

    # 入力されたチャンクを全て結合したもののトークン数が最大チャンクトークン数以下の場合は全て結合して返す
    # (無駄にオーバラップ処理を行わないための処理)
    total_tokens = __calc_tokens("".join(chunks))
    if total_tokens <= max_chunk_token_size:
        return ["".join(chunks)]

    # オーバラップ設定に合わせてオーバラップトークン数を計算する
    overlap_token_size = int(max_chunk_token_size * overlap_token_rate)

    # 最大チャンクサイズをオーバラップ設定に合わせて調整する
    if overlap_type == "PRE" or overlap_type == "POST":
        chunk_token_size = max_chunk_token_size - overlap_token_size
    elif overlap_type == "PREPOST":
        chunk_token_size = max_chunk_token_size - overlap_token_size * 2
    else:
        chunk_token_size = max_chunk_token_size

    processed_chunks = []
    staging_chunk = ""
    pre_overlap_chunk = ""
    post_overlap_chunk = ""
    for i in range(0, len(chunks)):
        # ステージングチャンクと処理対象のチャンクのトークン数を計算する
        chunk = chunks[i]
        staging_chunk_tokens = __calc_tokens(staging_chunk)
        chunk_tokens = __calc_tokens(chunk)

        # 指定トークン数を超える場合は、前後オーバラップ分を作成＆付与してチャンクとして確定する
        if staging_chunk_tokens + chunk_tokens > chunk_token_size:

            # 後オーバラップ分を作成
            if overlap_type == "POST" or overlap_type == "PREPOST":
                post_overlap_chunk = ""
                for j in range(i, len(chunks)):
                    overlap_chunk = chunks[j]
                    overlap_chunk_tokens = __calc_tokens(overlap_chunk)
                    post_overlap_chunk_tokens = __calc_tokens(post_overlap_chunk)
                    if overlap_chunk_tokens + post_overlap_chunk_tokens > overlap_token_size:
                        break
                    post_overlap_chunk += overlap_chunk

            # ステージングチャンクに前後オーバラップ分を付与してチャンクとして確定する
            processed_chunk = pre_overlap_chunk + staging_chunk + post_overlap_chunk
            processed_chunks.append(processed_chunk)
            staging_chunk = chunk

            # 前オーバラップ分を作成
            if overlap_type == "PRE" or overlap_type == "PREPOST":
                pre_overlap_chunk = ""
                for j in range(i - 1, 0, -1):
                    overlap_chunk = chunks[j]
                    overlap_chunk_tokens = __calc_tokens(overlap_chunk)
                    pre_overlap_chunk_tokens = __calc_tokens(pre_overlap_chunk)
                    if overlap_chunk_tokens + pre_overlap_chunk_tokens > overlap_token_size:
                        break
                    pre_overlap_chunk = overlap_chunk + pre_overlap_chunk
        else:
            # 指定トークン数を超えない場合は、ステージングチャンクに追加する
            staging_chunk += chunk

    # 最後のチャンクに前オーバラップ分を付与してチャンクとして確定する
    processed_chunk = pre_overlap_chunk + staging_chunk
    processed_chunks.append(processed_chunk)

    return processed_chunks


# 指定した文字列のトークン数を計算する
def __calc_tokens(s):
    return len(tiktoken_encoding.encode(s))
