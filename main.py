import streamlit as st
import boto3
import gzip
import re
from io import BytesIO
from datetime import datetime, timedelta
import pytz

# ページ幅を最大化するスタイル
st.markdown(
    """
    <style>
    .css-18e3th9, .block-container {
        padding-left: 1rem !important;
        padding-right: 1rem !important;
        max-width: 100% !important;
    }
    </style>
    """,
    unsafe_allow_html=True
)

# セッション状態の初期化
if "prefix" not in st.session_state:
    st.session_state.prefix = ""
if "selected_key" not in st.session_state:
    st.session_state.selected_key = None
if "current_text" not in st.session_state:
    st.session_state.current_text = None

# プロファイルとバケットの選択
profile = st.text_input("AWSプロファイル名を入力", "default")
try:
    session = boto3.Session(profile_name=profile)
    s3 = session.client("s3")

    buckets = s3.list_buckets()["Buckets"]
    bucket_names = [b["Name"] for b in buckets]
    bucket = st.selectbox("バケットを選択", bucket_names)

    st.write(f"📁 現在のパス: `{st.session_state.prefix}`")

    # フィルタUI（前方一致文字列 → S3 Prefixに使用）
    name_filter = st.text_input("オブジェクト名の前方一致でフィルタ（S3取得時に適用）", "")
    date_filter = st.date_input("JST日付でのフィルタ", value=None)
    time_filter = st.time_input("JST時分での±10分フィルタ", value=None)

    # オブジェクト一覧取得関数
    def list_prefixes_and_objects(bucket, base_prefix, name_filter_prefix=""):
        full_prefix = base_prefix + name_filter_prefix
        result = s3.list_objects_v2(
            Bucket=bucket,
            Prefix=full_prefix,
            Delimiter="/"
        )
        folders = [cp["Prefix"] for cp in result.get("CommonPrefixes", [])]
        files = result.get("Contents", [])
        return folders, files

    folders, files = list_prefixes_and_objects(bucket, st.session_state.prefix, name_filter)

    # 戻るボタン
    if st.session_state.prefix:
        parent_prefix = "/".join(st.session_state.prefix.strip("/").split("/")[:-1])
        parent_prefix = parent_prefix + "/" if parent_prefix else ""
        if st.button("⬅️ 1つ上のフォルダへ戻る"):
            st.session_state.prefix = parent_prefix
            st.session_state.current_text = None
            st.session_state.selected_key = None
            st.rerun()

    # サブフォルダ一覧
    st.subheader("📂 サブフォルダ")
    for folder in folders:
        name = folder[len(st.session_state.prefix):].rstrip("/")
        if st.button(f"➡ {name}", key=folder):
            st.session_state.prefix = folder
            st.session_state.current_text = None
            st.session_state.selected_key = None
            st.rerun()

    # オブジェクトフィルタリング（表示用）
    st.subheader("📄 ファイル一覧")
    filtered_files = []
    for obj in files:
        key = obj["Key"]
        if key.endswith("/"):
            continue  # フォルダ除外

        # JST変換
        jst_tz = pytz.timezone("Asia/Tokyo")
        jst_dt = obj["LastModified"].astimezone(jst_tz)
        jst_date = jst_dt.date()

        # ファイル名（prefixより後ろ）
        filename = key[len(st.session_state.prefix):]

        # JST日付でのフィルタ
        if date_filter and jst_date != date_filter:
            continue

        # JST時分±10分フィルタ
        if time_filter:
            target_dt = jst_tz.localize(datetime.combine(jst_date, time_filter))
            lower = target_dt - timedelta(minutes=10)
            upper = target_dt + timedelta(minutes=10)
            if not (lower <= jst_dt <= upper):
                continue

        filtered_files.append((key, jst_dt, filename))

    if filtered_files:
        keys = [f[2] for f in filtered_files]  # 表示名（ファイル名）
        selected_idx = st.selectbox("表示したい .gz ファイルを選択", range(len(keys)), format_func=lambda i: keys[i])
        selected_key = filtered_files[selected_idx][0]

        if selected_key != st.session_state.selected_key:
            st.session_state.current_text = None
            st.session_state.selected_key = selected_key

        if selected_key.endswith(".gz") and st.button("展開して表示"):
            obj = s3.get_object(Bucket=bucket, Key=selected_key)
            with gzip.GzipFile(fileobj=BytesIO(obj["Body"].read())) as gz:
                text = gz.read().decode("utf-8", errors="ignore")
                st.session_state.current_text = text

    else:
        st.info("条件に一致するファイルが見つかりません。")

    # 正規表現フィルタとログ表示
    if st.session_state.current_text:
        pattern = st.text_input("正規表現でフィルタ（例: Error|警告|\\tABC）", "")
        lines = st.session_state.current_text.splitlines()
        if pattern:
            try:
                filtered = [line for line in lines if re.search(pattern, line)]
            except re.error as e:
                st.error(f"正規表現エラー: {e}")
                filtered = []
        else:
            filtered = lines

        st.write(f"🔍 マッチした行: {len(filtered)} 件")

        log_text = "\n".join(filtered)
        st.markdown(
            f"""
            <div style="overflow-x: auto; white-space: pre; font-family: monospace; border: 1px solid #ddd; padding: 10px;">
                {log_text}
            </div>
            """,
            unsafe_allow_html=True
        )

except Exception as e:
    st.error(f"エラーが発生しました: {e}")
