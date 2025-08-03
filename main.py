import json
from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from config import BOT_TOKEN
import pandas as pd

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

# تحميل الأحياء من الإكسل
excel_path = "neighborhoods.xlsx"
neighborhoods = {
    "الرياض": pd.read_excel(excel_path, sheet_name="الرياض")["المنطقة"].dropna().tolist(),
    "جدة": pd.read_excel(excel_path, sheet_name="جدة")["المنطقة"].dropna().tolist()
}

# قاعدة بيانات مؤقتة
DB_FILE = "database.json"

def load_db():
    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {"clients": [], "captains": []}

def save_db(data):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

db = load_db()
user_states = {}

# البداية
@dp.message_handler(commands=['start'])
async def start(message: types.Message):
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("🚕 عميل"), KeyboardButton("🧑‍✈️ كابتن"))
    await message.answer("مرحبًا! اختر نوع المستخدم:", reply_markup=kb)
    user_states[message.from_user.id] = {"step": "role"}

# استقبال الدور
@dp.message_handler(lambda msg: msg.text in ["🚕 عميل", "🧑‍✈️ كابتن"])
async def choose_role(message: types.Message):
    user_id = message.from_user.id
    role = "client" if "عميل" in message.text else "captain"
    user_states[user_id] = {"role": role, "step": "subscription"}
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("يومي"), KeyboardButton("شهري"))
    if role == "captain":
        kb.add(KeyboardButton("كليهما"))
    await message.answer("اختر نوع الاشتراك:", reply_markup=kb)

# استمرار التدرج حسب الحالة
@dp.message_handler()
async def handle_flow(message: types.Message):
    user_id = message.from_user.id
    if user_id not in user_states:
        return await start(message)

    state = user_states[user_id]
    role = state["role"]
    step = state["step"]

    def ask(q):
        return message.answer(q, reply_markup=ReplyKeyboardMarkup(resize_keyboard=True).add(KeyboardButton("🔙 إلغاء")))

    if message.text == "🔙 إلغاء":
        del user_states[user_id]
        return await start(message)

    if step == "subscription":
        state["subscription"] = message.text
        state["step"] = "name"
        return await ask("اكتب اسمك الثلاثي:")

    if step == "name":
        state["name"] = message.text
        state["step"] = "phone"
        return await ask("اكتب رقم جوالك:")

    if step == "phone":
        state["phone"] = message.text
        state["step"] = "city"
        kb = ReplyKeyboardMarkup(resize_keyboard=True)
        kb.add(KeyboardButton("الرياض"), KeyboardButton("جدة"))
        return await message.answer("اختر مدينتك:", reply_markup=kb)

    if step == "city":
        if message.text not in ["الرياض", "جدة"]:
            return await ask("اختر مدينة صحيحة.")
        state["city"] = message.text
        state["step"] = "neighborhood"
        kb = ReplyKeyboardMarkup(resize_keyboard=True)
        for area in neighborhoods[message.text][:10]:  # أول 10 فقط
            kb.add(KeyboardButton(area))
        return await message.answer("اختر الحي:", reply_markup=kb)

    if step == "neighborhood":
        if message.text not in neighborhoods[state["city"]]:
            return await ask("الحي غير موجود. اختر من القائمة.")
        if role == "client":
            state["neighborhood"] = message.text
            state["step"] = "confirm"
        else:
            if "neighborhoods" not in state:
                state["neighborhoods"] = []
            state["neighborhoods"].append(message.text)
            if len(state["neighborhoods"]) < 3:
                return await ask(f"اختر حي رقم {len(state['neighborhoods']) + 1} (مجموع 3)")
            state["step"] = "car_type"
        if role == "client":
            return await ask("يتم الآن مطابقة الكباتن المتاحين لك...")

    if role == "captain" and step == "car_type":
        state["car_type"] = message.text
        state["step"] = "car_capacity"
        return await ask("كم راكب تستوعب سيارتك؟")

    if role == "captain" and step == "car_capacity":
        state["car_capacity"] = message.text
        state["step"] = "confirm"

    if step == "confirm":
        if role == "client":
            # مطابقة الأحياء
            matches = [c for c in db["captains"] if state["city"] == c["city"] and state["neighborhood"] in c["neighborhoods"]]
            if not matches:
                await message.answer("لا يوجد كباتن متاحين الآن في حيّك.")
            else:
                await message.answer("الكباتن المتاحين:\n" + "\n".join([f"{c['name']} ({c['car_type']})" for c in matches]))
        elif role == "captain":
            await message.answer("تم تسجيلك ككابتن بنجاح ✅")

        db[role + "s"].append(state)
        save_db(db)
        del user_states[user_id]
        return await message.answer("تم حفظ معلوماتك بنجاح 🎉")
if __name__ == "__main__":
    print("البوت يعمل الآن ✅")
    from aiogram import executor
    executor.start_polling(dp)

