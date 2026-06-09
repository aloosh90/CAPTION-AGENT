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

def load_analysis_file(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def extract_teacher_section(content: str, teacher_id: str) -> str:
    start_marker = f"تحليل المنافسين — {teacher_id}.md"
    lines = content.split("\n")
    start_idx = None
    for i, line in enumerate(lines):
        if start_marker in line:
            start_idx = i
            break
    if start_idx is None:
        return ""
    end_idx = len(lines)
    for i in range(start_idx + 1, len(lines)):
        if lines[i].startswith("🆚") and "تحليل المنافسين —" in lines[i]:
            end_idx = i
            break
    full_section = "\n".join(lines[start_idx:end_idx])
    MAX_CHARS = 6000
    if len(full_section) > MAX_CHARS:
        student_match = re.search(r"٧\.\s*التعليقات", full_section)
        if student_match:
            header = full_section[:1500]
            student_section = full_section[student_match.start(): student_match.start() + 4000]
            full_section = header + "\n\n[...قُلِّص...]\n\n" + student_section
        else:
            full_section = full_section[:MAX_CHARS]
    return full_section


def build_system_prompt(teacher_name, subject, platform, cta_type):
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


COMPETITOR_PLATFORMS = "أبواب، مرماز، جذور، مستقبلي، ريشة، أكاديمي، نابو، جواد، ماكس، نيبور"


def build_user_prompt(teacher_name, subject, teacher_section, caption_count, extra_comments, use_web_search=True):
    dna_count = (caption_count + 1) // 2
    new_count = caption_count - dna_count

    search_block = ""
    if use_web_search:
        search_block = f"""
🔎 مهمة بحث حي — الاعتماد الأساسي (≈85%):
ابحث بالويب عن المنافسين العراقيين بمجال تعليم السادس الإعدادي بمادة {subject}.
منصات منافسة معروفة: {COMPETITOR_PLATFORMS}.
دوّر على: حملاتهم الحالية وزواياهم، شكاوى الطلاب عنهم ونقاط ضعفهم، أقوى الأمثلة الإعلانية بالسوق العراقي.
استخرج أقوى الزوايا وحوّلها لصالح علا (بلا ذكر اسم منافس بالكابشن).
"""

    intel_block = ""
    if teacher_section.strip():
        weight_note = "مرجع ثانوي خفيف (≈15%)" if use_web_search else "المصدر الأساسي"
        intel_block = f"""
📁 ملف تحليل المنافسين ({weight_note}):
{'-' * 50}
{teacher_section}
{'-' * 50}
"""

    extra_block = ""
    if extra_comments.strip():
        extra_block = f"""
تعليقات إضافية (النقد والطلبات فقط):
{'-' * 50}
{extra_comments}
{'-' * 50}
"""

    return f"""اكتب {caption_count} كابشن إعلاني للأستاذ {teacher_name} بمنطق 50/50:
- {dna_count} كابشن "DNA" — مبني على هوية علا المعتمدة
- {new_count} كابشن "زاوية جديدة" — مبني على نقاط ضعف المنافسين
{search_block}{intel_block}{extra_block}
بعد البحث، أرجع JSON فقط — لا مقدمات، لا شرح، لا markdown."""


def safe_parse_json(text):
    text = text.strip()
    text = re.sub(r"```(?:json)?", "", text).replace("```", "").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if match:
        return json.loads(match.group())
    raise ValueError(f"ما قدرت أستخرج JSON:\n{text[:300]}")


def extract_text_candidates(message):
    text_blocks = [b.text for b in getattr(message, "content", []) if getattr(b, "type", None) == "text"]
    if not text_blocks:
        return []
    return [text_blocks[-1], "\n".join(text_blocks)]


def generate_captions(teacher_name, teacher_id, subject, platform, cta_type,
                      caption_count, extra_comments, analysis_text, api_key,
                      use_web_search=True):
    teacher_section = ""
    if analysis_text:
        teacher_section = extract_teacher_section(analysis_text, teacher_id)

    system_prompt = build_system_prompt(teacher_name, subject, platform, cta_type)
    user_prompt = build_user_prompt(teacher_name, subject, teacher_section,
                                    caption_count, extra_comments, use_web_search)

    client = anthropic.Anthropic(api_key=api_key)
    kwargs = dict(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )
    if use_web_search:
        kwargs["tools"] = [{"type": "web_search_20250305", "name": "web_search", "max_uses": 5}]

    message = client.messages.create(**kwargs)

    captions = None
    last_err = None
    for cand in extract_text_candidates(message):
        try:
            captions = safe_parse_json(cand)
            break
        except Exception as e:
            last_err = e
            continue
    if captions is None:
        raise ValueError(f"ما قدرت أستخرج JSON: {last_err}")

    if not isinstance(captions, list):
        raise ValueError("الجواب مو list")

    for c in captions:
        if isinstance(c, dict) and isinstance(c.get("caption"), str):
            c["caption"] = c["caption"].replace("\\n", "\n").replace("\\r", "").strip()

    return captions
