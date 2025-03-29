import requests
import json
import time
from datetime import datetime
import pytz
import random
import string
from pymongo import MongoClient
from threading import Timer

# Configuration
TOKEN = "1160037511:Dc8btl6zj31YgbocUgrQ5ImVb5DaPWZKXGHC7Pbv"
BASE_URL = f"https://tapi.bale.ai/bot{TOKEN}"
CHANNEL_ID = 5272323810 # Replace with your channel ID
WHITELIST = ["zonercm", "id_hormoz"]  # Whitelisted usernames
POLLING_INTERVAL = 0.1  # 250ms
ADMIN_COMMAND = "پنل"

# MongoDB setup
client = MongoClient('mongodb://mongo:WhLUfhKsSaOtcqOkzjnPoNqLMpboQTan@yamabiko.proxy.rlwy.net:34347')
db = client['telegram_bot']
files_collection = db['files']
texts_collection = db['texts']
users_collection = db['users']

# Helper functions
def get_iran_time():
    tz = pytz.timezone('Asia/Tehran')
    now = datetime.now(tz)
    return now.strftime("%Y/%m/%d %H:%M:%S")

def generate_random_code(length=8):
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

def send_message(chat_id, text, reply_markup=None):
    url = f"{BASE_URL}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML"
    }
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    requests.post(url, json=payload)

def delete_message(chat_id, message_id):
    url = f"{BASE_URL}/deleteMessage"
    payload = {
        "chat_id": chat_id,
        "message_id": message_id
    }
    requests.post(url, json=payload)

def get_chat_member(channel_id, user_id):
    url = f"{BASE_URL}/getChatMember"
    payload = {
        "chat_id": channel_id,
        "user_id": user_id
    }
    response = requests.post(url, json=payload)
    return response.json()

def is_user_member(channel_id, user_id):
    try:
        member_info = get_chat_member(channel_id, user_id)
        return member_info.get('result', {}).get('status') in ['member', 'administrator', 'creator']
    except:
        return False

def send_file(chat_id, file_id, caption=None):
    url = f"{BASE_URL}/sendDocument"
    payload = {
        "chat_id": chat_id,
        "document": file_id
    }
    if caption:
        payload["caption"] = caption
    requests.post(url, json=payload)

def send_photo(chat_id, photo_id, caption=None):
    url = f"{BASE_URL}/sendPhoto"
    payload = {
        "chat_id": chat_id,
        "photo": photo_id
    }
    if caption:
        payload["caption"] = caption
    requests.post(url, json=payload)

# State management for admin actions
admin_states = {}

