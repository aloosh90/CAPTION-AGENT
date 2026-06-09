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


# المنصات المنافسة (لتوجيه البحث الحي)
COMPETITOR_PLATFORMS = "أبواب، مرماز، جذور، مستقبلي، ريشة، أكاديمي، نابو، جواد، ماكس، نيبور"


# ─── بناء الـUser Prompt ──────────────────────────────────────
def build_user_prompt(
    teacher_name: str,
    subject: str,
    teacher_section: str,
    caption_count: int,
    extra_comments: str,
    use_web_search: bool = True,
) -> str:

    dna_count = (caption_count + 1) // 2      # نص مقرّب للأعلى
    new_count = caption_count - dna_count      # النص الثاني

    # ─── طبقة البحث الحي (الأولوية 85%) ───
    search_block = ""
    if use_web_search:
        search_block = f"""
🔎 مهمة بحث حي — الاعتماد الأساسي (≈85%):
ابحث بالويب عن المنافسين العراقيين بمجال تعليم السادس الإعدادي بمادة {subject}.
منصات منافسة معروفة: {COMPETITOR_PLATFORMS}.
دوّر على:
- حملاتهم وإعلاناتهم الحالية والزوايا اللي يستخدمونها
- شكاوى/انتقادات الطلاب عنهم ونقاط ضعفهم
- أقوى الأمثلة الإعلانية بالسوق التعليمي العراقي وما يخلّيها قوية
استخرج من البحث أقوى الزوايا الجديدة وحوّلها لصالح علا (بلا ذكر اسم منافس بالكابشن).
"""

    # ─── ملف التحليل (مرجع ثانوي خفيف 15%) ───
    intel_block = ""
    if teacher_section.strip():
        weight_note = "مرجع ثانوي خفيف (≈15%) — دعم فقط" if use_web_search else "المصدر الأساسي"
        intel_block = f"""
📁 ملف تحليل المنافسين ({weight_note}):
(احتياجات الطلاب الحقيقية وشكاواهم — استخدمه لتعميق الزوايا، مو كمصدر وحيد)
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
{search_block}{intel_block}{extra_block}
بعد ما تخلص البحث، أرجع JSON فقط بالصيغة المطلوبة — لا مقدمات، لا شرح، لا markdown."""


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


# ─── استخراج النص النهائي من رد قد يحتوي بلوكات بحث ──────────
def extract_text_candidates(message) -> list[str]:
    """يرجع نصوص محتملة لاستخراج الـJSON: آخر بلوك نصي أولاً، ثم الكل."""
    text_blocks = [
        b.text for b in getattr(message, "content", [])
        if getattr(b, "type", None) == "text"
    ]
    if not text_blocks:
        return []
    return [text_blocks[-1], "\n".join(text_blocks)]


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
    use_web_search: bool = True,
) -> list[dict]:
    """
    يولّد قائمة كابشنات بمنطق 50/50.
    use_web_search=True يفعّل البحث الحي عن المنافسين (الأولوية 85%).
    """
    # استخراج قسم الأستاذ
    teacher_section = ""
    if analysis_text:
        teacher_section = extract_teacher_section(analysis_text, teacher_id)

    # بناء البرومبتات
    system_prompt = build_system_prompt(teacher_name, subject, platform, cta_type)
    user_prompt   = build_user_prompt(
        teacher_name, subject, teacher_section,
        caption_count, extra_comments, use_web_search,
    )

    # إعداد الاستدعاء
    client = anthropic.Anthropic(api_key=api_key)
    kwargs = dict(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )
    # تفعيل أداة البحث الويب المدمجة
    if use_web_search:
        kwargs["tools"] = [{
            "type": "web_search_20250305",
            "name": "web_search",
            "max_uses": 5,
        }]

    message = client.messages.create(**kwargs)

    # استخراج الـJSON من الرد (يتعامل مع بلوكات البحث)
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
        raise ValueError(f"ما قدرت أستخرج JSON من الجواب: {last_err}")

    # تأكد إن الناتج list
    if not isinstance(captions, list):
        raise ValueError("الجواب مو list")

    # تنظيف: تحويل \n الحرفية لأسطر حقيقية
    for c in captions:
        if isinstance(c, dict) and isinstance(c.get("caption"), str):
            c["caption"] = (
                c["caption"]
                .replace("\\n", "\n")
                .replace("\\r", "")
                .strip()
            )

    return captions
