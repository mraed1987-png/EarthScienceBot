import logging
import sqlite3
import random
import asyncio
from datetime import datetime, date, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, MessageHandler,
    filters, ContextTypes, ConversationHandler
)
from questions import جميع_الأسئلة, دروس

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = "8744608803:AAFpiB8kGwd91CnrPcnX7okkjDcKFmffZkg"

MAT_GRADE, MAT_TOPIC, MAT_CONTENT, MAT_SUMMARY, MAT_QUESTIONS, MAT_DATE = range(6)

def get_db():
    conn = sqlite3.connect('earth_science_bot.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.execute('''CREATE TABLE IF NOT EXISTS students
                 (user_id INTEGER PRIMARY KEY, first_name TEXT, grade TEXT,
                  score INTEGER DEFAULT 0, quizzes_taken INTEGER DEFAULT 0, registered_date TEXT)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS quiz_results
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, grade TEXT,
                  score INTEGER, total INTEGER, date TEXT)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS feedback
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, message TEXT, date TEXT)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS teacher (id INTEGER PRIMARY KEY, chat_id INTEGER)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS groups
                 (grade TEXT PRIMARY KEY, chat_id INTEGER, title TEXT)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS materials
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, grade TEXT, topic TEXT,
                  content TEXT, summary TEXT, questions TEXT, class_date TEXT,
                  sent_before INTEGER DEFAULT 0, sent_after INTEGER DEFAULT 0, created_at TEXT)''')
    conn.commit()
    conn.close()

init_db()

def get_grade_name(grade):
    return {"9": "التاسع", "10": "العاشر", "11": "الحادي عشر"}.get(grade, grade)

def is_teacher(user_id):
    conn = get_db()
    t = conn.execute("SELECT chat_id FROM teacher WHERE id = 1").fetchone()
    conn.close()
    return t and t["chat_id"] == user_id

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    conn = get_db()
    student = conn.execute("SELECT * FROM students WHERE user_id = ?", (user.id,)).fetchone()
    conn.close()
    if student:
        await update.message.reply_text(
            f"أهلاً {user.first_name}!\n"
            f"صفك: {get_grade_name(student['grade'])}\n"
            f"نقاطك: {student['score']}\n"
            f"اختباراتك: {student['quizzes_taken']}\n\n"
            "استخدم /menu لعرض القائمة"
        )
    else:
        keyboard = [
            [InlineKeyboardButton("التاسع", callback_data="register_9")],
            [InlineKeyboardButton("العاشر", callback_data="register_10")],
            [InlineKeyboardButton("الحادي عشر", callback_data="register_11")],
        ]
        await update.message.reply_text(
            f"مرحباً بك {user.first_name} في بوت علوم الأرض!\nاختر صفك:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    conn = get_db()
    student = conn.execute("SELECT * FROM students WHERE user_id = ?", (user.id,)).fetchone()
    conn.close()
    if not student:
        await update.message.reply_text("سجل صفك عبر /start")
        return
    keyboard = [
        [InlineKeyboardButton("اختبار", callback_data="menu_quiz"),
         InlineKeyboardButton("درس", callback_data="menu_lesson")],
        [InlineKeyboardButton("نقاطي وترتيبي", callback_data="menu_score"),
         InlineKeyboardButton("رسالة للمعلم", callback_data="menu_feedback")],
        [InlineKeyboardButton("جدول الأسبوع", callback_data="menu_schedule")]
    ]
    await update.message.reply_text(
        f"القائمة - {get_grade_name(student['grade'])}",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    data = query.data

    if data.startswith("register_"):
        grade = data.split("_")[1]
        conn = get_db()
        conn.execute("INSERT OR REPLACE INTO students (user_id, first_name, grade, registered_date) VALUES (?, ?, ?, ?)",
                     (user.id, user.first_name, grade, datetime.now().strftime("%Y-%m-%d %H:%M")))
        conn.commit()
        conn.close()
        await query.edit_message_text(f"تم تسجيلك في الصف {get_grade_name(grade)}!\nاستخدم /menu")

    elif data == "menu_quiz":
        conn = get_db()
        student = conn.execute("SELECT grade FROM students WHERE user_id = ?", (user.id,)).fetchone()
        conn.close()
        if not student:
            await query.edit_message_text("سجل عبر /start")
            return
        grade = student["grade"]
        keyboard = [
            [InlineKeyboardButton("ابدأ الاختبار", callback_data=f"start_quiz_{grade}")],
            [InlineKeyboardButton("رجوع", callback_data="back_menu")]
        ]
        await query.edit_message_text(
            f"اختبار {get_grade_name(grade)}\n10 أسئلة - كل إجابة 10 نقاط\nجاهز؟",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif data.startswith("start_quiz_"):
        grade = data.split("_")[2]
        qs = جميع_الأسئلة.get(grade, [])
        if not qs:
            await query.edit_message_text("لا توجد أسئلة حالياً")
            return
        selected = random.sample(qs, min(10, len(qs)))
        context.user_data["quiz"] = {"grade": grade, "questions": selected, "index": 0, "score": 0}
        await send_question(query, context)

    elif data.startswith("answer_"):
        await handle_answer(query, context)

    elif data == "next_question":
        await send_question(query, context)

    elif data == "back_menu":
        conn = get_db()
        student = conn.execute("SELECT grade FROM students WHERE user_id = ?", (user.id,)).fetchone()
        conn.close()
        gn = get_grade_name(student["grade"]) if student else ""
        keyboard = [
            [InlineKeyboardButton("اختبار", callback_data="menu_quiz"),
             InlineKeyboardButton("درس", callback_data="menu_lesson")],
            [InlineKeyboardButton("نقاطي", callback_data="menu_score"),
             InlineKeyboardButton("للمعلم", callback_data="menu_feedback")],
            [InlineKeyboardButton("جدول", callback_data="menu_schedule")]
        ]
        await query.edit_message_text(f"القائمة - {gn}", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data == "menu_lesson":
        conn = get_db()
        student = conn.execute("SELECT grade FROM students WHERE user_id = ?", (user.id,)).fetchone()
        conn.close()
        if not student: return
        grade = student["grade"]
        lessons = دروس.get(grade, [])
        keyboard = [[InlineKeyboardButton(l["عنوان"], callback_data=f"lesson_{grade}_{i}")] for i, l in enumerate(lessons)]
        keyboard.append([InlineKeyboardButton("رجوع", callback_data="back_menu")])
        await query.edit_message_text(f"دروس {get_grade_name(grade)}:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith("lesson_"):
        parts = data.split("_")
        grade, idx = parts[1], int(parts[2])
        lessons = دروس.get(grade, [])
        if 0 <= idx < len(lessons):
            l = lessons[idx]
            keyboard = [[InlineKeyboardButton("للدروس", callback_data="menu_lesson"),
                         InlineKeyboardButton("القائمة", callback_data="back_menu")]]
            await query.edit_message_text(f"{l['عنوان']}\n\n{l['محتوى']}", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data == "menu_score":
        conn = get_db()
        student = conn.execute("SELECT * FROM students WHERE user_id = ?", (user.id,)).fetchone()
        if student:
            lb = conn.execute("SELECT first_name, score FROM students ORDER BY score DESC LIMIT 10").fetchall()
            r = conn.execute("SELECT COUNT(*)+1 as r FROM students WHERE score > (SELECT score FROM students WHERE user_id = ?)", (user.id,)).fetchone()
            rank = r["r"] if r else "?"
            conn.close()
            lb_text = "المتصدرون:\n"
            for i, s in enumerate(lb, 1):
                m = {1:"1.", 2:"2.", 3:"3."}.get(i, f"{i}.")
                lb_text += f"{m} {s['first_name']} - {s['score']}\n"
            await query.edit_message_text(
                f"نقاطك: {student['score']}\nاختباراتك: {student['quizzes_taken']}\nترتيبك: #{rank}\n\n{lb_text}",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("رجوع", callback_data="back_menu")]])
            )
        else:
            conn.close()
            await query.edit_message_text("سجل عبر /start")

    elif data == "menu_feedback":
        context.user_data["expecting_feedback"] = True
        await query.edit_message_text("أرسل رسالتك للمعلم الآن:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("رجوع", callback_data="back_menu")]]))

    elif data == "menu_schedule":
        keyboard = [
            [InlineKeyboardButton("التاسع", callback_data="schedule_9")],
            [InlineKeyboardButton("العاشر", callback_data="schedule_10")],
            [InlineKeyboardButton("الحادي عشر", callback_data="schedule_11")],
            [InlineKeyboardButton("رجوع", callback_data="back_menu")]
        ]
        await query.edit_message_text("اختر صفك:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith("schedule_"):
        grade = data.split("_")[1]
        sched = {
            "9": "التاسع\n\nالأحد: المعادن والصخور\nالإثنين: العمليات الجيولوجية\nالثلاثاء: تكتونية الصفائح\nالأربعاء: الزلازل والبراكين\nالخميس: مراجعة واختبار",
            "10": "العاشر\n\nالأحد: الغلاف الجوي\nالإثنين: الطقس والمناخ\nالثلاثاء: دورة الماء\nالأربعاء: المحيطات\nالخميس: مراجعة واختبار",
            "11": "الحادي عشر\n\nالأحد: المعادن والصناعة\nالإثنين: التراكيب الجيولوجية\nالثلاثاء: الموارد\nالأربعاء: التغير المناخي\nالخميس: مراجعة واختبار"
        }
        await query.edit_message_text(sched.get(grade, ""),
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("رجوع", callback_data="menu_schedule")]]))

    elif data.startswith("mat_grade_"):
        grade = data.split("_")[2]
        context.user_data["mat_grade"] = grade
        await query.edit_message_text(f"الصف: {get_grade_name(grade)}\nأرسل اسم الموضوع (مثال: المعادن):")
        return MAT_TOPIC

async def send_question(query, context):
    quiz = context.user_data.get("quiz")
    if not quiz: return
    idx = quiz["index"]
    questions = quiz["questions"]
    if idx >= len(questions):
        await finish_quiz(query, context)
        return
    q = questions[idx]
    buttons = [[InlineKeyboardButton(o, callback_data=f"answer_{i}")] for i, o in enumerate(q["خيارات"])]
    buttons.append([InlineKeyboardButton("إلغاء", callback_data="back_menu")])
    await query.edit_message_text(f"س{q['السؤال']}",
        reply_markup=InlineKeyboardMarkup(buttons))

async def handle_answer(query, context):
    quiz = context.user_data.get("quiz")
    if not quiz: return
    ua = int(query.data.split("_")[1])
    idx = quiz["index"]
    q = quiz["questions"][idx]
    correct = ua == q["الجواب"]
    if correct:
        quiz["score"] += 10
    qt = q["خيارات"][q["الجواب"]]
    fb = "صحيح!" if correct else f"خطأ. الإجابة: {qt}"
    quiz["index"] += 1
    if quiz["index"] >= len(quiz["questions"]):
        await finish_quiz(query, context, fb)
    else:
        await query.edit_message_text(f"{fb}\nالتالي...",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("التالي", callback_data="next_question")]]))

async def finish_quiz(query, context, feedback_text=None):
    quiz = context.user_data.pop("quiz", None)
    if not quiz: return
    user = query.from_user
    score = quiz["score"]
    total = len(quiz["questions"]) * 10
    conn = get_db()
    conn.execute("UPDATE students SET score = score + ?, quizzes_taken = quizzes_taken + 1 WHERE user_id = ?", (score, user.id))
    conn.execute("INSERT INTO quiz_results (user_id, grade, score, total, date) VALUES (?, ?, ?, ?, ?)",
                 (user.id, quiz["grade"], score, total, datetime.now().strftime("%Y-%m-%d %H:%M")))
    conn.commit()
    conn.close()
    pct = (score / total) * 100
    msg = f"انتهى!\n\n{feedback_text}\n\nنتيجتك: {score}/{total} ({pct:.0f}%)\n\n/menu"
    await query.edit_message_text(msg,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("القائمة", callback_data="back_menu")]]))

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text

    if context.user_data.get("expecting_feedback"):
        context.user_data["expecting_feedback"] = False
        conn = get_db()
        conn.execute("INSERT INTO feedback (user_id, message, date) VALUES (?, ?, ?)",
                     (user.id, text, datetime.now().strftime("%Y-%m-%d %H:%M")))
        conn.commit()
        teacher = conn.execute("SELECT chat_id FROM teacher WHERE id = 1").fetchone()
        conn.close()
        if teacher:
            try:
                await context.bot.send_message(chat_id=teacher["chat_id"],
                    text=f"رسالة من {user.first_name}:\n\n{text}")
            except Exception as e:
                logger.error(f"Send err: {e}")
        await update.message.reply_text("تم إرسال رسالتك!")
        return

    step = context.user_data.get("mat_step")
    if step is not None:
        if step == "topic":
            context.user_data["mat_topic"] = text
            context.user_data["mat_step"] = "content"
            await update.message.reply_text("أرسل نص المادة (محتوى الدرس):")
            return
        elif step == "content":
            context.user_data["mat_content"] = text
            context.user_data["mat_step"] = "summary"
            await update.message.reply_text("أرسل الملخص:")
            return
        elif step == "summary":
            context.user_data["mat_summary"] = text
            context.user_data["mat_step"] = "questions"
            await update.message.reply_text("أرسل الأسئلة:")
            return
        elif step == "questions":
            context.user_data["mat_questions"] = text
            context.user_data["mat_step"] = "date"
            await update.message.reply_text("أرسل تاريخ الحصة (مثال: 2026-06-15):")
            return
        elif step == "date":
            try:
                class_date = datetime.strptime(text.strip(), "%Y-%m-%d").strftime("%Y-%m-%d")
            except:
                await update.message.reply_text("صيغة خاطئة. أرسل التاريخ بصيغة YYYY-MM-DD (مثال: 2026-06-15):")
                return
            conn = get_db()
            conn.execute("""INSERT INTO materials (grade, topic, content, summary, questions, class_date, created_at)
                         VALUES (?, ?, ?, ?, ?, ?, ?)""",
                         (context.user_data["mat_grade"], context.user_data["mat_topic"],
                          context.user_data["mat_content"], context.user_data["mat_summary"],
                          context.user_data["mat_questions"], class_date,
                          datetime.now().strftime("%Y-%m-%d %H:%M")))
            conn.commit()
            conn.close()
            context.user_data["mat_step"] = None
            context.user_data["mat_grade"] = None
            context.user_data["mat_topic"] = None
            context.user_data["mat_content"] = None
            context.user_data["mat_summary"] = None
            context.user_data["mat_questions"] = None
            await update.message.reply_text(f"تم حفظ المادة! سيتم إرسالها تلقائياً.\nقبل الحصة بيوم: المادة + الملخص\nيوم الحصة: الأسئلة")
            return

    await update.message.reply_text("الأوامر: /start /menu /help")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "/start - تسجيل\n/menu - القائمة\n/quiz - اختبار\n/lesson - دروس\n"
        "/score - نقاطي\n/leaderboard - ترتيب\n/schedule - جدول\n"
        "/feedback - للمعلم\n/register_group 9|10|11 - تسجيل مجموعة (في المجموعة)\n"
        "/add_material - إضافة مادة (للمعلم)\n/myid - تسجيل كمعلم",
        parse_mode="Markdown"
    )

async def quiz_shortcut(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    conn = get_db()
    student = conn.execute("SELECT grade FROM students WHERE user_id = ?", (user.id,)).fetchone()
    conn.close()
    if not student:
        await update.message.reply_text("سجل عبر /start")
        return
    grade = student["grade"]
    qs = جميع_الأسئلة.get(grade, [])
    if not qs:
        await update.message.reply_text("لا توجد أسئلة")
        return
    selected = random.sample(qs, min(10, len(qs)))
    context.user_data["quiz"] = {"grade": grade, "questions": selected, "index": 0, "score": 0}
    q = selected[0]
    buttons = [[InlineKeyboardButton(o, callback_data=f"answer_{i}")] for i, o in enumerate(q["خيارات"])]
    buttons.append([InlineKeyboardButton("إلغاء", callback_data="back_menu")])
    await update.message.reply_text(f"س{q['السؤال']}", reply_markup=InlineKeyboardMarkup(buttons))

async def score_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    conn = get_db()
    s = conn.execute("SELECT * FROM students WHERE user_id = ?", (user.id,)).fetchone()
    if s:
        r = conn.execute("SELECT COUNT(*)+1 as r FROM students WHERE score > (SELECT score FROM students WHERE user_id = ?)", (user.id,)).fetchone()
        rank = r["r"] if r else "?"
        conn.close()
        await update.message.reply_text(f"نقاطك: {s['score']}\nاختباراتك: {s['quizzes_taken']}\nترتيبك: #{rank}")
    else:
        conn.close()
        await update.message.reply_text("سجل عبر /start")

async def leaderboard_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = get_db()
    students = conn.execute("SELECT first_name, grade, score FROM students ORDER BY score DESC LIMIT 15").fetchall()
    conn.close()
    if not students:
        await update.message.reply_text("لا يوجد طلاب")
        return
    text = "الترتيب:\n"
    for i, s in enumerate(students, 1):
        m = {1:"1.", 2:"2.", 3:"3."}.get(i, f"{i}.")
        text += f"{m} {s['first_name']} - {get_grade_name(s['grade'])} - {s['score']}\n"
    await update.message.reply_text(text)

async def lesson_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    conn = get_db()
    s = conn.execute("SELECT grade FROM students WHERE user_id = ?", (user.id,)).fetchone()
    conn.close()
    if not s:
        await update.message.reply_text("سجل عبر /start")
        return
    lessons = دروس.get(s["grade"], [])
    text = f"دروس {get_grade_name(s['grade'])}:\n"
    for i, l in enumerate(lessons, 1):
        text += f"{i}. {l['عنوان']}\n"
    text += "\n/menu"
    await update.message.reply_text(text)

async def feedback_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["expecting_feedback"] = True
    await update.message.reply_text("أرسل رسالتك:")

async def schedule_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("التاسع", callback_data="schedule_9")],
        [InlineKeyboardButton("العاشر", callback_data="schedule_10")],
        [InlineKeyboardButton("الحادي عشر", callback_data="schedule_11")],
    ]
    await update.message.reply_text("اختر صفك:", reply_markup=InlineKeyboardMarkup(keyboard))

async def myid_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    conn = get_db()
    conn.execute("INSERT OR REPLACE INTO teacher (id, chat_id) VALUES (1, ?)", (uid,))
    conn.commit()
    conn.close()
    await update.message.reply_text(f"معرفك: {uid}\nتم تسجيلك كمعلم!")

async def register_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    conn = get_db()
    t = conn.execute("SELECT chat_id FROM teacher WHERE id = 1").fetchone()
    conn.close()
    if not t or t["chat_id"] != user.id:
        await update.message.reply_text("هذا الأمر للمعلم فقط. أرسل /myid أولاً.")
        return
    chat = update.effective_chat
    if chat.type == "private":
        await update.message.reply_text("هذا الأمر يعمل داخل المجموعة فقط.")
        return
    args = context.args
    if not args or args[0] not in ("9", "10", "11"):
        await update.message.reply_text("استخدم: /register_group 9  أو 10 أو 11\nمثال: /register_group 9")
        return
    grade = args[0]
    conn = get_db()
    conn.execute("INSERT OR REPLACE INTO groups (grade, chat_id, title) VALUES (?, ?, ?)",
                 (grade, chat.id, chat.title or ""))
    conn.commit()
    conn.close()
    await update.message.reply_text(f"تم تسجيل هذه المجموعة كمجموعة الصف {get_grade_name(grade)}!")

async def add_material(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    conn = get_db()
    t = conn.execute("SELECT chat_id FROM teacher WHERE id = 1").fetchone()
    conn.close()
    if not t or t["chat_id"] != user.id:
        await update.message.reply_text("هذا الأمر للمعلم فقط.")
        return
    keyboard = [
        [InlineKeyboardButton("التاسع", callback_data="mat_grade_9")],
        [InlineKeyboardButton("العاشر", callback_data="mat_grade_10")],
        [InlineKeyboardButton("الحادي عشر", callback_data="mat_grade_11")],
    ]
    await update.message.reply_text("اختر الصف:", reply_markup=InlineKeyboardMarkup(keyboard))

async def mat_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data.startswith("mat_grade_"):
        grade = data.split("_")[2]
        context.user_data["mat_grade"] = grade
        context.user_data["mat_step"] = "topic"
        await query.edit_message_text(f"اخترت {get_grade_name(grade)}\nأرسل اسم الموضوع:")
        return

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Error: {context.error}")

async def check_and_send(context: ContextTypes.DEFAULT_TYPE):
    """تشغيل كل دقيقة لفحص المواد المجدولة وإرسالها"""
    conn = get_db()
    today = date.today().isoformat()
    yesterday = (date.today() - timedelta(days=1)).isoformat()

    materials = conn.execute("SELECT * FROM materials WHERE sent_before = 0 OR sent_after = 0").fetchall()
    for mat in materials:
        grade = mat["grade"]
        group = conn.execute("SELECT chat_id FROM groups WHERE grade = ?", (grade,)).fetchone()
        if not group:
            continue

        # إرسال المادة + الملخص قبل الحصة بيوم
        if mat["class_date"] == today and mat["sent_before"] == 0:
            msg = f"مادة درس: {mat['topic']}\n\n{mat['content']}\n\nملخص:\n{mat['summary']}"
            try:
                await context.bot.send_message(chat_id=group["chat_id"], text=msg)
                conn.execute("UPDATE materials SET sent_before = 1 WHERE id = ?", (mat["id"],))
                conn.commit()
                logger.info(f"Sent material {mat['id']} to grade {grade}")
            except Exception as e:
                logger.error(f"Failed to send material {mat['id']}: {e}")

        # إرسال الأسئلة في يوم الحصة (نفس اليوم)
        if mat["class_date"] == today and mat["sent_after"] == 0:
            # نرسلها بعد الظهر تقريباً، نتحقق الوقت
            now = datetime.now()
            if now.hour >= 14:  # بعد الساعة 2 ظهراً
                msg = f"أسئلة مراجعة - {mat['topic']}\n\n{mat['questions']}"
                try:
                    await context.bot.send_message(chat_id=group["chat_id"], text=msg)
                    conn.execute("UPDATE materials SET sent_after = 1 WHERE id = ?", (mat["id"],))
                    conn.commit()
                    logger.info(f"Sent questions {mat['id']} to grade {grade}")
                except Exception as e:
                    logger.error(f"Failed to send questions {mat['id']}: {e}")

    conn.close()

def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", menu))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("quiz", quiz_shortcut))
    app.add_handler(CommandHandler("score", score_command))
    app.add_handler(CommandHandler("leaderboard", leaderboard_command))
    app.add_handler(CommandHandler("lesson", lesson_command))
    app.add_handler(CommandHandler("feedback", feedback_command))
    app.add_handler(CommandHandler("schedule", schedule_command))
    app.add_handler(CommandHandler("myid", myid_command))
    app.add_handler(CommandHandler("register_group", register_group))
    app.add_handler(CommandHandler("add_material", add_material))

    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(error_handler)

    # جدولة فحص المواد كل 60 ثانية
    job_queue = app.job_queue
    job_queue.run_repeating(check_and_send, interval=60, first=10)

    print("Bot running...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
