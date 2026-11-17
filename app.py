"""AIメモリ手帳（Streamlit UI）

起動: streamlit run app.py
会話サンプル（または自分で入力した発話）から抽出されたメモリ候補をカードで表示し、
分類（scope）の変更・文面の編集・承認・削除ができる。
承認済みメモリだけを使った夕食提案を、使ったメモリの理由つきで表示する。
"""

import streamlit as st

from memory_logic import (
    SCOPE_LABELS,
    MemoryCandidate,
    classify_utterance,
    propose_dinner,
    run_evaluation,
)

SAMPLE_CONVERSATION = [
    "チョコレートが大好きで、いつも甘いものを選ぶ",
    "しそが苦手で絶対に食べられない",
    "今日は胃が疲れているから軽めのものがいい",
    "辛いものも好きかもしれないけど自信がない",
    "牛乳を買ってきて",
]

SCOPE_KEYS = list(SCOPE_LABELS.keys())

st.set_page_config(page_title="AIメモリ手帳", page_icon="📝")
st.title("AIに何を覚えさせるかを選べるメモリ手帳")
st.caption(
    "AIアシスタントが会話から覚えたことを、ユーザーが"
    "「ずっと覚える／今日だけ／要確認／捨てる」に分けて管理できるプロトタイプです。"
    "自動分類はあくまで下書きで、最終的にどう覚えるかはユーザーが決めます。"
)

if "candidates" not in st.session_state:
    st.session_state.candidates = [classify_utterance(t) for t in SAMPLE_CONVERSATION]
if "approved" not in st.session_state:
    st.session_state.approved = []

st.header("0. 自分の発話を試す")
new_text = st.text_input("会話の発話を入力すると、メモリ候補として分類されます", key="new_text")
if st.button("候補に追加する"):
    if new_text.strip():
        st.session_state.candidates.append(classify_utterance(new_text.strip()))
        st.rerun()

st.header("1. メモリ候補（会話から自動抽出）")
st.caption("分類と文面はここで直せます。直した上で「承認する」と、提案に使われるようになります。")
for i, cand in enumerate(list(st.session_state.candidates)):
    with st.container(border=True):
        edited_text = st.text_input("メモリの文面", value=cand.text, key=f"text-{i}")
        scope_index = SCOPE_KEYS.index(cand.scope)
        new_scope_label = st.selectbox(
            "分類（scope）",
            [SCOPE_LABELS[k] for k in SCOPE_KEYS],
            index=scope_index,
            key=f"scope-{i}",
        )
        st.write(f"自動分類の理由: {cand.reason}（確信度 {cand.confidence:.2f}）")
        col1, col2 = st.columns(2)
        if col1.button("この内容で承認する", key=f"ok-{i}"):
            new_scope = SCOPE_KEYS[[SCOPE_LABELS[k] for k in SCOPE_KEYS].index(new_scope_label)]
            st.session_state.approved.append(
                MemoryCandidate(edited_text, new_scope, cand.confidence, cand.reason)
            )
            st.session_state.candidates.pop(i)
            st.rerun()
        if col2.button("捨てる", key=f"ng-{i}"):
            st.session_state.candidates.pop(i)
            st.rerun()

st.header("2. 承認済みメモリ")
if st.session_state.approved:
    for j, mem in enumerate(st.session_state.approved):
        col1, col2 = st.columns([4, 1])
        col1.write(f"- [{SCOPE_LABELS[mem.scope]}] {mem.text}")
        if col2.button("取り消す", key=f"un-{j}"):
            st.session_state.approved.pop(j)
            st.rerun()
else:
    st.info("まだ承認済みメモリはありません。")

st.header("3. 承認済みメモリを使った提案")
if st.session_state.approved:
    for proposal in propose_dinner(st.session_state.approved):
        st.write(f"### {proposal['name']}")
        if proposal["reasons"]:
            for reason in proposal["reasons"]:
                st.write(f"- {reason}")
        else:
            st.write("- 使えるメモリがまだないため、標準の候補から選んでいます")
else:
    st.info("メモリを承認すると、ここに理由つきの提案が出ます。")

st.header("4. 分類の評価")
passed, total, failures = run_evaluation()
st.write(f"評価シナリオ: {passed} / {total} 件が期待どおりの分類になりました")
for failure in failures:
    st.write(f"- {failure}")
