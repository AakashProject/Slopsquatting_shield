"""Web demo for Slopsquatting Shield. Run:  streamlit run app.py"""
import streamlit as st
from shield import analyze

st.set_page_config(page_title="Slopsquatting Shield", page_icon="🛡️", layout="centered")

STYLE = {
    "BLOCK":   ("#fdecea", "#c62828", "🛑 BLOCK - do not install"),
    "WARN":    ("#fff8e1", "#e08600", "⚠️ WARN - be careful"),
    "ALLOW":   ("#e8f5e9", "#2e7d32", "✅ ALLOW - looks safe"),
    "UNKNOWN": ("#eeeeee", "#555555", "❔ UNKNOWN - could not check"),
}

st.title("🛡️ Slopsquatting Shield")
st.caption("Paste an install command suggested by an AI. We check every package BEFORE you run it.")

SAMPLES = {
    "Choose a sample...": "",
    "Safe packages": "pip install requests pandas",
    "AI-invented package": "pip install requests pdf-reader-pro",
    "npm example": "npm install express express-auth-helper",
}
choice = st.selectbox("Quick samples", list(SAMPLES.keys()))
command = st.text_area("Install command", value=SAMPLES[choice], height=90,
                       placeholder="pip install some-package another-package")

if st.button("Check before installing", type="primary") and command.strip():
    with st.spinner("Checking registries..."):
        results = analyze(command)
    if not results:
        st.info("No pip / npm / yarn / pnpm install command found in that text.")
    for r in results:
        bg, fg, label = STYLE[r["verdict"]]
        score = "" if r["score"] is None else f" &nbsp;|&nbsp; risk score {r['score']}"
        lines = "".join(
            f"<li>{'<b>' + format(p, '+d') + '</b> ' if p else ''}{t}</li>" for p, t in r["reasons"]
        ) or "<li>No risk signals found.</li>"
        hint = (f"<p style='margin:8px 0 0'><b>Did you mean:</b> <code>{r['did_you_mean']}</code></p>"
                if r["did_you_mean"] else "")
        st.markdown(
            f"""<div style="background:{bg};border-left:6px solid {fg};padding:14px 18px;
                border-radius:8px;margin-bottom:14px;color:#222">
                <div style="color:{fg};font-weight:700;font-size:1.05rem">{label}</div>
                <div style="font-size:1.2rem;margin:4px 0"><code>{r['name']}</code>
                  <span style="color:#666;font-size:.85rem">({r['ecosystem']}){score}</span></div>
                <ul style="margin:6px 0 0 18px">{lines}</ul>{hint}</div>""",
            unsafe_allow_html=True,
        )
