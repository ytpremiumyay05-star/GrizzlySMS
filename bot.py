import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, CopyTextButton
import requests
import threading
import time
from flask import Flask
import os

# Bot Config
BOT_TOKEN = "8867616150:AAFVpSMqqiBzyQXs1KbYdUWD_bx8LUCPdX8"
ADMIN_ID = 7266067201

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

# State Management
maintenance_mode = False
user_api_keys = {}
user_active_orders = {} # Format: {user_id: {activation_id: phone_number}}

# Checker API Config
CHECKER_URL = "http://api.agbots.site:8080/check/"
CHECKER_AUTH = "user8354"
CHECKER_API_KEY = "SIGUzg7Xf7euGs8B"

STATUS_EMOJIS = {
    "fresh": "🟢",
    "banned": "🔴",
    "registered": "🟡",
    "locked": "🔒",
    "2fa": "🔐"
}

def check_tg_number(phone_number):
    if not phone_number.startswith("+"):
        phone_number = "+" + phone_number
        
    payload = {
        "auth": CHECKER_AUTH,
        "api_key": CHECKER_API_KEY,
        "phone_numbers": [phone_number]
    }
    
    try:
        response = requests.get(CHECKER_URL, json=payload, timeout=60)
        if response.status_code == 200:
            data = response.json()
            if str(data.get("status")) == "200":
                result_obj = data.get("result_obj", {})
                status = str(result_obj.get(phone_number, "unknown")).lower()
                return STATUS_EMOJIS.get(status, "❓")
    except Exception:
        pass
    
    return "❓"

def wait_for_otp(chat_id, user_id, api_key, activation_id, phone_number):
    url = f"https://api.grizzlysms.com/stubs/handler_api.php?api_key={api_key}&action=getStatus&id={activation_id}"
    
    for _ in range(60): 
        # Jodi user nije theke /active theke cancel kore dey, tahole thread off hoye jabe
        if user_id not in user_active_orders or activation_id not in user_active_orders.get(user_id, {}):
            return

        time.sleep(5)
        try:
            res = requests.get(url, timeout=10)
            response_text = res.text
            
            if response_text.startswith("STATUS_OK"):
                otp = response_text.split(":")[1]
                
                # OTP ashle list theke shoriye dibe
                if user_id in user_active_orders and activation_id in user_active_orders[user_id]:
                    del user_active_orders[user_id][activation_id]
                
                text = f"✅ **OTP Received!**\n\n🇨🇴 Telegram `{phone_number}`"
                
                markup = InlineKeyboardMarkup()
                markup.add(InlineKeyboardButton(text=f"{otp}", copy_text=CopyTextButton(text=otp)))
                
                bot.send_message(chat_id, text, reply_markup=markup, parse_mode="Markdown")
                return
            elif response_text == "STATUS_CANCEL":
                if user_id in user_active_orders and activation_id in user_active_orders[user_id]:
                    del user_active_orders[user_id][activation_id]
                bot.send_message(chat_id, f"❌ Automatically Cancelled: `{phone_number}`", parse_mode="Markdown")
                return
        except Exception:
            pass
            
    # Timeout hole list theke remove hobe
    if user_id in user_active_orders and activation_id in user_active_orders[user_id]:
        del user_active_orders[user_id][activation_id]
    bot.send_message(chat_id, f"⏱ Timeout! Kono OTP asheni: `{phone_number}`", parse_mode="Markdown")

@bot.message_handler(commands=['start'])
def start_command(message):
    if maintenance_mode and message.from_user.id != ADMIN_ID:
        return
        
    text = "Bot e swagotom! 🚀\n\n🔑 API key set korte likho:\n`/api <tomar_api_key>`\n\n🛒 Number kinte likho:\n`/buy`\n\n🟢 Active number dekhte & Cancel korte likho:\n`/active`"
    bot.send_message(message.chat.id, text, parse_mode="Markdown")

@bot.message_handler(commands=['api'])
def api_command(message):
    if maintenance_mode and message.from_user.id != ADMIN_ID:
        return
        
    args = message.text.split()
    if len(args) > 1:
        user_key = args[1]
        user_api_keys[message.from_user.id] = user_key
        bot.send_message(message.chat.id, "✅ API key successfully saved!")
    else:
        current_key = user_api_keys.get(message.from_user.id, "Ekhono kono API key set kora hoyni.")
        bot.send_message(message.chat.id, f"Tomar current API key:\n`{current_key}`\n\nChange korte likho:\n`/api <notun_key>`", parse_mode="Markdown")

@bot.message_handler(commands=['admin'])
def admin_command(message):
    if message.from_user.id != ADMIN_ID:
        return
        
    args = message.text.split()
    global maintenance_mode
    
    if len(args) > 1:
        if args[1].lower() == "on":
            maintenance_mode = True
            bot.send_message(message.chat.id, "🛠 Maintenance mode ON kora hoyeche.")
        elif args[1].lower() == "off":
            maintenance_mode = False
            bot.send_message(message.chat.id, "✅ Maintenance mode OFF kora hoyeche.")

@bot.message_handler(commands=['active'])
def active_command(message):
    user_id = message.from_user.id
    orders = user_active_orders.get(user_id, {})
    
    if not orders:
        bot.send_message(message.chat.id, "Tomar ekhon kono active order nei.")
        return
        
    text = "🟢 **Tomar Active Number Gula:**\n*(Number e tap korlei copy hobe)*\n\n"
    markup = InlineKeyboardMarkup(row_width=1)
    
    for act_id, phone in list(orders.items()):
        text += f"• `{phone}`\n"
        markup.add(InlineKeyboardButton(text=f"Cancel {phone} ❌", callback_data=f"cancel_{act_id}_{phone}"))
        
    bot.send_message(message.chat.id, text, reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith("cancel_"))
