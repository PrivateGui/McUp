import requests
from pymongo import MongoClient
from datetime import datetime
import pytz
import random
import string
import time

# MongoDB setup
client = MongoClient('mongodb://mongo:WhLUfhKsSaOtcqOkzjnPoNqLMpboQTan@yamabiko.proxy.rlwy.net:34347')
db = client['telegram_bot_db']
files_collection = db['files']
texts_collection = db['texts']
users_collection = db['users']
admin_messages_collection = db['admin_messages']

# Bot configuration
BOT_TOKEN = '1160037511:LpWEJYm4o6Jw33kEFiYXahNwdWPoHASdsIgRLVeB'
CHANNEL_ID = 5272323810
WHITELIST = ['zonercm', 'id_hormoz']  # Whitelisted usernames
BASE_URL = f'https://tapi.bale.ai/bot{BOT_TOKEN}'
LAST_UPDATE_ID = 0

# Persian month names for Gregorian conversion
PERSIAN_MONTHS = [
    'فروردین', 'اردیبهشت', 'خرداد', 'تیر', 'مرداد', 'شهریور',
    'مهر', 'آبان', 'آذر', 'دی', 'بهمن', 'اسفند'
]

def get_persian_time():
    tz = pytz.timezone('Asia/Tehran')
    now = datetime.now(tz)
    
    # Convert to Persian year (approximation)
    persian_year = now.year - 621
    
    # Format the date string
    return f"{persian_year}/{PERSIAN_MONTHS[now.month-1]}/{now.day} {now.hour}:{now.minute:02d}"

def send_message(chat_id, text, reply_markup=None):
    payload = {
        'chat_id': chat_id,
        'text': text,
        'parse_mode': 'HTML'
    }
    if reply_markup:
        payload['reply_markup'] = reply_markup
    requests.post(f"{BASE_URL}/sendMessage", json=payload)

def delete_message(chat_id, message_id):
    requests.post(f"{BASE_URL}/deleteMessage", json={
        'chat_id': chat_id,
        'message_id': message_id
    })

def check_channel_membership(user_id):
    response = requests.post(f"{BASE_URL}/getChatMember", json={
        'chat_id': CHANNEL_ID,
        'user_id': user_id
    }).json()
    return response.get('result', {}).get('status') in ['member', 'administrator', 'creator']

def generate_random_code():
    return ''.join(random.choices(string.ascii_letters + string.digits, k=10))

def handle_start(update):
    message = update['message']
    user = message['from']
    chat_id = message['chat']['id']
    
    # Check if it's a file link request
    if len(message.get('text', '').split()) > 1:
        code = message['text'].split()[1]
        handle_file_request(chat_id, code)
        return
    
    # Normal start command
    first_name = user.get('first_name', 'کاربر')
    persian_time = get_persian_time()
    
    users_collection.update_one(
        {'user_id': user['id']},
        {'$set': {
            'username': user.get('username'),
            'first_name': first_name,
            'chat_id': chat_id
        }},
        upsert=True
    )
    
    send_message(chat_id, f"👋 سلام {first_name}!\n\n🕒 زمان ایران: {persian_time}")

def handle_file_request(chat_id, code):
    # Check files
    file_data = files_collection.find_one({'code': code})
    if file_data:
        send_document(chat_id, file_data['file_id'], file_data.get('caption'))
        return
    
    # Check texts
    text_data = texts_collection.find_one({'code': code})
    if text_data:
        send_message(chat_id, text_data['text'])
        return
    
    send_message(chat_id, "❌ لینک نامعتبر!")

def send_document(chat_id, file_id, caption=None):
    payload = {'chat_id': chat_id, 'document': file_id}
    if caption: payload['caption'] = caption
    requests.post(f"{BASE_URL}/sendDocument", json=payload)

def handle_panel(update):
    message = update['message']
    user = message['from']
    chat_id = message['chat']['id']
    
    if user.get('username') not in WHITELIST:
        send_message(chat_id, "⛔ دسترسی محدود!")
        return
    
    keyboard = {
        'inline_keyboard': [
            [{'text': '📤 آپلود فایل', 'callback_data': 'upload_file'}],
            [{'text': '📝 آپلود متن', 'callback_data': 'upload_text'}],
            [{'text': '📢 ارسال پیام همگانی', 'callback_data': 'broadcast_msg'}],
            [{'text': '🖼️ ارسال عکس همگانی', 'callback_data': 'broadcast_photo'}]
        ]
    }
    
    send_message(chat_id, "👑 پنل مدیریت", keyboard)

