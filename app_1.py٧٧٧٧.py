# ═══════════════════════════════════════════════════════════════
# app.py — واجهة وكيل الكابشنات لمنصة علا
# ═══════════════════════════════════════════════════════════════

import streamlit as st
import json
import glob
from pathlib import Path
from config import TEACHERS, PLATFORMS, CTA_TYPES, DEFAULT_CAPTION_COUNT
from agent import generate_captions, load_analysis_file

# ─── إعدادات الصفحة ───────────────────────────────────────────
st.set_page_config(
    page_title="علا — وكيل الكابشنات",
    page_icon="✏️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── CSS عربي RTL ─────────────────────────────────────────────
st.markdown("""
<style>
    /* RTL global */
    html, body, [class*="css"] { direction: rtl; }
    .stSelectbox label, .stSlider label,
    .stTextArea label, .stFileUploader label,
    .stTextInput label { text-align: right; display: block; }
    .stTextArea textarea { direction: rtl; font-size: 15px; line-height: 1.8; }

    /* Caption cards */
    .cap-card {
        background: #1a1a2e;
        border: 1px solid #2d2d4e;
        border-radius: 14px;
        padding: 20px 22px;
        margin-bottom: 18px;
        direction: rtl;
    }
    .cap-text {
        font-size: 18px;
        line-height: 2;
        color: #e2e8f0;
        font-family: 'Segoe UI', Tahoma, Arial, sans-serif;
        white-space: pre-wrap;
    }
    .badge {
        display: inline-block;
        padding: 3px 12px;
        border-radius: 20px;
        font-size: 12px;
        font-weight: bold;
        margin-bottom: 12px;
    }
    .badge-dna  { background: #1e3a5f; color: #90cdf4; }
    .badge-new  { background: #1a3a2a; color: #9ae6b4; }
    .angle-box {
        background: #2d1f0e;
        color: #fbd38d;
        border-radius: 8px;
        padding: 7px 14px;
        font-size: 13px;
        margin-top: 10px;
    }
    .meta { color: #718096; font-size: 12px; margin-top: 10px; }
    .num  { color: #4a5568; font-size: 13px; }

    /* Sidebar */
    [data-testid="stSidebar"] { direction: rtl; }
    [data-testid="stSidebar"] * { text-align: right; }

    /* Header */
    .page-title { font-size: 30px; font-weight: 800; color: #e2e8f0; margin-bottom: 2px; }
    .page-sub   { color: #718096; font-size: 14px; margin-bottom: 28px; }

    /* Generate button */
    div[data-testid="stButton"] button {
        background: linear-gradient(135deg, #667eea, #764ba2);
        color: white;
        font-size: 16px;
        font-weight: bold;
        border: none;
        border-radius: 10px;
        padding: 12px 0;
    }
    div[data-testid="stButton"] button:hover {
        background: linear-gradient(135deg, #764ba2, #667eea);
    }
</style>
""", unsafe_allow_html=True)


# ─── تحميل ملف التحليل (مع كاش) ─────────────────────────────
# ملفات الكود نفسها — نتجاهلها عند البحث عن ملف التحليل
_CODE_FILES = {"app.py", "agent.py", "config.py"}

@st.cache_data
def load_default_analysis() -> str | None:
    """
    يبحث تلقائياً عن ملف تحليل المنافسين في المجلد الرئيسي أو data/
    بأي اسم (يكفي يحتوي على 'تحليل المنافسين').
    """
    patterns = ["*.py", "*.txt", "*.md", "data/*.py", "data/*.txt", "data/*.md"]
    seen = set()
    for pattern in patterns:
        for path in glob.glob(pattern):
            if path in seen or Path(path).name in _CODE_FILES:
                continue
            seen.add(path)
            try:
                text = load_analysis_file(path)
            except Exception:
                continue
            if "تحليل المنافسين" in text:
                return text
    return None


def get_analysis_text(uploaded=None) -> str | None:
    if uploaded is not None:
        return uploaded.read().decode("utf-8")
    return load_default_analysis()


# ─── Sidebar ─────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### ⚙️ الإعدادات")
    st.divider()

    # مفتاح API
    api_key = st.text_input(
        "🔑 مفتاح Claude API",
        type="password",
        placeholder="sk-ant-api03-...",
        help="احصل عليه من console.anthropic.com — يُحفظ بـ secrets.toml للنشر",
    )
    # محاولة من secrets (للنشر على Streamlit Cloud)
    if not api_key:
        try:
            api_key = st.secrets["ANTHROPIC_API_KEY"]
        except Exception:
            pass

    st.divider()

    # اختيار الأستاذ
    teacher_name = st.selectbox("👨‍🏫 الأستاذ", options=list(TEACHERS.keys()))
    info = TEACHERS[teacher_name]
    st.caption(f"📚 المادة: **{info['subject']}**")

    # المنصة
    platform = st.selectbox("📱 المنصة", options=PLATFORMS)

    # نوع CTA
    cta_type = st.selectbox("📢 نوع CTA", options=CTA_TYPES)

    # عدد الكابشنات
    caption_count = st.slider(
        "🔢 عدد الكابشنات",
        min_value=1, max_value=10,
        value=DEFAULT_CAPTION_COUNT,
    )

    # البحث الويب الحي
    use_web_search = st.toggle(
        "🔎 بحث ويب حي عن المنافسين",
        value=True,
        help="يبحث بالويب عن المنافسين (≈85%) ويستخدم الملف كمرجع خفيف (≈15%). يبطّئ التوليد ويكلّف زيادة بسيطة.",
    )

    st.divider()

    # رفع ملف التحليل
    st.markdown("**📂 ملف تحليل المنافسين**")
    st.caption("ضع الملف في مجلد `data/` أو ارفعه هنا")
    uploaded_file = st.file_uploader(
        "ارفع الملف",
        type=["py", "txt", "md"],
        label_visibility="collapsed",
    )

    analysis_status = "✅ موجود تلقائياً" if load_default_analysis() else (
        "📤 مرفوع يدوياً" if uploaded_file else "⚠️ مو موجود — DNA فقط"
    )
    st.caption(f"الحالة: {analysis_status}")


# ─── الصفحة الرئيسية ─────────────────────────────────────────
st.markdown('<div class="page-title">✏️ وكيل الكابشنات — علا</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="page-sub">كابشنات إعلانية للسادس الإعدادي &nbsp;|&nbsp; '
    'لهجة عراقية أصيلة &nbsp;|&nbsp; منطق 50/50</div>',
    unsafe_allow_html=True,
)

# مدخل التعليقات الإضافية
extra_comments = st.text_area(
    "💬 تعليقات/كابشنات إضافية (اختياري)",
    placeholder=(
        "الصق هنا:\n"
        "• تعليقات نقدية من طلاب عند المنافسين\n"
        "• كابشنات منافسين تريد تحلل فجواتها\n"
        "• طلبات طلاب ما شيفتها بالتقارير\n\n"
        "المدح والإشادة تُتجاهل تلقائياً."
    ),
    height=110,
)

# زر التوليد
col_l, col_c, col_r = st.columns([1, 2, 1])
with col_c:
    generate_btn = st.button("⚡  اكتب الكابشنات", use_container_width=True)


# ─── منطق التوليد ─────────────────────────────────────────────
if generate_btn:

    # التحقق من الـAPI key
    if not api_key:
        st.error("⚠️  أدخل مفتاح Claude API في الـSidebar أولاً.")
        st.stop()

    # تحميل ملف التحليل
    analysis_text = get_analysis_text(uploaded_file)
    if not analysis_text:
        st.warning(
            "⚠️  ملف التحليل مو موجود — راح يشتغل DNA فقط (بلا زوايا جديدة).\n"
            "ضع الملف في `data/competitor_analysis.py` للنتيجة الكاملة."
        )

    spinner_msg = (
        f"يبحث عن المنافسين ويكتب {caption_count} كابشن للأستاذ {teacher_name}…"
        if use_web_search else
        f"يكتب {caption_count} كابشن للأستاذ {teacher_name}…"
    )
    with st.spinner(spinner_msg):
        try:
            captions = generate_captions(
                teacher_name=teacher_name,
                teacher_id=info["id"],
                subject=info["subject"],
                platform=platform,
                cta_type=cta_type,
                caption_count=caption_count,
                extra_comments=extra_comments,
                analysis_text=analysis_text or "",
                api_key=api_key,
                use_web_search=use_web_search,
            )

            # ─── عرض النتائج ──────────────────────────────────
            st.divider()

            dna_count = sum(1 for c in captions if c.get("type") == "DNA")
            new_count = len(captions) - dna_count

            st.markdown(
                f"### {len(captions)} كابشن &nbsp;|&nbsp; "
                f"الأستاذ **{teacher_name}** — {info['subject']}"
            )
            st.caption(f"🔵 DNA معتمد: {dna_count}  &nbsp;|&nbsp;  🟢 زاوية جديدة: {new_count}")
            st.divider()

            for i, cap in enumerate(captions, 1):
                caption_text = cap.get("caption", "")
                cap_type     = cap.get("type", "DNA")
                angle        = cap.get("angle", "")
                cta          = cap.get("cta", "")
                cap_platform = cap.get("platform", "")

                is_dna       = (cap_type == "DNA")
                badge_class  = "badge-dna" if is_dna else "badge-new"
                badge_icon   = "🔵" if is_dna else "🟢"

                angle_html = (
                    f'<div class="angle-box">🎯 يعالج: {angle}</div>'
                    if (angle and not is_dna) else ""
                )

                st.markdown(f"""
<div class="cap-card">
  <div style="display:flex; justify-content:space-between; align-items:center; flex-direction:row-reverse;">
    <span class="num">#{i}</span>
    <span class="badge {badge_class}">{badge_icon} {cap_type}</span>
  </div>
  <div class="cap-text">{caption_text}</div>
  {angle_html}
  <div class="meta">📱 {cap_platform} &nbsp;·&nbsp; 📢 {cta}</div>
</div>
""", unsafe_allow_html=True)

                # كود قابل للنسخ
                st.code(caption_text, language=None)

            # ─── تصدير الكل ───────────────────────────────────
            st.divider()
            export_lines = []
            for i, c in enumerate(captions, 1):
                export_lines.append(
                    f"{'─'*50}\n"
                    f"#{i} [{c.get('type','')}] | {c.get('platform','')} | {c.get('cta','')}\n"
                    f"{c.get('caption','')}\n"
                )
                if c.get("angle"):
                    export_lines.append(f"الزاوية: {c['angle']}\n")

            export_text = "\n".join(export_lines)

            st.download_button(
                label="⬇️  حمّل الكابشنات (TXT)",
                data=export_text,
                file_name=f"captions_{info['id']}_{platform.replace('/', '-')}.txt",
                mime="text/plain",
            )

        except ValueError as e:
            st.error(f"⚠️  خطأ بتحليل الجواب — حاول مرة ثانية:\n{e}")
        except Exception as e:
            st.error(f"⚠️  خطأ: {e}")