def cancel_order_callback(call):
    parts = call.data.split("_")
    act_id = parts[1]
    phone = parts[2]
    user_id = call.from_user.id
    
    api_key = user_api_keys.get(user_id)
    if not api_key:
        bot.answer_callback_query(call.id, "API key pawa jayni!", show_alert=True)
        return
        
    # API te Cancel request pathano (status=8)
    cancel_url = f"https://api.grizzlysms.com/stubs/handler_api.php?api_key={api_key}&action=setStatus&status=8&id={act_id}"
    
    try:
        requests.get(cancel_url, timeout=10)
        
        # Local list theke remove kora
        if user_id in user_active_orders and act_id in user_active_orders[user_id]:
            del user_active_orders[user_id][act_id]
            
        bot.answer_callback_query(call.id, f"{phone} Cancel kora hoyeche & Taka Refund hoyeche!", show_alert=True)
        
        # UI theke button ti remove kora / list update kora
        orders = user_active_orders.get(user_id, {})
        if not orders:
            bot.edit_message_text("✅ Tomar shob active number cancel hoye geche.", chat_id=call.message.chat.id, message_id=call.message.message_id)
        else:
            text = "🟢 **Tomar Active Number Gula:**\n*(Number e tap korlei copy hobe)*\n\n"
            markup = InlineKeyboardMarkup(row_width=1)
            for a_id, p_num in list(orders.items()):
                text += f"• `{p_num}`\n"
                markup.add(InlineKeyboardButton(text=f"Cancel {p_num} ❌", callback_data=f"cancel_{a_id}_{p_num}"))
            bot.edit_message_text(text, chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=markup, parse_mode="Markdown")
            
    except Exception:
        bot.answer_callback_query(call.id, "API er sathe connect kora jayni.", show_alert=True)

@bot.message_handler(commands=['buy'])
def buy_command(message):
    if maintenance_mode and message.from_user.id != ADMIN_ID:
        return
        
    api_key = user_api_keys.get(message.from_user.id)
    if not api_key:
        bot.send_message(message.chat.id, "⚠️ Doyakore age /api command diye API key set koro.", parse_mode="Markdown")
        return
        
    msg = bot.send_message(message.chat.id, "Koyta number kinte chao? (Jemon: 1, 5, 10)")
    bot.register_next_step_handler(msg, process_buy_amount, api_key)

def process_buy_amount(message, api_key):
    if not message.text.isdigit():
        bot.send_message(message.chat.id, "Sothik number dewa hoyni. Abar /buy try koro.")
        return
        
    amount = int(message.text)
    if amount <= 0:
        bot.send_message(message.chat.id, "Amount 0 er cheye beshi hote hobe.")
        return
        
    if amount > 20:
        bot.send_message(message.chat.id, "Eksathe max 20 ta number order kora jabe. 20 ta processing hocche...")
        amount = 20
        
    user_id = message.from_user.id
    if user_id not in user_active_orders:
        user_active_orders[user_id] = {}
        
    # Live updating message
    text = f"🛒 **Tomar Order List:**\n\n"
    msg = bot.send_message(message.chat.id, text + "Processing... ⏳", parse_mode="Markdown")
    
    buy_url = f"https://api.grizzlysms.com/stubs/handler_api.php?api_key={api_key}&action=getNumber&service=tg&country=33&maxPrice=0.12"
    
    for i in range(amount):
        try:
            res = requests.get(buy_url, timeout=30)
            response_text = res.text
            
            if response_text.startswith("ACCESS_NUMBER"):
                parts = response_text.split(":")
                activation_id = parts[1]
                phone_number = parts[2]
                
                emoji_status = check_tg_number(phone_number)
                text += f"{i+1}. `{phone_number}` {emoji_status}\n"
                
                # Active list e add kora
                user_active_orders[user_id][activation_id] = phone_number
                
                bot.edit_message_text(text + f"\n⏳ Baki gula asche... ({i+1}/{amount})", chat_id=message.chat.id, message_id=msg.message_id, parse_mode="Markdown")
                
                threading.Thread(target=wait_for_otp, args=(message.chat.id, user_id, api_key, activation_id, phone_number)).start()
                
            else:
                text += f"{i+1}. ❌ Failed (`{response_text}`)\n"
                bot.edit_message_text(text + f"\n⏳ Baki gula asche... ({i+1}/{amount})", chat_id=message.chat.id, message_id=msg.message_id, parse_mode="Markdown")
                
                if response_text in ["NO_BALANCE", "NO_NUMBERS", "BAD_KEY"]:
                    text += "\n⚠️ API Error er karone order stop kora holo."
                    break
                    
        except Exception:
            text += f"{i+1}. ⚠️ Connection Error\n"
            break
            
        time.sleep(1)
        
    bot.edit_message_text(text + "\n✅ **Order Complete!**\nManage/Cancel korte `/active` command dao.", chat_id=message.chat.id, message_id=msg.message_id, parse_mode="Markdown")

# --- Render Dummy Server ---
@app.route('/')
def index():
    return "Bot is running on Polling mode!"

def run_server():
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

if __name__ == "__main__":
    threading.Thread(target=run_server, daemon=True).start()
    bot.remove_webhook()
    time.sleep(1)
    bot.infinity_polling(skip_pending=True)
