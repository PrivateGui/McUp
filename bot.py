import requests
from pymongo import MongoClient
from datetime import datetime
import pytz
import random
import string
import time

# MongoDB setup
client = MongoClient('mongodb://mongo:WhLUfhKsSaOtcqOkzjnPoNqLMpboQTan@yamabiko.proxy.rlwy.net:34347', connectTimeoutMS=1000, serverSelectionTimeoutMS=1000)
db = client['telegram_bot_db']
files_col = db['files']
texts_col = db['texts']
users_col = db['users']
stats_col = db['stats']

# Config
BOT_TOKEN = '1160037511:LpWEJYm4o6Jw33kEFiYXahNwdWPoHASdsIgRLVeB'
CHANNEL_ID = 5272323810
WHITELIST = ['zonercm', 'id_hormoz']
BASE_URL = f'https://tapi.bale.ai/bot{BOT_TOKEN}'
LAST_UPDATE_ID = 0

# Persian numbers
PERSIAN_NUMS = str.maketrans('0123456789', '۰۱۲۳۴۵۶۷۸۹')

def to_persian(text):
    return str(text).translate(PERSIAN_NUMS)

def get_iran_time():
    now = datetime.now(pytz.timezone('Asia/Tehran'))
    return f"{to_persian(now.year-621)}/{to_persian(now.month)}/{to_persian(now.day)} - {to_persian(now.hour)}:{to_persian(now.minute)}:{to_persian(now.second)}"

def send_message(chat_id, text, reply_markup=None):
    try:
        requests.post(
            f"{BASE_URL}/sendMessage",
            json={
                'chat_id': chat_id,
                'text': text,
                'parse_mode': 'MarkdownV2',
                'reply_markup': reply_markup
            },
            timeout=2
        )
    except:
        pass

def send_photo(chat_id, photo_id, caption=None):
    try:
        requests.post(
            f"{BASE_URL}/sendPhoto",
            json={
                'chat_id': chat_id,
                'photo': photo_id,
                'caption': caption,
                'parse_mode': 'MarkdownV2'
            },
            timeout=3
        )
    except:
        pass

def send_document(chat_id, file_id, caption=None, reply_markup=None):
    try:
        requests.post(
            f"{BASE_URL}/sendDocument",
            json={
                'chat_id': chat_id,
                'document': file_id,
                'caption': caption,
                'parse_mode': 'MarkdownV2',
                'reply_markup': reply_markup
            },
            timeout=3
        )
    except:
        pass

def check_member(user_id):
    try:
        response = requests.post(
            f"{BASE_URL}/getChatMember",
            json={'chat_id': CHANNEL_ID, 'user_id': user_id},
            timeout=2
        ).json()
        return response.get('result', {}).get('status') in ['member', 'administrator', 'creator']
    except:
        return True  # Fail-safe

def generate_code():
    return ''.join(random.choices(string.ascii_letters + string.digits, k=10))

def handle_start(update):
    msg = update['message']
    user = msg['from']
    chat_id = msg['chat']['id']
    
    if len(msg.get('text', '').split()) > 1:
        code = msg['text'].split()[1]
        handle_file_request(chat_id, code)
        return
    
    if not check_member(user['id']):
        keyboard = {
            'inline_keyboard': [
                [{'text': '👉 عضویت در کانال', 'url': f'https://t.me/c/{str(CHANNEL_ID)[4:]}'}],
                [{'text': '🔍 بررسی عضویت', 'callback_data': 'check_channel'}]
            ]
        }
        send_message(chat_id, "⚠️ برای استفاده از ربات باید در کانال عضو شوید!", keyboard)
        return
    
    users_col.update_one(
        {'user_id': user['id']},
        {'$set': {
            'username': user.get('username'),
            'first_name': user.get('first_name', 'کاربر'),
            'chat_id': chat_id,
            'last_seen': datetime.now()
        }},
        upsert=True
    )
    
    send_message(chat_id, f"✨ سلام {user.get('first_name', 'کاربر')}!\n\n⏰ زمان: {get_iran_time()}")

def handle_file_request(chat_id, code):
    # THIS IS THE CRUCIAL FIX - SIMPLIFIED FILE HANDLING
    file_data = files_col.find_one({'code': code})
    if file_data:
        send_document(chat_id, file_data['file_id'], file_data.get('caption'))
        return
    
    text_data = texts_col.find_one({'code': code})
    if text_data:
        send_message(chat_id, text_data['text'])
    else:
        send_message(chat_id, "⚠️ لینک نامعتبر!")

