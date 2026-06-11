import logging
import sqlite3
import random
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from questions import جميع_الأسئلة, دروس

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = "8744608803:AAFpiB8kGwd91CnrPcnX7okkjDcKFmffZkg"
CHANNEL_USERNAME = "@علوم_الارض_تاسع_عاشر_حادي_عشر"  # غير اسم القناة هنا
TEACHER_ID = None

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
    conn.commit()
    conn.close()

init_db()

def get_grade_name(grade):
    return {"9": "التاسع", "10": "العاشر", "11": "الحادي عشر"}.get(grade, grade)

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
            "استخدم /menu لعرض القائمة الرئيسية"
        )
    else:
        keyboard = [
            [InlineKeyboardButton("التاسع 🏫", callback_data="register_9")],
            [InlineKeyboardButton("العاشر 🏫", callback_data="register_10")],
            [InlineKeyboardButton("الحادي عشر 🏫", callback_data="register_11")],
        ]
        await update.message.reply_text(
            f"مرحباً بك {user.first_name} في بوت علوم الأرض!\n\n"
            "اختر صفك الدراسي للتسجيل:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    conn = get_db()
    student = conn.execute("SELECT * FROM students WHERE user_id = ?", (user.id,)).fetchone()
    conn.close()

    if not student:
        await update.message.reply_text("أولاً سجل صفك عبر /start")
        return

    keyboard = [
        [InlineKeyboardButton("🧪 اختبار", callback_data="menu_quiz"),
         InlineKeyboardButton("📖 درس", callback_data="menu_lesson")],
        [InlineKeyboardButton("🏆 نقاطي وترتيبي", callback_data="menu_score"),
         InlineKeyboardButton("✉️ رسالة للمعلم", callback_data="menu_feedback")],
        [InlineKeyboardButton("📅 جدول الأسبوع", callback_data="menu_schedule")]
    ]
    await update.message.reply_text(
        f"القائمة الرئيسية - {get_grade_name(student['grade'])}",
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
        await query.edit_message_text(
            f"تم تسجيلك في الصف {get_grade_name(grade)}!\n\n"
            "استخدم /menu للقائمة الرئيسية"
        )

    elif data == "menu_quiz":
        conn = get_db()
        student = conn.execute("SELECT grade FROM students WHERE user_id = ?", (user.id,)).fetchone()
        conn.close()
        if not student:
            await query.edit_message_text("سجل أولاً عبر /start")
            return
        grade = student["grade"]
        keyboard = [
            [InlineKeyboardButton("✅ ابدأ الاختبار", callback_data=f"start_quiz_{grade}")],
            [InlineKeyboardButton("🔙 رجوع", callback_data="back_menu")]
        ]
        await query.edit_message_text(
            f"اختبار الصف {get_grade_name(grade)}\n"
            "10 أسئلة اختيار من متعدد\n"
            "كل إجابة صحيحة = 10 نقاط\n\n"
            "جاهز؟",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif data.startswith("start_quiz_"):
        grade = data.split("_")[2]
        questions_list = جميع_الأسئلة.get(grade, [])
        if not questions_list:
            await query.edit_message_text("لا توجد أسئلة لهذا الصف حالياً")
            return
        selected = random.sample(questions_list, min(10, len(questions_list)))
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
        grade_name = get_grade_name(student["grade"]) if student else ""
        keyboard = [
            [InlineKeyboardButton("🧪 اختبار", callback_data="menu_quiz"),
             InlineKeyboardButton("📖 درس", callback_data="menu_lesson")],
            [InlineKeyboardButton("🏆 نقاطي وترتيبي", callback_data="menu_score"),
             InlineKeyboardButton("✉️ رسالة للمعلم", callback_data="menu_feedback")],
            [InlineKeyboardButton("📅 جدول الأسبوع", callback_data="menu_schedule")]
        ]
        await query.edit_message_text(
            f"القائمة الرئيسية - {grade_name}",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif data == "menu_lesson":
        conn = get_db()
        student = conn.execute("SELECT grade FROM students WHERE user_id = ?", (user.id,)).fetchone()
        conn.close()
        if not student:
            await query.edit_message_text("سجل أولاً عبر /start")
            return
        grade = student["grade"]
        lessons = دروس.get(grade, [])
        keyboard = []
        for i, lesson in enumerate(lessons):
            keyboard.append([InlineKeyboardButton(lesson["عنوان"], callback_data=f"lesson_{grade}_{i}")])
        keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data="back_menu")])
        await query.edit_message_text(
            f"دروس الصف {get_grade_name(grade)}:\nاختر درساً:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif data.startswith("lesson_"):
        parts = data.split("_")
        grade = parts[1]
        idx = int(parts[2])
        lessons = دروس.get(grade, [])
        if 0 <= idx < len(lessons):
            lesson = lessons[idx]
            keyboard = [[InlineKeyboardButton("🔙 للدروس", callback_data="menu_lesson"),
                         InlineKeyboardButton("🏠 القائمة", callback_data="back_menu")]]
            await query.edit_message_text(
                f"📖 {lesson['عنوان']}\n\n{lesson['محتوى']}",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

    elif data == "menu_score":
        conn = get_db()
        student = conn.execute("SELECT * FROM students WHERE user_id = ?", (user.id,)).fetchone()
        if student:
            leaderboard = conn.execute(
                "SELECT first_name, score FROM students ORDER BY score DESC LIMIT 10"
            ).fetchall()
            rank_row = conn.execute(
                "SELECT COUNT(*) + 1 as rank FROM students WHERE score > (SELECT score FROM students WHERE user_id = ?)",
                (user.id,)
            ).fetchone()
            rank = rank_row["rank"] if rank_row else "?"
            conn.close()

            lb_text = "🏆 *المتصدرون:*\n"
            for i, s in enumerate(leaderboard, 1):
                medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(i, f"{i}.")
                lb_text += f"{medal} {s['first_name']} - {s['score']} نقطة\n"

            await query.edit_message_text(
                f"*نقاطك:* {student['score']}\n"
                f"*اختباراتك:* {student['quizzes_taken']}\n"
                f"*ترتيبك:* #{rank}\n\n"
                f"{lb_text}\n"
                "كل اختبار 10 أسئلة × 10 نقاط = 100 نقطة",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="back_menu")]])
            )
        else:
            conn.close()
            await query.edit_message_text("سجل أولاً عبر /start")

    elif data == "menu_feedback":
        context.user_data["expecting_feedback"] = True
        await query.edit_message_text(
            "✉️ أرسل رسالتك للمعلم الآن:\n"
            "(سؤال، اقتراح، استفسار...)",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="back_menu")]])
        )

    elif data == "menu_schedule":
        keyboard = [
            [InlineKeyboardButton("📅 جدول التاسع", callback_data="schedule_9")],
            [InlineKeyboardButton("📅 جدول العاشر", callback_data="schedule_10")],
            [InlineKeyboardButton("📅 جدول الحادي عشر", callback_data="schedule_11")],
            [InlineKeyboardButton("🔙 رجوع", callback_data="back_menu")]
        ]
        await query.edit_message_text("اختر صفك لعرض الجدول:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith("schedule_"):
        grade = data.split("_")[1]
        schedules = {
            "9": "📅 *جدول التاسع - علوم الأرض*\n\n"
                 "الأحد: المعادن والصخور\n"
                 "الإثنين: العمليات الجيولوجية\n"
                 "الثلاثاء: تكتونية الصفائح\n"
                 "الأربعاء: الزلازل والبراكين\n"
                 "الخميس: مراجعة واختبار أسبوعي",
            "10": "📅 *جدول العاشر - علوم الأرض*\n\n"
                  "الأحد: الغلاف الجوي\n"
                  "الإثنين: الطقس والمناخ\n"
                  "الثلاثاء: دورة الماء\n"
                  "الأربعاء: المحيطات\n"
                  "الخميس: مراجعة واختبار أسبوعي",
            "11": "📅 *جدول الحادي عشر - علوم الأرض*\n\n"
                  "الأحد: المعادن والصناعة\n"
                  "الإثنين: التراكيب الجيولوجية\n"
                  "الثلاثاء: الموارد الطبيعية\n"
                  "الأربعاء: التغير المناخي\n"
                  "الخميس: مراجعة واختبار أسبوعي"
        }
        await query.edit_message_text(
            schedules.get(grade, "غير متوفر"),
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="menu_schedule")]])
        )

