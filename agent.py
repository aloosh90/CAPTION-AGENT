# ═══════════════════════════════════════════════════════════════
# agent.py — منطق وكيل الكابشنات
# ═══════════════════════════════════════════════════════════════

import anthropic
import json
import re
from config import (
    BRAND_DNA, WEAKNESS_ANGLE_MAP, DIALECT_REFERENCE,
    PLATFORM_GUIDELINES, GUARDRAILS, OUTPUT_FORMAT_INSTRUCTION,
    MODEL, MAX_TOKENS,
)

# ─── تحميل ملف التحليل ────────────────────────────────────────
def load_analysis_file(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


# ─── استخراج قسم الأستاذ من الملف ────────────────────────────
def extract_teacher_section(content: str, teacher_id: str) -> str:
    """
    يستخرج قسم تحليل المنافسين الخاص بأستاذ معين.
    الملف يستخدم '🆚 تحليل المنافسين — {id}.md' كفاصل بين الأقسام.
    """
    start_marker = f"تحليل المنافسين — {teacher_id}.md"
    lines = content.split("\n")

    start_idx = None
    for i, line in enumerate(lines):
        if start_marker in line:
            start_idx = i
            break

    if start_idx is None:
        return ""  # الأستاذ مو موجود بالملف

    # إيجاد نهاية القسم (بداية القسم التالي)
    end_idx = len(lines)
    for i in range(start_idx + 1, len(lines)):
        if lines[i].startswith("🆚") and "تحليل المنافسين —" in lines[i]:
            end_idx = i
            break

    full_section = "\n".join(lines[start_idx:end_idx])

    # لو القسم طويل، نعطي الأولوية لقسم التعليقات (§٧) لأنه الأهم للكابشنات
    MAX_CHARS = 6000
    if len(full_section) > MAX_CHARS:
        student_match = re.search(r"٧\.\s*التعليقات", full_section)
        if student_match:
            header = full_section[: 1500]
            student_section = full_section[student_match.start() : student_match.start() + 4000]
            full_section = header + "\n\n[...قُلِّص للتركيز على احتياجات الطلاب...]\n\n" + student_section
        else:
            full_section = full_section[:MAX_CHARS]

    return full_section


# ─── بناء الـSystem Prompt ────────────────────────────────────
def build_system_prompt(teacher_name: str, subject: str, platform: str, cta_type: str) -> str:
    return f"""أنت وكيل كتابة كابشنات إعلانية متخصص حصراً لمنصة علا التعليمية العراقية.
مهمتك الوحيدة: كتابة كابشنات للأستاذ {teacher_name} (مادة {subject})، السادس الإعدادي، السوق العراقي.

{BRAND_DNA}

{WEAKNESS_ANGLE_MAP}

{DIALECT_REFERENCE}

{PLATFORM_GUIDELINES}

{GUARDRAILS}

معلومات الطلب الحالي:
- الأستاذ: {teacher_name} | المادة: {subject}
- المنصة: {platform}
- نوع CTA: {cta_type}

{OUTPUT_FORMAT_INSTRUCTION}"""


# ─── بناء الـUser Prompt ──────────────────────────────────────
def build_user_prompt(
    teacher_name: str,
    teacher_section: str,
    caption_count: int,
    extra_comments: str,
) -> str:

    dna_count = (caption_count + 1) // 2      # نص مقرّب للأعلى
    new_count = caption_count - dna_count      # النص الثاني

    intel_block = ""
    if teacher_section.strip():
        intel_block = f"""
تقرير تحليل المنافسين للأستاذ {teacher_name}:
(ركّز على: احتياجات الطلاب الحقيقية، شكاوى الطلاب من المنافسين، نقاط الضعف القابلة للاستثمار)
{'─' * 60}
{teacher_section}
{'─' * 60}
"""

    extra_block = ""
    if extra_comments.strip():
        extra_block = f"""
تعليقات/كابشنات إضافية (النقد والطلبات فقط — المدح مرفوض تلقائياً):
{'─' * 60}
{extra_comments}
{'─' * 60}
"""

    return f"""اكتب {caption_count} كابشن إعلاني للأستاذ {teacher_name} بمنطق 50/50:
• {dna_count} كابشن من النوع "DNA" — مبني على هوية علا المعتمدة وأنماطها الثابتة
• {new_count} كابشن من النوع "زاوية جديدة" — مبني على نقاط ضعف المنافسين وشكاوى/طلبات الطلاب

{intel_block}
{extra_block}
أرجع JSON فقط — لا مقدمات، لا شرح، لا markdown."""


# ─── استخراج JSON بشكل آمن ────────────────────────────────────
def safe_parse_json(text: str) -> list:
    """يحاول يستخرج JSON array من النص حتى لو فيه نص زيادة."""
    text = text.strip()
    # إزالة backticks احتمالية
    text = re.sub(r"```(?:json)?", "", text).replace("```", "").strip()
    # محاولة أول: النص كامل
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # محاولة ثانية: نبحث عن أول [ ... ] في النص
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if match:
        return json.loads(match.group())
    raise ValueError(f"ما قدرت أستخرج JSON من الجواب:\n{text[:300]}")


# ─── الدالة الرئيسية ──────────────────────────────────────────
def generate_captions(
    teacher_name: str,
    teacher_id: str,
    subject: str,
    platform: str,
    cta_type: str,
    caption_count: int,
    extra_comments: str,
    analysis_text: str,
    api_key: str,
) -> list[dict]:
    """
    يولّد قائمة كابشنات بمنطق 50/50.
    يرجع: list من dicts، كل dict فيه caption, type, angle, cta, platform.
    """
    # استخراج قسم الأستاذ
    teacher_section = ""
    if analysis_text:
        teacher_section = extract_teacher_section(analysis_text, teacher_id)

    # بناء البرومبتات
    system_prompt = build_system_prompt(teacher_name, subject, platform, cta_type)
    user_prompt   = build_user_prompt(teacher_name, teacher_section, caption_count, extra_comments)

    # استدعاء Claude API
    client  = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )

    raw_text = message.content[0].text
    captions = safe_parse_json(raw_text)

    # تأكد إن الناتج list
    if not isinstance(captions, list):
        raise ValueError("الجواب مو list")

    return captions