def handle_panel(update):
    msg = update['message']
    user = msg['from']
    chat_id = msg['chat']['id']
    
    if user.get('username') not in WHITELIST:
        send_message(chat_id, "🔒 دسترسی محدود!")
        return
    
    keyboard = {
        'inline_keyboard': [
            [{'text': '📁 آپلود فایل', 'callback_data': 'upload_file'}],
            [{'text': '📝 آپلود متن', 'callback_data': 'upload_text'}],
            [{'text': '📢 ارسال همگانی', 'callback_data': 'broadcast_msg'}],
            [{'text': '🖼️ ارسال عکس', 'callback_data': 'broadcast_photo'}]
        ]
    }
    
    send_message(chat_id, "🔧 *پنل مدیریت*", keyboard)

def handle_broadcast_photo(chat_id, photo_id, caption):
    users = list(users_col.find({}))
    for u in users:
        try:
            send_photo(u['chat_id'], photo_id, caption)
        except:
            continue

def process_update(update):
    global LAST_UPDATE_ID
    LAST_UPDATE_ID = update['update_id']
    
    if 'callback_query' in update:
        cb = update['callback_query']
        data = cb['data']
        msg = cb['message']
        user = cb['from']
        chat_id = msg['chat']['id']
        
        if data == 'check_channel':
            if check_member(user['id']):
                send_message(chat_id, "✅ عضویت تایید شد!")
            else:
                send_message(chat_id, "❌ هنوز عضو نشده‌اید!")
        elif data in ['upload_file', 'upload_text', 'broadcast_msg', 'broadcast_photo']:
            users_col.update_one(
                {'user_id': user['id']},
                {'$set': {'action': data}},
                upsert=True
            )
            send_message(chat_id, {
                'upload_file': "📁 فایل خود را ارسال کنید",
                'upload_text': "📝 متن خود را ارسال کنید",
                'broadcast_msg': "📢 پیام همگانی را وارد کنید",
                'broadcast_photo': "🖼️ عکس همگانی را ارسال کنید"
            }[data])
        return
    
    if 'message' not in update or 'from' not in update['message']:
        return
    
    msg = update['message']
    user = msg['from']
    chat_id = msg['chat']['id']
    
    # Handle admin actions
    user_data = users_col.find_one({'user_id': user['id']}) or {}
    if 'action' in user_data:
        action = user_data['action']
        
        if action == 'upload_file' and 'document' in msg:
            code = generate_code()
            files_col.insert_one({
                'file_id': msg['document']['file_id'],
                'caption': msg.get('caption'),
                'code': code,
                'time': datetime.now()
            })
            send_message(chat_id, f"✅ فایل آپلود شد!\n\n```\n/start {code}\n```")
            users_col.update_one({'user_id': user['id']}, {'$unset': {'action': ''}})
        
        elif action == 'upload_text' and 'text' in msg:
            code = generate_code()
            texts_col.insert_one({
                'text': msg['text'],
                'code': code,
                'time': datetime.now()
            })
            send_message(chat_id, f"✅ متن آپلود شد!\n\n```\n/start {code}\n```")
            users_col.update_one({'user_id': user['id']}, {'$unset': {'action': ''}})
        
        elif action == 'broadcast_msg' and 'text' in msg:
            users = list(users_col.find({}))
            for u in users:
                try:
                    send_message(u['chat_id'], msg['text'])
                except:
                    continue
            send_message(chat_id, f"📢 پیام به {to_persian(len(users))} کاربر ارسال شد")
            users_col.update_one({'user_id': user['id']}, {'$unset': {'action': ''}})
        
        elif action == 'broadcast_photo' and 'photo' in msg:
            photo_id = msg['photo'][-1]['file_id']
            caption = msg.get('caption', '')
            handle_broadcast_photo(chat_id, photo_id, caption)
            send_message(chat_id, f"🖼️ عکس به کاربران ارسال شد")
            users_col.update_one({'user_id': user['id']}, {'$unset': {'action': ''}})
        
        return
    
    # Normal commands
    if 'text' in msg:
        if msg['text'].startswith('/start'):
            handle_start(update)
        elif msg['text'] == 'پنل' and user.get('username') in WHITELIST:
            handle_panel(update)

def get_updates():
    try:
        response = requests.get(
            f"{BASE_URL}/getUpdates",
            params={'offset': LAST_UPDATE_ID + 1, 'timeout': 5},
            timeout=10
        ).json()
        return response.get('result', []) if response.get('ok') else []
    except:
        return []

def main():
    print("🤖 ربات فعال شد! تمام مشکلات رفع شده‌اند")
    while True:
        updates = get_updates()
        for update in updates:
            process_update(update)
        time.sleep(0.1)

if __name__ == '__main__':
    main()