async def send_question(query, context):
    quiz = context.user_data.get("quiz")
    if not quiz:
        return
    idx = quiz["index"]
    questions = quiz["questions"]
    if idx >= len(questions):
        await finish_quiz(query, context)
        return

    q = questions[idx]
    buttons = []
    for i, option in enumerate(q["خيارات"]):
        buttons.append([InlineKeyboardButton(option, callback_data=f"answer_{i}")])
    buttons.append([InlineKeyboardButton("🔙 إلغاء", callback_data="back_menu")])

    await query.edit_message_text(
        f"*السؤال {idx + 1}/{len(questions)}*\n\n{q['السؤال']}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

async def handle_answer(query, context):
    quiz = context.user_data.get("quiz")
    if not quiz:
        return

    user_answer = int(query.data.split("_")[1])
    questions = quiz["questions"]
    idx = quiz["index"]
    q = questions[idx]
    correct = user_answer == q["الجواب"]

    if correct:
        quiz["score"] += 10

    answer_text = q["خيارات"][q["الجواب"]]
    feedback = "✅ إجابة صحيحة! +10 نقاط" if correct else f"❌ إجابة خاطئة\nالإجابة الصحيحة: {answer_text}"

    quiz["index"] += 1
    if quiz["index"] >= len(questions):
        await finish_quiz(query, context, feedback)
    else:
        await query.edit_message_text(
            f"{feedback}\n\nجارٍ السؤال التالي...",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("▶️ التالي", callback_data="next_question")]])
        )

