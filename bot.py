import requests
from pymongo import MongoClient
from datetime import datetime
import pytz
import random
import string
import time

# MongoDB setup with optimized settings
client = MongoClient(
    'mongodb://mongo:WhLUfhKsSaOtcqOkzjnPoNqLMpboQTan@yamabiko.proxy.rlwy.net:34347',
    connectTimeoutMS=2000,
    socketTimeoutMS=2000,
    serverSelectionTimeoutMS=2000
)
db = client['telegram_bot_db']
files_collection = db['files']
texts_collection = db['texts']
users_collection = db['users']
stats_collection = db['stats']

# Bot configuration
BOT_TOKEN = '1160037511:LpWEJYm4o6Jw33kEFiYXahNwdWPoHASdsIgRLVeB'
CHANNEL_ID = 5272323810
WHITELIST = ['zonercm', 'id_hormoz']
BASE_URL = f'https://tapi.bale.ai/bot{BOT_TOKEN}'
LAST_UPDATE_ID = 0

# Persian numerals mapping
PERSIAN_NUMS = str.maketrans('0123456789', '۰۱۲۳۴۵۶۷۸۹')

def to_persian_num(text):
    return str(text).translate(PERSIAN_NUMS)

def get_persian_time():
    now = datetime.now(pytz.timezone('Asia/Tehran'))
    return f"{to_persian_num(now.year-621)}/{to_persian_num(now.month)}/{to_persian_num(now.day)} - {to_persian_num(now.hour)}:{to_persian_num(now.minute)}:{to_persian_num(now.second)}"

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

def edit_message_reply_markup(chat_id, message_id, reply_markup):
    try:
        requests.post(
            f"{BASE_URL}/editMessageReplyMarkup",
            json={
                'chat_id': chat_id,
                'message_id': message_id,
                'reply_markup': reply_markup
            },
            timeout=2
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

def check_channel_membership(user_id):
    try:
        response = requests.post(
            f"{BASE_URL}/getChatMember",
            json={'chat_id': CHANNEL_ID, 'user_id': user_id},
            timeout=2
        ).json()
        return response.get('result', {}).get('status') in ['member', 'administrator', 'creator']
    except:
        return False

def generate_random_code():
    return ''.join(random.choices(string.ascii_letters + string.digits, k=10))

def get_file_stats(code, user_id=None):
    stats = stats_collection.find_one({'code': code}) or {
        'code': code,
        'downloads': 0,
        'likes': 0,
        'liked_by': []
    }
    user_liked = str(user_id) in stats.get('liked_by', []) if user_id else False
    return stats, user_liked

def update_download_count(code):
    stats_collection.update_one(
        {'code': code},
        {'$inc': {'downloads': 1}},
        upsert=True
    )

def update_like_count(code, user_id):
    user_id = str(user_id)
    stats, liked = get_file_stats(code, user_id)
    
    if liked:
        new_likes = stats['likes'] - 1
        stats_collection.update_one(
            {'code': code},
            {
                '$inc': {'likes': -1},
                '$pull': {'liked_by': user_id}
            }
        )
    else:
        new_likes = stats['likes'] + 1
        stats_collection.update_one(
            {'code': code},
            {
                '$inc': {'likes': 1},
                '$addToSet': {'liked_by': user_id}
            },
            upsert=True
        )
    return new_likes

def create_stats_keyboard(code, likes, downloads, user_liked=False):
    like_emoji = '❤️' if user_liked else '🤍'
    return {
        'inline_keyboard': [
            [
                {'text': f'{like_emoji} {to_persian_num(likes)}', 'callback_data': f'like_{code}'},
                {'text': f'📥 {to_persian_num(downloads)}', 'callback_data': 'download_count'}
            ]
        ]
    }

def handle_start(update):
    message = update['message']
    user = message['from']
    chat_id = message['chat']['id']
    
    if len(message.get('text', '').split()) > 1:
        code = message['text'].split()[1]
        handle_file_request(chat_id, code, user['id'])
        return
    
    first_name = user.get('first_name', 'کاربر')
    persian_time = get_persian_time()
    
    users_collection.update_one(
        {'user_id': user['id']},
        {'$set': {
            'username': user.get('username'),
            'first_name': first_name,
            'chat_id': chat_id,
            'last_seen': datetime.now()
        }},
        upsert=True
    )
    
    send_message(chat_id, f"✨ سلام {first_name}!\n\n⏰ زمان: {persian_time}")

def handle_file_request(chat_id, code, user_id=None):
    file_data = files_collection.find_one({'code': code})
    if file_data:
        stats, user_liked = get_file_stats(code, user_id)
        update_download_count(code)
        keyboard = create_stats_keyboard(code, stats['likes'], stats['downloads'] + 1, user_liked)
        send_document(chat_id, file_data['file_id'], file_data.get('caption'), keyboard)
        return
    
    text_data = texts_collection.find_one({'code': code})
    if text_data:
        send_message(chat_id, text_data['text'])
    else:
        send_message(chat_id, "⚠️ لینک نامعتبر!")

def handle_panel(update):
    message = update['message']
    user = message['from']
    chat_id = message['chat']['id']
    
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

def handle_callback(update):
    callback = update['callback_query']
    data = callback['data']
    message = callback['message']
    user = callback['from']
    chat_id = message['chat']['id']
    message_id = message['message_id']
    
    if data == 'check_channel':
        if check_channel_membership(user['id']):
            delete_message(chat_id, message_id)
            send_message(chat_id, "✅ عضویت تایید شد!")
        else:
            send_message(chat_id, "❌ هنوز عضو نشده‌اید!")
    elif data.startswith('like_'):
        code = data.split('_')[1]
        new_likes = update_like_count(code, user['id'])
        stats, user_liked = get_file_stats(code, user['id'])
        keyboard = create_stats_keyboard(code, new_likes, stats['downloads'], user_liked)
        edit_message_reply_markup(chat_id, message_id, keyboard)

def process_update(update):
    global LAST_UPDATE_ID
    LAST_UPDATE_ID = update['update_id']
    
    if 'callback_query' in update:
        handle_callback(update)
        return
    
    message = update.get('message', {})
    if not message or 'from' not in message:
        return
    
    user = message['from']
    chat_id = message['chat']['id']
    
    # Check channel membership
    if not check_channel_membership(user['id']):
        keyboard = {
            'inline_keyboard': [
                [{'text': '👉 عضویت در کانال', 'url': f'https://t.me/c/{str(CHANNEL_ID)[4:]}'}],
                [{'text': '🔍 بررسی عضویت', 'callback_data': 'check_channel'}]
            ]
        }
        send_message(chat_id, "⚠️ برای استفاده از ربات باید در کانال عضو شوید!", keyboard)
        return
    
    # Check admin commands
    if 'text' in message:
        text = message['text']
        if text.startswith('/start'):
            handle_start(update)
        elif text == 'پنل' and user.get('username') in WHITELIST:
            handle_panel(update)

def get_updates():
    try:
        response = requests.get(
            f"{BASE_URL}/getUpdates",
            params={'offset': LAST_UPDATE_ID + 1, 'timeout': 10},
            timeout=15
        ).json()
        return response.get('result', []) if response.get('ok') else []
    except:
        return []

def main():
    print("🚀 Bot started with all features working!")
    while True:
        try:
            updates = get_updates()
            for update in updates:
                process_update(update)
        except Exception as e:
            print(f"⚠️ Temporary error: {e}")
            time.sleep(1)

if __name__ == '__main__':
    main()