# Main bot logic
def process_update(update):
    if "message" in update:
        message = update["message"]
        chat_id = message["chat"]["id"]
        user_id = message["from"]["id"]
        username = message["from"].get("username", "")
        first_name = message["from"].get("first_name", "کاربر")
        
        # Check channel membership
        if not is_user_member(CHANNEL_ID, user_id):
            if "text" in message and message["text"].startswith("/start"):
                # Don't show join message for /start commands to avoid loops
                return
            
            keyboard = {
                "inline_keyboard": [
                    [{"text": "عضویت در کانال 📢", "url": f"https://t.me/{CHANNEL_ID}"}],
                    [{"text": "بررسی عضویت ♻️", "callback_data": f"check_membership:{chat_id}:{message['message_id']}"}]
                ]
            }
            greeting = f"سلام {first_name}!\n\n⏰ زمان ایران: {get_iran_time()}\n\nلطفا ابتدا در کانال ما عضو شوید تا بتوانید از ربات استفاده کنید."
            send_message(chat_id, greeting, keyboard)
            return
        
        # Greet user
        if "text" in message and message["text"].lower() == "/start":
            greeting = f"سلام {first_name}! 👋\n\n📅 تاریخ ایران: {get_iran_time()}\n\nبه ربات آپلودر خوش آمدید!"
            send_message(chat_id, greeting)
            
            # Save user to database
            users_collection.update_one(
                {"user_id": user_id},
                {"$set": {
                    "username": username,
                    "first_name": first_name,
                    "chat_id": chat_id,
                    "joined_at": datetime.now()
                }},
                upsert=True
            )
            return
        
        # Check for start codes
        if "text" in message and message["text"].startswith("/start"):
            parts = message["text"].split()
            if len(parts) > 1:
                code = parts[1]
                # Check for file
                file_data = files_collection.find_one({"code": code})
                if file_data:
                    send_file(chat_id, file_data["file_id"], file_data.get("caption"))
                    return
                
                # Check for text
                text_data = texts_collection.find_one({"code": code})
                if text_data:
                    send_message(chat_id, text_data["text"])
                    return
        
        # Admin panel
        if username in WHITELIST and "text" in message and message["text"] == ADMIN_COMMAND:
            greeting = f"سلام ادمین {first_name}! 👑\n\n⏰ زمان ایران: {get_iran_time()}\n\nبه پنل مدیریت خوش آمدید!"
            keyboard = {
                "inline_keyboard": [
                    [{"text": "آپلود فایل 📁", "callback_data": "upload_file"}],
                    [{"text": "آپلود متن 📝", "callback_data": "upload_text"}],
                    [{"text": "ارسال پیام به کاربران ✉️", "callback_data": "send_to_users"}],
                    [{"text": "ارسال عکس به کاربران 🖼️", "callback_data": "send_photo_to_users"}]
                ]
            }
            send_message(chat_id, greeting, keyboard)
            return
        
        # Handle admin states
        if user_id in admin_states:
            state = admin_states[user_id]
            
            if state["action"] == "awaiting_file":
                if "document" in message:
                    file_id = message["document"]["file_id"]
                    caption = message.get("caption", "")
                    code = generate_random_code()
                    
                    files_collection.insert_one({
                        "code": code,
                        "file_id": file_id,
                        "caption": caption,
                        "uploaded_by": user_id,
                        "uploaded_at": datetime.now()
                    })
                    
                    send_message(chat_id, f"فایل شما با موفقیت آپلود شد! 🎉\n\nلینک دسترسی:\n/start {code}")
                    del admin_states[user_id]
            
            elif state["action"] == "awaiting_text":
                if "text" in message:
                    text = message["text"]
                    code = generate_random_code()
                    
                    texts_collection.insert_one({
                        "code": code,
                        "text": text,
                        "created_by": user_id,
                        "created_at": datetime.now()
                    })
                    
                    send_message(chat_id, f"متن شما با موفقیت آپلود شد! 🎉\n\nلینک دسترسی:\n/start {code}")
                    del admin_states[user_id]
            
            elif state["action"] == "awaiting_broadcast_text":
                if "text" in message:
                    users = users_collection.find({})
                    count = 0
                    for user in users:
                        try:
                            send_message(user["chat_id"], message["text"])
                            count += 1
                        except:
                            continue
                    send_message(chat_id, f"پیام به {count} کاربر ارسال شد! ✅")
                    del admin_states[user_id]
            
            elif state["action"] == "awaiting_broadcast_photo":
                if "photo" in message:
                    photo_id = message["photo"][-1]["file_id"]  # Get highest resolution
                    caption = message.get("caption", "")
                    
                    users = users_collection.find({})
                    count = 0
                    for user in users:
                        try:
                            send_photo(user["chat_id"], photo_id, caption)
                            count += 1
                        except:
                            continue
                    send_message(chat_id, f"عکس به {count} کاربر ارسال شد! ✅")
                    del admin_states[user_id]
    
    elif "callback_query" in update:
        callback = update["callback_query"]
        data = callback["data"]
        user_id = callback["from"]["id"]
        username = callback["from"].get("username", "")
        chat_id = callback["message"]["chat"]["id"]
        message_id = callback["message"]["message_id"]
        
        # Check channel membership callback
        if data.startswith("check_membership:"):
            parts = data.split(":")
            target_chat_id = int(parts[1])
            target_message_id = int(parts[2])
            
            if is_user_member(CHANNEL_ID, user_id):
                delete_message(target_chat_id, target_message_id)
                # Resend their original command if it was a start command
                if "message" in callback and callback["message"].get("reply_to_message"):
                    original_text = callback["message"]["reply_to_message"].get("text", "")
                    if original_text.startswith("/start"):
                        process_update({"message": {
                            "chat": {"id": target_chat_id},
                            "from": callback["from"],
                            "text": original_text
                        }})
            else:
                send_message(chat_id, "شما هنوز در کانال عضو نشده اید! لطفا ابتدا در کانال عضو شوید.")
        
        # Admin panel callbacks
        elif username in WHITELIST:
            if data == "upload_file":
                admin_states[user_id] = {"action": "awaiting_file"}
                send_message(chat_id, "لطفا فایل خود را ارسال کنید... 📁")
            
            elif data == "upload_text":
                admin_states[user_id] = {"action": "awaiting_text"}
                send_message(chat_id, "لطفا متن خود را ارسال کنید... 📝")
            
            elif data == "send_to_users":
                admin_states[user_id] = {"action": "awaiting_broadcast_text"}
                send_message(chat_id, "لطفا متن پیامی که می خواهید برای کاربران ارسال کنید را بنویسید... ✉️")
            
            elif data == "send_photo_to_users":
                admin_states[user_id] = {"action": "awaiting_broadcast_photo"}
                send_message(chat_id, "لطفا عکسی که می خواهید برای کاربران ارسال کنید را بفرستید... 🖼️")
            
            # Answer callback query
            requests.post(f"{BASE_URL}/answerCallbackQuery", json={
                "callback_query_id": callback["id"]
            })

# Polling loop
offset = 0
while True:
    try:
        response = requests.get(f"{BASE_URL}/getUpdates", params={"offset": offset, "timeout": 30})
        if response.status_code == 200:
            updates = response.json().get("result", [])
            for update in updates:
                offset = update["update_id"] + 1
                process_update(update)
        time.sleep(POLLING_INTERVAL)
    except Exception as e:
        print(f"Error: {e}")
        time.sleep(5)