async def finish_quiz(query, context, feedback_text=None):
    quiz = context.user_data.pop("quiz", None)
    if not quiz:
        return

    user = query.from_user
    grade = quiz["grade"]
    score = quiz["score"]
    total = len(quiz["questions"]) * 10

    conn = get_db()
    conn.execute("UPDATE students SET score = score + ?, quizzes_taken = quizzes_taken + 1 WHERE user_id = ?",
                 (score, user.id))
    conn.execute("INSERT INTO quiz_results (user_id, grade, score, total, date) VALUES (?, ?, ?, ?, ?)",
                 (user.id, grade, score, total, datetime.now().strftime("%Y-%m-%d %H:%M")))
    conn.commit()
    conn.close()

    percentage = (score / total) * 100
    stars = "⭐" * (score // 20)
    msg = f"🎉 *الاختبار انتهى!*\n\n"
    if feedback_text:
        msg += f"{feedback_text}\n\n"
    msg += (
        f"*نتيجتك:* {score} من {total}\n"
        f"*النسبة:* {percentage:.0f}%\n"
        f"{stars}\n\n"
        "استخدم /menu للعودة"
    )

    await query.edit_message_text(msg, parse_mode="Markdown",
                                  reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 القائمة", callback_data="back_menu")]]))

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("expecting_feedback"):
        context.user_data["expecting_feedback"] = False
        conn = get_db()
        conn.execute("INSERT INTO feedback (user_id, message, date) VALUES (?, ?, ?)",
                     (update.effective_user.id, update.message.text, datetime.now().strftime("%Y-%m-%d %H:%M")))
        conn.commit()
        teacher = conn.execute("SELECT chat_id FROM teacher WHERE id = 1").fetchone()
        conn.close()

        if teacher:
            try:
                await context.bot.send_message(
                    chat_id=teacher["chat_id"],
                    text=f"✉️ رسالة من {update.effective_user.first_name} (ID: {update.effective_user.id}):\n\n{update.message.text}"
                )
            except Exception as e:
                logger.error(f"Failed to send to teacher: {e}")

        await update.message.reply_text("✅ تم إرسال رسالتك للمعلم!")
        return

    await update.message.reply_text(
        "استخدم الأوامر التالية:\n"
        "/start - تسجيل الدخول\n"
        "/menu - القائمة الرئيسية\n"
        "/help - المساعدة"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎯 *أوامر البوت:*\n\n"
        "/start - تسجيل الصف\n"
        "/menu - القائمة الرئيسية\n"
        "/quiz - اختبار سريع\n"
        "/lesson - الدروس\n"
        "/score - نقاطي\n"
        "/leaderboard - ترتيب الطلاب\n"
        "/schedule - الجدول الأسبوعي\n"
        "/feedback - رسالة للمعلم\n"
        "/myid - معرفك (للمعلم)\n\n"
        "للاستفسارات: أرسل رسالة وسأرد عليك قريباً",
        parse_mode="Markdown"
    )

async def quiz_shortcut(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    conn = get_db()
    student = conn.execute("SELECT grade FROM students WHERE user_id = ?", (user.id,)).fetchone()
    conn.close()
    if not student:
        await update.message.reply_text("سجل أولاً عبر /start")
        return
    grade = student["grade"]
    questions_list = جميع_الأسئلة.get(grade, [])
    if not questions_list:
        await update.message.reply_text("لا توجد أسئلة")
        return
    selected = random.sample(questions_list, min(10, len(questions_list)))
    context.user_data["quiz"] = {"grade": grade, "questions": selected, "index": 0, "score": 0}
    q = selected[0]
    buttons = []
    for i, option in enumerate(q["خيارات"]):
        buttons.append([InlineKeyboardButton(option, callback_data=f"answer_{i}")])
    buttons.append([InlineKeyboardButton("🔙 إلغاء", callback_data="back_menu")])
    await update.message.reply_text(
        f"*السؤال 1/{len(selected)}*\n\n{q['السؤال']}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

async def score_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    conn = get_db()
    student = conn.execute("SELECT * FROM students WHERE user_id = ?", (user.id,)).fetchone()
    if student:
        rank_row = conn.execute(
            "SELECT COUNT(*) + 1 as rank FROM students WHERE score > (SELECT score FROM students WHERE user_id = ?)",
            (user.id,)
        ).fetchone()
        rank = rank_row["rank"] if rank_row else "?"
        conn.close()
        await update.message.reply_text(
            f"🏆 *نقاطك:* {student['score']}\n"
            f"📝 *اختباراتك:* {student['quizzes_taken']}\n"
            f"👑 *ترتيبك:* #{rank}",
            parse_mode="Markdown"
        )
    else:
        conn.close()
        await update.message.reply_text("سجل أولاً عبر /start")

async def leaderboard_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = get_db()
    students = conn.execute("SELECT first_name, grade, score FROM students ORDER BY score DESC LIMIT 15").fetchall()
    conn.close()
    if not students:
        await update.message.reply_text("لا يوجد طلاب مسجلين بعد")
        return
    text = "🏆 *ترتيب الطلاب:*\n\n"
    for i, s in enumerate(students, 1):
        medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(i, f"{i}.")
        text += f"{medal} {s['first_name']} - {get_grade_name(s['grade'])} - {s['score']} نقطة\n"
    await update.message.reply_text(text, parse_mode="Markdown")

async def lesson_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    conn = get_db()
    student = conn.execute("SELECT grade FROM students WHERE user_id = ?", (user.id,)).fetchone()
    conn.close()
    if not student:
        await update.message.reply_text("سجل أولاً عبر /start")
        return
    grade = student["grade"]
    lessons = دروس.get(grade, [])
    text = f"*دروس الصف {get_grade_name(grade)}:*\n\n"
    for i, lesson in enumerate(lessons, 1):
        text += f"{i}. {lesson['عنوان']}\n"
    text += "\nاستخدم /menu لاختيار درس"
    await update.message.reply_text(text, parse_mode="Markdown")

async def feedback_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["expecting_feedback"] = True
    await update.message.reply_text("✉️ أرسل رسالتك للمعلم الآن:")

async def schedule_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("📅 التاسع", callback_data="schedule_9")],
        [InlineKeyboardButton("📅 العاشر", callback_data="schedule_10")],
        [InlineKeyboardButton("📅 الحادي عشر", callback_data="schedule_11")],
    ]
    await update.message.reply_text("اختر صفك:", reply_markup=InlineKeyboardMarkup(keyboard))

async def myid_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    conn = get_db()
    conn.execute("INSERT OR REPLACE INTO teacher (id, chat_id) VALUES (1, ?)", (user_id,))
    conn.commit()
    conn.close()
    await update.message.reply_text(f"معرفك (ID): {user_id}\nتم تسجيلك كمعلم! الآن ستصل لك رسائل الطلاب.")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Exception: {context.error}")

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

    app.add_handler(CallbackQueryHandler(button_handler))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(error_handler)

    print("Bot is running... Press Ctrl+C to stop")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