def handle_callback(update):
    callback = update['callback_query']
    data = callback['data']
    message = callback['message']
    user = callback['from']
    
    if data == 'check_channel':
        if check_channel_membership(user['id']):
            delete_message(message['chat']['id'], message['message_id'])
            send_message(message['chat']['id'], "✅ حالا می‌توانید از ربات استفاده کنید!")
        else:
            send_message(message['chat']['id'], "❌ هنوز در کانال عضو نشده‌اید!")
    else:
        send_message(message['chat']['id'], {
            'upload_file': "📤 فایل خود را ارسال کنید",
            'upload_text': "📝 متن خود را ارسال کنید",
            'broadcast_msg': "📢 پیام همگانی خود را بنویسید",
            'broadcast_photo': "🖼️ عکس همگانی خود را ارسال کنید"
        }[data])
        users_collection.update_one(
            {'user_id': user['id']},
            {'$set': {'admin_action': data}},
            upsert=True
        )

def handle_admin_file(update):
    message = update['message']
    user = message['from']
    file_id = message['document']['file_id']
    code = generate_random_code()
    
    files_collection.insert_one({
        'file_id': file_id,
        'caption': message.get('caption', ''),
        'code': code,
        'timestamp': datetime.now(),
        'uploaded_by': user.get('username')
    })
    
    send_message(message['chat']['id'], f"✅ فایل آپلود شد!\nلینک: /start {code}")
    users_collection.update_one({'user_id': user['id']}, {'$unset': {'admin_action': ''}})

def handle_admin_text(update):
    message = update['message']
    user = message['from']
    code = generate_random_code()
    
    texts_collection.insert_one({
        'text': message['text'],
        'code': code,
        'timestamp': datetime.now(),
        'uploaded_by': user.get('username')
    })
    
    send_message(message['chat']['id'], f"✅ متن آپلود شد!\nلینک: /start {code}")
    users_collection.update_one({'user_id': user['id']}, {'$unset': {'admin_action': ''}})

def handle_broadcast(update):
    message = update['message']
    user = message['from']
    chat_id = message['chat']['id']
    
    users = list(users_collection.find({}))
    success = 0
    
    if 'text' in message:
        for u in users:
            try:
                send_message(u['chat_id'], message['text'])
                success += 1
            except:
                continue
        send_message(chat_id, f"📢 پیام به {success}/{len(users)} کاربر ارسال شد!")
    
    elif 'photo' in message:
        photo_id = message['photo'][-1]['file_id']
        caption = message.get('caption', '')
        for u in users:
            try:
                send_photo(u['chat_id'], photo_id, caption)
                success += 1
            except:
                continue
        send_message(chat_id, f"🖼️ عکس به {success}/{len(users)} کاربر ارسال شد!")
    
    users_collection.update_one({'user_id': user['id']}, {'$unset': {'admin_action': ''}})

def send_photo(chat_id, photo_id, caption=None):
    payload = {'chat_id': chat_id, 'photo': photo_id}
    if caption: payload['caption'] = caption
    requests.post(f"{BASE_URL}/sendPhoto", json=payload)

def process_update(update):
    global LAST_UPDATE_ID
    LAST_UPDATE_ID = update['update_id']
    
    if 'callback_query' in update:
        handle_callback(update)
        return
    
    message = update.get('message', {})
    if not message: return
    
    user = message.get('from', {})
    chat_id = message['chat']['id']
    
    # Channel check
    if not check_channel_membership(user.get('id', 0)):
        keyboard = {
            'inline_keyboard': [
                [{'text': 'عضویت در کانال', 'url': f'https://t.me/c/{str(CHANNEL_ID)[4:]}'}],
                [{'text': 'بررسی عضویت', 'callback_data': 'check_channel'}]
            ]
        }
        send_message(chat_id, "⚠️ لطفا ابتدا در کانال عضو شوید!", keyboard)
        return
    
    # Check admin actions
    user_data = users_collection.find_one({'user_id': user['id']}) or {}
    if user_data.get('admin_action'):
        {
            'upload_file': handle_admin_file,
            'upload_text': handle_admin_text,
            'broadcast_msg': handle_broadcast,
            'broadcast_photo': handle_broadcast
        }[user_data['admin_action']](update)
        return
    
    # Normal commands
    if 'text' in message:
        if message['text'] == '/start' or message['text'].startswith('/start '):
            handle_start(update)
        elif message['text'] == 'پنل' and user.get('username') in WHITELIST:
            handle_panel(update)

def get_updates():
    response = requests.get(f"{BASE_URL}/getUpdates", params={
        'offset': LAST_UPDATE_ID + 1,
        'timeout': 30
    }).json()
    return response.get('result', []) if response.get('ok') else []

def main():
    print("Bot is running...")
    while True:
        try:
            updates = get_updates()
            for update in updates:
                process_update(update)
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(5)

if __name__ == '__main__':
    main()
