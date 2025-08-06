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
        return {"clients": [], "captains": [], "matches": []}

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

        # نبحث الكباتن المناسبين ونرسل لهم رسالة مع الأحياء المشتركة
        matches = []
        for c in db["captains"]:
            if state["city"] == c["city"]:
                common_areas = set([area]) & set(c.get("neighborhoods", []))
                if common_areas:
                    matches.append({
                        "captain": c,
                        "common_areas": list(common_areas)
                    })

        if not matches:
            await bot.send_message(user_id, "لا يوجد كباتن متاحين الآن في حيّك.")
            user_states.pop(user_id, None)  # انهاء الحالة
            return
        
        kb = InlineKeyboardMarkup()
        for i, match in enumerate(matches):
            c = match["captain"]
            common_areas_text = ", ".join(match["common_areas"])
            kb.add(InlineKeyboardButton(
                f"{c['name']} - {c.get('car_type', '')} - لوحة: {c.get('plate_number', '')}\nالأحياء المشتركة: {common_areas_text}",
                callback_data=f"choose_captain_{i}"
            ))
        await bot.send_message(user_id, "اختر كابتن من القائمة:", reply_markup=kb)

        # نحفظ مؤقتًا قائمة الكباتن المطابقة للحالة
        state["matches"] = matches

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

@dp.callback_query_handler(lambda c: c.data.startswith("choose_captain_"))
async def choose_captain_callback(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id
    if user_id not in user_states:
        return await callback_query.answer("الرجاء بدء التسجيل أولاً.")
    state = user_states[user_id]
    if state.get("role") != "client":
        return await callback_query.answer("هذه العملية مخصصة للعملاء فقط.")
    idx = int(callback_query.data.split("_")[-1])
    matches = state.get("matches", [])
    if idx >= len(matches):
        return await callback_query.answer("اختيار غير صالح.")
    chosen_captain = matches[idx]["captain"]

    # حفظ بيانات العميل (مضافة user_id)
    state["user_id"] = user_id

    # حفظ بيانات العميل في قاعدة البيانات (إذا لم يكن موجود)
    existing_clients = [c for c in db["clients"] if c.get("user_id") == user_id]
    if existing_clients:
        for i, c in enumerate(db["clients"]):
            if c.get("user_id") == user_id:
                db["clients"][i] = state
                break
    else:
        db["clients"].append(state)

    save_db(db)

    # حفظ الربط مؤقتًا مع حالة انتظار موافقة الكابتن
    user_states[user_id]["chosen_captain"] = chosen_captain
    user_states[user_id]["step"] = "waiting_captain_response"

    # إرسال رسالة للكابتن مع خيارات قبول أو رفض
    captain_id = chosen_captain.get("user_id")
    if not captain_id:
        await callback_query.answer("لا يمكن التواصل مع هذا الكابتن (مفقود معرف).")
        return

    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("✅ قبول", callback_data=f"captain_response_accept_{user_id}"))
    kb.add(InlineKeyboardButton("❌ رفض", callback_data=f"captain_response_reject_{user_id}"))

    try:
        await bot.send_message(
            captain_id,
            f"العميل {state['name']} اختارك، هل تقبل؟",
            reply_markup=kb
        )
    except Exception:
        await callback_query.answer("تعذر إرسال الرسالة للكابتن.")
        return

    await callback_query.answer("تم إرسال طلب الموافقة للكابتن، انتظر الرد.")

@dp.callback_query_handler(lambda c: c.data.startswith("captain_response_"))
async def captain_response_handler(callback_query: types.CallbackQuery):
    data = callback_query.data.split("_")
    response = data[2]  # accept أو reject
    client_id = int(data[3])

    # تحقق من وجود حالة العميل
    if client_id not in user_states:
        return await callback_query.answer("حالة العميل غير موجودة أو انتهت.")

    client_state = user_states[client_id]
    chosen_captain = client_state.get("chosen_captain")
    if not chosen_captain:
        return await callback_query.answer("لا يوجد كابتن مختار.")

    captain_id = callback_query.from_user.id
    if chosen_captain.get("user_id") != captain_id:
        return await callback_query.answer("أنت غير مخول للرد على هذا الطلب.")

    if response == "accept":
        # تحديث قاعدة البيانات بإضافة العلاقة النهائية في matches
        if "matches" not in db:
            db["matches"] = []

        db["matches"].append({
            "client_id": client_id,
            "client_name": client_state["name"],
            "captain_id": captain_id,
            "captain_name": chosen_captain["name"],
            "city": client_state["city"],
            "neighborhood": client_state["neighborhood"],
            "common_areas": list(set([client_state["neighborhood"]]) & set(chosen_captain.get("neighborhoods", []))),
            "status": "accepted"
        })
        save_db(db)

        # رسالة للعميل باسم الكابتن ويوزره
        captain_username = chosen_captain.get("username")
        username_text = f"@{captain_username}" if captain_username else "لا يوجد اسم مستخدم متاح"

        await bot.send_message(client_id, f"الكابتن {chosen_captain['name']} قبل طلبك ✅\nيمكنك التواصل معه على الخاص عبر: {username_text}")

        await callback_query.answer("تم قبول الطلب، تم إعلام العميل.")

        # احذف حالة العميل لأنه تمت الموافقة
        user_states.pop(client_id, None)

    else:
        # رفض الكابتن
        await bot.send_message(client_id, f"الكابتن {chosen_captain['name']} رفض طلبك ❌")
        await callback_query.answer("تم رفض الطلب، تم إعلام العميل.")

        # يمكن هنا إعادة العميل لاختيار كابتن آخر لو تريد، أو حذف الحالة:
        user_states.pop(client_id, None)

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
        # خزن username تلقائيًا
        state["username"] = message.from_user.username or ""
        state["user_id"] = user_id
        state["step"] = "confirm"

    if state.get("step") == "confirm":
        if role == "captain":
            # تأكد من عدم تكرار التسجيل لنفس user_id
            existing_captains = [c for c in db["captains"] if c.get("user_id") == user_id]
            if existing_captains:
                # تحديث بيانات الكابتن بدل الإضافة
                for i, c in enumerate(db["captains"]):
                    if c.get("user_id") == user_id:
                        db["captains"][i] = state
                        break
            else:
                db["captains"].append(state)

            save_db(db)
            await message.answer("تم تسجيلك ككابتن بنجاح ✅")
            del user_states[user_id]
        else:
            await message.answer("يرجى اختيار كابتن من القائمة.")

if __name__ == "__main__":
    print("البوت يعمل الآن ✅")
    from aiogram import executor
    executor.start_polling(dp)
