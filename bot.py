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
CHANNEL_ID = 5272323810 # Replace with your channel ID
WHITELIST = ['zonercm', 'id_hormoz']  # Whitelisted usernames
BASE_URL = f'https://tapi.bale.ai/bot{BOT_TOKEN}'
LAST_UPDATE_ID = 0  # For long polling

# States for admin commands
ADMIN_STATES = {}

def get_iran_time():
    tz = pytz.timezone('Asia/Tehran')
    now = datetime.now(tz)
    return now.strftime("%Y-%m-%d %H:%M:%S")

def send_message(chat_id, text, reply_markup=None, parse_mode='HTML'):
    url = f"{BASE_URL}/sendMessage"
    payload = {
        'chat_id': chat_id,
        'text': text,
        'parse_mode': parse_mode
    }
    if reply_markup:
        payload['reply_markup'] = reply_markup
    requests.post(url, json=payload)

def delete_message(chat_id, message_id):
    url = f"{BASE_URL}/deleteMessage"
    payload = {
        'chat_id': chat_id,
        'message_id': message_id
    }
    requests.post(url, json=payload)

def check_channel_membership(user_id):
    url = f"{BASE_URL}/getChatMember"
    payload = {
        'chat_id': CHANNEL_ID,
        'user_id': user_id
    }
    response = requests.post(url, json=payload).json()
    return response.get('result', {}).get('status') in ['member', 'administrator', 'creator']

def generate_random_code():
    return ''.join(random.choices(string.ascii_letters + string.digits, k=10))

def handle_start(update):
    message = update['message']
    user = message['from']
    chat_id = message['chat']['id']
    first_name = user.get('first_name', 'کاربر')
    iran_time = get_iran_time()
    
    # Save user if not exists
    users_collection.update_one(
        {'user_id': user['id']},
        {'$set': {
            'username': user.get('username'),
            'first_name': first_name,
            'chat_id': chat_id
        }},
        upsert=True
    )
    
    welcome_text = f"👋 سلام {first_name}!\n\n🕒 زمان ایران: {iran_time}"
    send_message(chat_id, welcome_text)

def handle_panel(update):
    message = update['message']
    user = message['from']
    chat_id = message['chat']['id']
    
    if user.get('username') not in WHITELIST:
        send_message(chat_id, "⛔ دسترسی محدود! شما مجاز به استفاده از این بخش نیستید.")
        return
    
    iran_time = get_iran_time()
    welcome_text = f"👑 پنل مدیریت\n\n🕒 زمان ایران: {iran_time}"
    
    keyboard = {
        'inline_keyboard': [
            [{'text': '📤 آپلود فایل', 'callback_data': 'upload_file'}],
            [{'text': '📝 آپلود متن', 'callback_data': 'upload_text'}],
            [{'text': '📢 ارسال پیام به کاربران', 'callback_data': 'send_message_to_users'}],
            [{'text': '🖼️ ارسال عکس به کاربران', 'callback_data': 'send_photo_to_users'}]
        ]
    }
    
    send_message(chat_id, welcome_text, keyboard)

def handle_callback_query(update):
    callback = update['callback_query']
    data = callback['data']
    message = callback['message']
    chat_id = message['chat']['id']
    user = callback['from']
    message_id = message['message_id']
    
    if data == 'check_channel':
        if check_channel_membership(user['id']):
            delete_message(chat_id, message_id)
            send_message(chat_id, "✅ حالا می‌توانید از ربات استفاده کنید!")
        else:
            send_message(chat_id, "❌ هنوز در کانال عضو نشده‌اید!")
    elif data in ['upload_file', 'upload_text', 'send_message_to_users', 'send_photo_to_users']:
        ADMIN_STATES[user['id']] = data
        action_text = {
            'upload_file': '📤 لطفا فایل مورد نظر را ارسال کنید.',
            'upload_text': '📝 لطفا متن مورد نظر را ارسال کنید.',
            'send_message_to_users': '📢 لطفا پیام متنی که می‌خواهید برای کاربران ارسال شود را بنویسید.',
            'send_photo_to_users': '🖼️ لطفا عکس مورد نظر را ارسال کنید (می‌توانید همراه با کپشن باشد).'
        }[data]
        send_message(chat_id, action_text)

def handle_admin_file(message):
    user = message['from']
    chat_id = message['chat']['id']
    file_id = message['document']['file_id']
    caption = message.get('caption', '')
    code = generate_random_code()
    
    files_collection.insert_one({
        'file_id': file_id,
        'caption': caption,
        'code': code,
        'timestamp': datetime.now(),
        'uploaded_by': user.get('username')
    })
    
    send_message(chat_id, f"✅ فایل با موفقیت آپلود شد!\n\nلینک دسترسی:\n/start {code}")
    ADMIN_STATES.pop(user['id'], None)

