import json
import re
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
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

def valid_phone(phone):
    return re.fullmatch(r"05\d{8}", phone)

def valid_name(name):
    return len(name.strip().split()) >= 3

# ازرار انلاين للمستخدمين
async def send_role_buttons(message):
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("🚕 عميل", callback_data="role_client"))
    kb.add(InlineKeyboardButton("🧑‍✈️ كابتن", callback_data="role_captain"))
    await message.answer("مرحبًا! اختر نوع المستخدم:", reply_markup=kb)

@dp.message_handler(commands=['start'])
async def start(message: types.Message):
    user_states[message.from_user.id] = {"step": "role"}
    await send_role_buttons(message)

@dp.callback_query_handler(lambda c: c.data.startswith("role_"))
async def choose_role(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id
    role = callback_query.data.split("_")[1]
    user_states[user_id] = {"role": role, "step": "subscription"}
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("يومي", callback_data="sub_يومي"))
    kb.add(InlineKeyboardButton("شهري", callback_data="sub_شهري"))
    if role == "captain":
        kb.add(InlineKeyboardButton("كليهما", callback_data="sub_كليهما"))
    await bot.send_message(user_id, "اختر نوع الاشتراك:", reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data.startswith("sub_"))
async def process_subscription(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id
    subscription = callback_query.data.split("_", 1)[1]
    user_states[user_id]["subscription"] = subscription
    user_states[user_id]["step"] = "name"
    await bot.send_message(user_id, "اكتب اسمك الثلاثي:")

@dp.callback_query_handler(lambda c: c.data.startswith("city_"))
async def process_city(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id
    city = callback_query.data.split("_", 1)[1]
    user_states[user_id]["city"] = city
    user_states[user_id]["step"] = "neighborhood"
    kb = InlineKeyboardMarkup()
    for n in neighborhoods[city][:10]:
        kb.add(InlineKeyboardButton(n, callback_data=f"neigh_{n}"))
    await bot.send_message(user_id, "اختر الحي:", reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data.startswith("neigh_"))
async def process_neighborhood(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id
    area = callback_query.data.split("_", 1)[1]
    state = user_states[user_id]
    role = state["role"]

    if role == "client":
        state["neighborhood"] = area
        state["step"] = "confirm"
        await bot.send_message(user_id, "يتم الآن مطابقة الكباتن المتاحين لك...")
    else:
        if "neighborhoods" not in state:
            state["neighborhoods"] = []
        if area in state["neighborhoods"]:
            return await bot.send_message(user_id, "تم اختيار هذا الحي مسبقًا.")
        state["neighborhoods"].append(area)
        if len(state["neighborhoods"]) < 3:
            return await bot.send_message(user_id, f"اختر حي رقم {len(state['neighborhoods'])+1}:")
        state["step"] = "car_type"
        await bot.send_message(user_id, "اكتب نوع سيارتك:")

@dp.message_handler()
async def handle_all_messages(message: types.Message):
    user_id = message.from_user.id
    if user_id not in user_states:
        return await start(message)

    state = user_states[user_id]
    step = state.get("step")
    role = state.get("role")

    if message.text == "🔙 إلغاء":
        del user_states[user_id]
        return await start(message)

    if step == "name":
        if not valid_name(message.text):
            return await message.reply("الرجاء إدخال الاسم الثلاثي بشكل صحيح.")
        state["name"] = message.text
        state["step"] = "phone"
        return await message.answer("اكتب رقم جوالك (يبدأ بـ 05 ومكون من 10 أرقام):")

    elif step == "phone":
        if not valid_phone(message.text):
            return await message.reply("رقم الجوال غير صحيح.")
        state["phone"] = message.text
        state["step"] = "city"
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("الرياض", callback_data="city_الرياض"))
        kb.add(InlineKeyboardButton("جدة", callback_data="city_جدة"))
        return await message.answer("اختر مدينتك:", reply_markup=kb)

    elif role == "captain" and step == "car_type":
        state["car_type"] = message.text
        state["step"] = "plate_number"
        return await message.answer("اكتب رقم لوحة السيارة:")

    elif role == "captain" and step == "plate_number":
        state["plate_number"] = message.text
        state["step"] = "confirm"

    if state.get("step") == "confirm":
        if role == "client":
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
        await message.answer("تم حفظ معلوماتك بنجاح 🎉")

if __name__ == "__main__":
    print("البوت يعمل الآن ✅")
    from aiogram import executor
    executor.start_polling(dp)