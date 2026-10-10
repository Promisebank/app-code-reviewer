import os
import streamlit as st

from reviewer import (CRITERIA, DEFAULT_MODEL, annotate_code, review_code, review_to_markdown)

st.set_page_config(page_title="AI Code Reviewer", page_icon="🔍", layout="wide")

SEVERITY_ICON = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🔵"}
SAMPLES = {
    "Python: SQL injection": 'import sqlite3\n\ndef get_user(username):\n    conn = sqlite3.connect("app.db")\n    cur = conn.cursor()\n    cur.execute(f"SELECT * FROM users WHERE name = \'{username}\'")\n    return cur.fetchone()\n',
    "JavaScript: async bug": 'async function loadUsers(ids) {\n  const users = [];\n  ids.forEach(async (id) => {\n    const res = await fetch("/api/users/" + id);\n    users.push(await res.json());\n  });\n  return users;\n}\n',
}


def get_api_key(user_key: str):
    if user_key:
        return user_key
    try:
        if "OPENAI_API_KEY" in st.secrets:
            return st.secrets["OPENAI_API_KEY"]
    except Exception:
        pass
    return os.environ.get("OPENAI_API_KEY")


st.title("🔍 AI Code Reviewer")
st.caption("Paste Python or JavaScript. Get bugs, risks and fixes, line by line.")

with st.sidebar:
    st.header("Settings")
    language = st.selectbox("Language", ["Python", "JavaScript"])
    model = st.selectbox("Model", [DEFAULT_MODEL, "gpt-4o", "gpt-4.1-mini"])
    chosen = st.multiselect("Review criteria (bugs are always checked)", list(CRITERIA), default=list(CRITERIA))
    user_key = st.text_input("OpenAI API key (optional if set in app secrets)", type="password")
    st.divider()
    sample = st.selectbox("Load a sample", ["(none)"] + list(SAMPLES))

default_code = SAMPLES.get(sample, "")
code = st.text_area("Your code", value=default_code, height=300, key=f"code_{sample}")

if st.button("Review my code", type="primary"):
    api_key = get_api_key(user_key)
    if not api_key:
        st.error("No API key found. Add one in the sidebar or in the app secrets.")
    elif not code.strip():
        st.warning("Paste some code first.")
    else:
        try:
            with st.spinner("Reviewing..."):
                st.session_state["review"] = review_code(code, language, api_key, model, chosen)
                st.session_state["reviewed_code"] = code
                st.session_state["reviewed_lang"] = language
        except Exception as e:
            st.error(f"Review failed: {e}")

review = st.session_state.get("review")
if review:
    code_r = st.session_state["reviewed_code"]
    lang_r = st.session_state["reviewed_lang"]
    issues = review["issues"]

    c1, c2, c3 = st.columns(3)
    c1.metric("Score", f"{review['overall_score']}/10")
    c2.metric("Issues found", len(issues))
    c3.metric("Review time", f"{review['_meta']['seconds']}s")
    st.info(review["summary"])

    left, right = st.columns([1, 1])
    with left:
        st.subheader("Annotated code")
        st.code(annotate_code(code_r, issues), language=None)
    with right:
        st.subheader("Issues")
        if not issues:
            st.success("No issues found.")
        for n, i in enumerate(issues, start=1):
            label = f"{SEVERITY_ICON[i['severity']]} [{n}] {i['title']} · lines {i['line_start']}-{i['line_end']} · {i['category']}"
            with st.expander(label, expanded=i["severity"] in ("critical", "high")):
                st.markdown(f"**Why it matters:** {i['explanation']}")
                st.markdown(f"**Fix:** {i['suggestion']}")
                if i["fixed_code"].strip():
                    st.code(i["fixed_code"], language=lang_r.lower())

    if review["improved_code"].strip():
        st.subheader("Improved version")
        st.code(review["improved_code"], language=lang_r.lower())

    st.download_button("Download review (.md)", review_to_markdown(review, lang_r),
                       file_name="code_review.md", mime="text/markdown")
    st.caption("AI reviews can miss issues or flag false alarms. Treat this as a second pair of eyes, not a replacement for tests and human review.")