def handle_admin_text(message):
    user = message['from']
    chat_id = message['chat']['id']
    text = message['text']
    code = generate_random_code()
    
    texts_collection.insert_one({
        'text': text,
        'code': code,
        'timestamp': datetime.now(),
        'uploaded_by': user.get('username')
    })
    
    send_message(chat_id, f"✅ متن با موفقیت آپلود شد!\n\nلینک دسترسی:\n/start {code}")
    ADMIN_STATES.pop(user['id'], None)

def handle_admin_broadcast_message(message):
    user = message['from']
    chat_id = message['chat']['id']
    text = message['text']
    
    # Save the message for tracking
    message_id = admin_messages_collection.insert_one({
        'text': text,
        'timestamp': datetime.now(),
        'sent_by': user.get('username'),
        'type': 'text'
    }).inserted_id
    
    # Send to all users
    users = users_collection.find()
    success_count = 0
    total_users = users.count()
    
    for user in users:
        try:
            send_message(user['chat_id'], text)
            success_count += 1
        except:
            continue
    
    send_message(chat_id, f"📢 پیام به {success_count} از {total_users} کاربر ارسال شد!")
    ADMIN_STATES.pop(user['id'], None)

def handle_admin_broadcast_photo(message):
    user = message['from']
    chat_id = message['chat']['id']
    photo_id = message['photo'][-1]['file_id']  # Get highest resolution photo
    caption = message.get('caption', '')
    
    # Save the message for tracking
    message_id = admin_messages_collection.insert_one({
        'photo_id': photo_id,
        'caption': caption,
        'timestamp': datetime.now(),
        'sent_by': user.get('username'),
        'type': 'photo'
    }).inserted_id
    
    # Send to all users
    users = users_collection.find()
    success_count = 0
    total_users = users.count()
    
    for user in users:
        try:
            send_photo(user['chat_id'], photo_id, caption)
            success_count += 1
        except:
            continue
    
    send_message(chat_id, f"🖼️ عکس به {success_count} از {total_users} کاربر ارسال شد!")
    ADMIN_STATES.pop(user['id'], None)

def send_photo(chat_id, photo_id, caption=None):
    url = f"{BASE_URL}/sendPhoto"
    payload = {
        'chat_id': chat_id,
        'photo': photo_id
    }
    if caption:
        payload['caption'] = caption
    requests.post(url, json=payload)

def process_update(update):
    global LAST_UPDATE_ID
    
    if 'callback_query' in update:
        LAST_UPDATE_ID = update['update_id']
        handle_callback_query(update)
        return
    
    if 'message' not in update:
        return
    
    message = update['message']
    LAST_UPDATE_ID = update['update_id']
    chat_id = message['chat']['id']
    user = message.get('from')
    
    if not user:
        return
    
    # Check channel membership first
    if not check_channel_membership(user['id']):
        keyboard = {
            'inline_keyboard': [
                [{'text': 'عضویت در کانال', 'url': f'https://t.me/c/{str(CHANNEL_ID)[4:]}'}],
                [{'text': 'بررسی عضویت', 'callback_data': 'check_channel'}]
            ]
        }
        send_message(chat_id, "⚠️ لطفا ابتدا در کانال ما عضو شوید!", keyboard)
        return
    
    # Check if user is in admin state
    if user['id'] in ADMIN_STATES:
        state = ADMIN_STATES[user['id']]
        if state == 'upload_file' and 'document' in message:
            handle_admin_file(message)
        elif state == 'upload_text' and 'text' in message:
            handle_admin_text(message)
        elif state == 'send_message_to_users' and 'text' in message:
            handle_admin_broadcast_message(message)
        elif state == 'send_photo_to_users' and 'photo' in message:
            handle_admin_broadcast_photo(message)
        return
    
    # Normal commands
    if 'text' in message:
        text = message['text']
        if text == '/start' or text.startswith('/start '):
            handle_start(update)
        elif text == 'پنل' and user.get('username') in WHITELIST:
            handle_panel(update)
        elif text.startswith('/start '):
            code = text.split(' ')[1]
            # Check for file
            file_data = files_collection.find_one({'code': code})
            if file_data:
                send_document(chat_id, file_data['file_id'], file_data.get('caption'))
                return
            
            # Check for text
            text_data = texts_collection.find_one({'code': code})
            if text_data:
                send_message(chat_id, text_data['text'])
                return
            
            send_message(chat_id, "❌ لینک نامعتبر!")

def send_document(chat_id, file_id, caption=None):
    url = f"{BASE_URL}/sendDocument"
    payload = {
        'chat_id': chat_id,
        'document': file_id
    }
    if caption:
        payload['caption'] = caption
    requests.post(url, json=payload)

def get_updates():
    global LAST_UPDATE_ID
    url = f"{BASE_URL}/getUpdates"
    params = {'offset': LAST_UPDATE_ID + 1, 'timeout': 30}
    response = requests.get(url, params=params).json()
    if response.get('ok'):
        return response.get('result', [])
    return []

def main():
    print("Bot started polling...")
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
