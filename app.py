import streamlit as st
import openai
import pdfplumber
import boto3
import json
import uuid
from datetime import datetime

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Code Compliance Checker",
    page_icon="🏗️",
    layout="wide"
)

# ── Custom CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    .main { background-color: #F4F7FB; }
    .stApp { background-color: #F4F7FB; }
    .title-box {
        background: linear-gradient(135deg, #1F3864, #2E5DA6);
        padding: 2rem 2.5rem;
        border-radius: 16px;
        margin-bottom: 1.5rem;
    }
    .title-box h1 { color: white; font-size: 2rem; margin: 0; }
    .title-box p  { color: #BDD4F0; margin: 0.4rem 0 0; font-size: 1rem; }
    .card {
        background: white;
        border-radius: 12px;
        padding: 1.5rem;
        margin-bottom: 1rem;
        box-shadow: 0 2px 8px rgba(0,0,0,0.07);
    }
    .violation-critical {
        background: #FFF0F0;
        border-left: 5px solid #D32F2F;
        padding: 1rem 1.2rem;
        border-radius: 8px;
        margin-bottom: 0.8rem;
    }
    .violation-warning {
        background: #FFFBEA;
        border-left: 5px solid #F9A825;
        padding: 1rem 1.2rem;
        border-radius: 8px;
        margin-bottom: 0.8rem;
    }
    .violation-info {
        background: #F0F6FF;
        border-left: 5px solid #1565C0;
        padding: 1rem 1.2rem;
        border-radius: 8px;
        margin-bottom: 0.8rem;
    }
    .badge-critical { background:#D32F2F; color:white; padding:2px 10px; border-radius:20px; font-size:0.75rem; font-weight:bold; }
    .badge-warning  { background:#F9A825; color:white; padding:2px 10px; border-radius:20px; font-size:0.75rem; font-weight:bold; }
    .badge-info     { background:#1565C0; color:white; padding:2px 10px; border-radius:20px; font-size:0.75rem; font-weight:bold; }
    .chat-user { background:#E8F0FE; border-radius:12px; padding:0.8rem 1rem; margin:0.5rem 0; text-align:right; }
    .chat-ai   { background:#F1F3F4; border-radius:12px; padding:0.8rem 1rem; margin:0.5rem 0; }
    .s3-badge  { background:#FF9900; color:white; padding:4px 12px; border-radius:20px; font-size:0.8rem; font-weight:bold; }
    .stButton>button {
        background: linear-gradient(135deg, #1F3864, #2E5DA6);
        color: white;
        border: none;
        border-radius: 8px;
        padding: 0.5rem 1.5rem;
        font-weight: 600;
    }
    .stButton>button:hover { opacity: 0.9; }
</style>
""", unsafe_allow_html=True)

# ── Header ────────────────────────────────────────────────────────────────────
st.markdown("""
<div class="title-box">
    <h1>🏗️ Local Code Compliance Checker</h1>
    <p>Upload your building plan PDF and get an instant AI-powered compliance report. Every report is automatically saved to AWS S3.</p>
</div>
""", unsafe_allow_html=True)

# ── S3 helpers ────────────────────────────────────────────────────────────────
def get_s3_client():
    try:
        return boto3.client(
            "s3",
            aws_access_key_id     = st.secrets["AWS_ACCESS_KEY_ID"],
            aws_secret_access_key = st.secrets["AWS_SECRET_ACCESS_KEY"],
            region_name           = st.secrets["AWS_REGION"]
        )
    except Exception:
        return None

def save_report_to_s3(report_text, plan_text, jurisdiction, filename):
    try:
        s3 = get_s3_client()
        if not s3:
            return None
        bucket    = st.secrets["AWS_BUCKET_NAME"]
        report_id = str(uuid.uuid4())[:8]
        timestamp = datetime.utcnow().strftime("%Y-%m-%d_%H-%M-%S")
        s3_key    = f"reports/{timestamp}_{report_id}.json"
        payload   = {
            "report_id":    report_id,
            "timestamp":    datetime.utcnow().isoformat(),
            "jurisdiction": jurisdiction,
            "filename":     filename,
            "plan_excerpt": plan_text[:2000],
            "full_report":  report_text,
        }
        s3.put_object(
            Bucket      = bucket,
            Key         = s3_key,
            Body        = json.dumps(payload, indent=2),
            ContentType = "application/json"
        )
        return s3_key
    except Exception as e:
        st.warning(f"S3 save failed: {e}")
        return None

def list_saved_reports():
    try:
        s3     = get_s3_client()
        bucket = st.secrets["AWS_BUCKET_NAME"]
        resp   = s3.list_objects_v2(Bucket=bucket, Prefix="reports/", MaxKeys=20)
        items  = resp.get("Contents", [])
        return sorted(items, key=lambda x: x["LastModified"], reverse=True)
    except Exception:
        return []

def load_report_from_s3(s3_key):
    try:
        s3     = get_s3_client()
        bucket = st.secrets["AWS_BUCKET_NAME"]
        obj    = s3.get_object(Bucket=bucket, Key=s3_key)
        return json.loads(obj["Body"].read().decode("utf-8"))
    except Exception:
        return None

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### ⚙️ Settings")
    api_key = st.text_input("OpenAI API Key", type="password", placeholder="sk-...")
    jurisdiction = st.selectbox(
        "Jurisdiction / Building Code",
        ["International Building Code (IBC) 2021",
         "Georgia State Building Code",
         "City of Atlanta Building Code",
         "California Building Code (CBC) 2022",
         "New York City Building Code"]
    )
    st.markdown("---")

    s3_ok = get_s3_client() is not None
    if s3_ok:
        st.markdown("🟢 **AWS S3 Connected**")
    else:
        st.markdown("🔴 **AWS S3 Not Connected**")
        st.caption("Add AWS credentials in Streamlit Secrets to enable S3 storage.")

    st.markdown("---")
    st.markdown("### 📂 Saved Reports (S3)")
    if s3_ok:
        if st.button("Refresh Reports", use_container_width=True):
            st.session_state.s3_reports = list_saved_reports()
        reports = st.session_state.get("s3_reports", list_saved_reports())
        st.session_state.s3_reports = reports
        if reports:
            for item in reports:
                key  = item["Key"]
                name = key.replace("reports/", "")
                if st.button(f"📄 {name}", key=key, use_container_width=True):
                    loaded = load_report_from_s3(key)
                    if loaded:
                        st.session_state.report       = loaded["full_report"]
                        st.session_state.plan_text    = loaded.get("plan_excerpt", "")
                        st.session_state.analyzed     = True
                        st.session_state.chat_history = []
                        st.rerun()
        else:
            st.caption("No reports saved yet.")
    else:
        st.caption("Connect AWS S3 to view saved reports.")

    st.markdown("---")
    st.markdown("**About**")
    st.markdown("Uses GPT-4o to analyze building plans and flag code violations. Always verify with a licensed engineer.")

# ── Session state ─────────────────────────────────────────────────────────────
if "report"       not in st.session_state: st.session_state.report       = None
if "plan_text"    not in st.session_state: st.session_state.plan_text    = ""
if "chat_history" not in st.session_state: st.session_state.chat_history = []
if "analyzed"     not in st.session_state: st.session_state.analyzed     = False
if "s3_key"       not in st.session_state: st.session_state.s3_key       = None
if "filename"     not in st.session_state: st.session_state.filename     = "demo-input"

# ── Core functions ─────────────────────────────────────────────────────────────
def extract_pdf_text(uploaded_file):
    text = ""
    with pdfplumber.open(uploaded_file) as pdf:
        for page in pdf.pages:
            t = page.extract_text()
            if t:
                text += t + "\n"
    return text.strip()

def run_compliance_check(plan_text, jurisdiction, client):
    system_prompt = f"""You are an expert building code compliance analyst specializing in {jurisdiction}.
Identify potential code violations categorized as CRITICAL, WARNING, or INFORMATIONAL.
For each violation cite the relevant code section, explain in plain language, and suggest a correction.

Format EXACTLY like this for each violation:
SEVERITY: [CRITICAL / WARNING / INFORMATIONAL]
ELEMENT: [What part of the design is affected]
CODE SECTION: [e.g. IBC Section 1005.1]
ISSUE: [Plain language explanation]
CORRECTION: [Specific fix]
---

End with:
SUMMARY:
- Total violations found: X
- Critical: X
- Warnings: X
- Informational: X
- Overall compliance status: [PASS / FAIL / NEEDS REVIEW]

Be thorough. Identify at least 3-5 issues."""

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": f"Analyze for compliance with {jurisdiction}:\n\n{plan_text[:6000]}"}
        ],
        max_tokens=2000,
        temperature=0.3
    )
    return response.choices[0].message.content

def parse_violations(report_text):
    violations = []
    for block in report_text.split("---"):
        if "SEVERITY:" not in block:
            continue
        v = {}
        for line in block.strip().split("\n"):
            if line.startswith("SEVERITY:"):      v["severity"]   = line.replace("SEVERITY:", "").strip()
            elif line.startswith("ELEMENT:"):     v["element"]    = line.replace("ELEMENT:", "").strip()
            elif line.startswith("CODE SECTION:"): v["code"]      = line.replace("CODE SECTION:", "").strip()
            elif line.startswith("ISSUE:"):       v["issue"]      = line.replace("ISSUE:", "").strip()
            elif line.startswith("CORRECTION:"):  v["correction"] = line.replace("CORRECTION:", "").strip()
        if v:
            violations.append(v)
    return violations

def extract_summary(report_text):
    if "SUMMARY:" in report_text:
        return report_text.split("SUMMARY:")[1].strip()
    return ""

def chat_with_report(question, report, plan_text, jurisdiction, history, client):
    messages = [{"role": "system", "content": f"""You are a helpful building code compliance assistant for {jurisdiction}.
Answer questions clearly in plain language. Always reference specific code sections when relevant.
COMPLIANCE REPORT: {report}
ORIGINAL PLAN: {plan_text[:2000]}"""}]
    for turn in history[-6:]:
        messages.append({"role": "user",      "content": turn["user"]})
        messages.append({"role": "assistant", "content": turn["ai"]})
    messages.append({"role": "user", "content": question})
    response = client.chat.completions.create(
        model="gpt-4o", messages=messages, max_tokens=600, temperature=0.4
    )
    return response.choices[0].message.content

# ── Main layout ───────────────────────────────────────────────────────────────
col1, col2 = st.columns([1, 1], gap="large")

with col1:
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.markdown("### 📁 Upload Building Plan")
    uploaded_file = st.file_uploader("Drag and drop your PDF building plan here", type=["pdf"])
    if uploaded_file:
        st.success(f"✅ File uploaded: **{uploaded_file.name}**")
        st.session_state.filename = uploaded_file.name
        with st.spinner("Extracting text from PDF..."):
            plan_text = extract_pdf_text(uploaded_file)
            st.session_state.plan_text = plan_text
        if plan_text:
            st.info(f"📄 Extracted {len(plan_text)} characters")
            with st.expander("Preview extracted text"):
                st.text(plan_text[:1000] + ("..." if len(plan_text) > 1000 else ""))
        else:
            st.warning("Could not extract text — use the text box below instead.")
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.markdown("### 🧪 No PDF? Use Demo Mode")
    demo_text = st.text_area(
        "Paste a building plan description here:",
        height=160,
        placeholder="""Example:
Two-story commercial office building, 8,400 sq ft total.
Ground floor: open office 4,200 sq ft, 2 restrooms, 1 storage room.
Ceiling height: 8 feet. Single staircase 36 inches wide.
Main exit: one 32-inch door. Sprinkler system: not installed.
Parking: 12 spaces, no accessible spaces designated.""",
        key="demo_input"
    )
    st.markdown('</div>', unsafe_allow_html=True)

    if st.button("🔍 Run Compliance Check", use_container_width=True):
        if not api_key:
            st.error("Please enter your OpenAI API key in the sidebar.")
        else:
            text_to_analyze = st.session_state.plan_text or demo_text
            if not text_to_analyze.strip():
                st.error("Please upload a PDF or paste a building description first.")
            else:
                try:
                    client = openai.OpenAI(api_key=api_key)
                    with st.spinner("AI is analyzing your building plan... 20-30 seconds"):
                        report = run_compliance_check(text_to_analyze, jurisdiction, client)
                        st.session_state.report       = report
                        st.session_state.plan_text    = text_to_analyze
                        st.session_state.analyzed     = True
                        st.session_state.chat_history = []

                    with st.spinner("Saving report to AWS S3..."):
                        s3_key = save_report_to_s3(
                            report_text  = report,
                            plan_text    = text_to_analyze,
                            jurisdiction = jurisdiction,
                            filename     = st.session_state.filename
                        )
                        st.session_state.s3_key = s3_key

                    if s3_key:
                        st.success(f"✅ Report saved to S3: `{s3_key}`")
                    else:
                        st.info("Analysis complete. S3 not connected — report not saved to cloud.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {str(e)}")

with col2:
    if st.session_state.analyzed and st.session_state.report:
        report = st.session_state.report

        if st.session_state.s3_key:
            st.markdown(f'<span class="s3-badge">☁️ Saved to S3: {st.session_state.s3_key}</span>', unsafe_allow_html=True)
            st.markdown("")

        summary = extract_summary(report)
        if "FAIL" in summary.upper():
            st.error("⛔ Compliance Status: FAIL — Violations require attention before approval")
        elif "PASS" in summary.upper():
            st.success("✅ Compliance Status: PASS — No critical violations found")
        else:
            st.warning("⚠️ Compliance Status: NEEDS REVIEW — Please examine flagged items")

        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown("### 📋 Compliance Report")
        violations = parse_violations(report)

        if violations:
            critical = [v for v in violations if "CRITICAL"      in v.get("severity","").upper()]
            warnings = [v for v in violations if "WARNING"       in v.get("severity","").upper()]
            info     = [v for v in violations if "INFORMATIONAL" in v.get("severity","").upper()]

            c1, c2, c3 = st.columns(3)
            c1.metric("🔴 Critical",      len(critical))
            c2.metric("🟡 Warnings",      len(warnings))
            c3.metric("🔵 Informational", len(info))
            st.markdown("---")

            for v in violations:
                sev = v.get("severity","").upper()
                if "CRITICAL" in sev:   css, badge = "violation-critical", "badge-critical"
                elif "WARNING" in sev:  css, badge = "violation-warning",  "badge-warning"
                else:                   css, badge = "violation-info",     "badge-info"
                st.markdown(f"""
<div class="{css}">
  <span class="{badge}">{sev}</span>
  <strong style="margin-left:8px">{v.get('element','')}</strong><br>
  <small style="color:#666">📖 {v.get('code','')}</small><br><br>
  <b>Issue:</b> {v.get('issue','')}<br>
  <b>Correction:</b> {v.get('correction','')}
</div>""", unsafe_allow_html=True)
        else:
            st.markdown(report)

        with st.expander("📄 View raw report text"):
            st.text(report)
        st.markdown('</div>', unsafe_allow_html=True)

        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown("### 💬 Ask the Compliance Chatbot")
        for turn in st.session_state.chat_history:
            st.markdown(f'<div class="chat-user">👤 {turn["user"]}</div>', unsafe_allow_html=True)
            st.markdown(f'<div class="chat-ai">🤖 {turn["ai"]}</div>',    unsafe_allow_html=True)

        with st.form("chat_form", clear_on_submit=True):
            user_q = st.text_input("Your question:", placeholder="e.g. What does IBC Section 1005.1 require for egress width?")
            send   = st.form_submit_button("Send")

        if send and user_q.strip():
            if not api_key:
                st.error("Enter your OpenAI API key in the sidebar.")
            else:
                try:
                    client = openai.OpenAI(api_key=api_key)
                    with st.spinner("Thinking..."):
                        answer = chat_with_report(
                            user_q, st.session_state.report,
                            st.session_state.plan_text, jurisdiction,
                            st.session_state.chat_history, client
                        )
                    st.session_state.chat_history.append({"user": user_q, "ai": answer})
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {str(e)}")
        st.markdown('</div>', unsafe_allow_html=True)

    else:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown("### 📊 Your Report Will Appear Here")
        st.markdown("""
Upload a building plan PDF or paste a description on the left, then click **Run Compliance Check**.

**What you'll get:**
- 🔴 **Critical violations** — must fix before approval
- 🟡 **Warnings** — should be reviewed
- 🔵 **Informational** — best practice notes
- ☁️ **Auto-saved to AWS S3**
- 💬 **Chatbot** for follow-up questions
        """)
        st.markdown('</div>', unsafe_allow_html=True)

        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown("### 🗺️ How It Works")
        for icon, title, desc in [
            ("1️⃣", "Upload PDF",   "Drag and drop your building plan"),
            ("2️⃣", "AI Parses",    "Extracts text and design data"),
            ("3️⃣", "Code Check",   "Cross-references local building codes"),
            ("4️⃣", "Report",       "Violations flagged with explanations"),
            ("5️⃣", "Saved to S3",  "Report automatically stored in AWS S3"),
            ("6️⃣", "Chatbot",      "Ask follow-up questions instantly"),
        ]:
            st.markdown(f"**{icon} {title}** — {desc}")
        st.markdown('</div>', unsafe_allow_html=True)
