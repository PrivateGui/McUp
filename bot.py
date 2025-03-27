import requests
from pymongo import MongoClient
from datetime import datetime
import pytz
import random
import string
import time

# MongoDB setup with optimized settings
client = MongoClient('mongodb://mongo:WhLUfhKsSaOtcqOkzjnPoNqLMpboQTan@yamabiko.proxy.rlwy.net:34347', connectTimeoutMS=500, socketTimeoutMS=500)
db = client['telegram_bot_db']
files_col = db['files']
texts_col = db['texts']
users_col = db['users']
stats_col = db['stats']

# Configuration
BOT_TOKEN = '1160037511:LpWEJYm4o6Jw33kEFiYXahNwdWPoHASdsIgRLVeB'
CHANNEL_ID = 5272323810  # MUST be negative for channels
WHITELIST = ['zonercm', 'id_hormoz']
BASE_URL = f'https://tapi.bale.ai/bot{BOT_TOKEN}'
LAST_UPDATE_ID = 0

# Persian numbers converter
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
            timeout=1
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
            timeout=1
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
            timeout=2
        )
    except:
        pass

def check_member(user_id):
    try:
        response = requests.post(
            f"{BASE_URL}/getChatMember",
            json={'chat_id': CHANNEL_ID, 'user_id': user_id},
            timeout=1
        ).json()
        status = response.get('result', {}).get('status')
        return status in ['member', 'administrator', 'creator']
    except Exception as e:
        print(f"Channel check error: {e}")
        return True  # Fail-safe to prevent blocking users

def generate_code():
    return ''.join(random.choices(string.ascii_letters + string.digits, k=10))

def get_stats(code, user_id=None):
    stats = stats_col.find_one({'code': code}) or {'downloads': 0, 'likes': 0, 'liked_by': []}
    liked = str(user_id) in stats.get('liked_by', []) if user_id else False
    return stats, liked

def update_downloads(code):
    stats_col.update_one({'code': code}, {'$inc': {'downloads': 1}}, upsert=True)

def update_likes(code, user_id):
    user_id = str(user_id)
    stats, liked = get_stats(code, user_id)
    
    if liked:
        stats_col.update_one(
            {'code': code},
            {'$inc': {'likes': -1}, '$pull': {'liked_by': user_id}}
        )
        return stats['likes'] - 1
    else:
        stats_col.update_one(
            {'code': code},
            {'$inc': {'likes': 1}, '$addToSet': {'liked_by': user_id}},
            upsert=True
        )
        return stats['likes'] + 1

def create_keyboard(code, likes, downloads, liked=False):
    return {
        'inline_keyboard': [[
            {'text': f'{"❤️" if liked else "🤍"} {to_persian(likes)}', 'callback_data': f'like_{code}'},
            {'text': f'📥 {to_persian(downloads)}', 'callback_data': 'download'}
        ]]
    }

def handle_start(update):
    msg = update['message']
    user = msg['from']
    chat_id = msg['chat']['id']
    
    # FIRST check if it's a file request
    if len(msg.get('text', '').split()) > 1:
        code = msg['text'].split()[1]
        handle_file(chat_id, code, user['id'])
        return
    
    # Only show welcome for plain /start
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

def handle_file(chat_id, code, user_id):
    # Check files
    file_data = files_col.find_one({'code': code})
    if file_data:
        stats, liked = get_stats(code, user_id)
        update_downloads(code)
        keyboard = create_keyboard(code, stats['likes'], stats['downloads']+1, liked)
        send_document(chat_id, file_data['file_id'], file_data.get('caption'), keyboard)
        return
    
    # Check texts
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

def handle_callback(update):
    cb = update['callback_query']
    data = cb['data']
    msg = cb['message']
    user = cb['from']
    chat_id = msg['chat']['id']
    msg_id = msg['message_id']
    
    if data == 'check_channel':
        if check_member(user['id']):
            requests.post(f"{BASE_URL}/deleteMessage", json={'chat_id': chat_id, 'message_id': msg_id}, timeout=1)
            send_message(chat_id, "✅ عضویت تایید شد!")
        else:
            send_message(chat_id, "❌ هنوز عضو نشده‌اید!")
    elif data.startswith('like_'):
        code = data.split('_')[1]
        new_likes = update_likes(code, user['id'])
        stats, liked = get_stats(code, user['id'])
        keyboard = create_keyboard(code, new_likes, stats['downloads'], liked)
        edit_message_reply_markup(chat_id, msg_id, keyboard)
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

def handle_admin_action(update):
    msg = update['message']
    user = msg['from']
    chat_id = msg['chat']['id']
    
    user_data = users_col.find_one({'user_id': user['id']}) or {}
    action = user_data.get('action')
    
    if not action:
        return
    
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
        send_message(chat_id, f"📢 ارسال به {to_persian(len(users))} کاربر")
        users_col.update_one({'user_id': user['id']}, {'$unset': {'action': ''}})
    
    elif action == 'broadcast_photo' and 'photo' in msg:
        users = list(users_col.find({}))
        photo_id = msg['photo'][-1]['file_id']
        caption = msg.get('caption', '')
        for u in users:
            try:
                send_document(u['chat_id'], photo_id, caption)
            except:
                continue
        send_message(chat_id, f"🖼️ ارسال به {to_persian(len(users))} کاربر")
        users_col.update_one({'user_id': user['id']}, {'$unset': {'action': ''}})

def process_update(update):
    global LAST_UPDATE_ID
    LAST_UPDATE_ID = update['update_id']
    
    if 'callback_query' in update:
        handle_callback(update)
        return
    
    if 'message' not in update or 'from' not in update['message']:
        return
    
    msg = update['message']
    user = msg['from']
    chat_id = msg['chat']['id']
    
    # Skip channel check for file requests and panel commands
    if not (len(msg.get('text', '').split()) > 1 or msg.get('text') == 'پنل'):
        if not check_member(user['id']):
            keyboard = {
                'inline_keyboard': [
                    [{'text': '👉 عضویت در کانال', 'url': f'https://t.me/c/{str(CHANNEL_ID)[4:]}'}],
                    [{'text': '🔍 بررسی عضویت', 'callback_data': 'check_channel'}]
                ]
            }
            send_message(chat_id, "⚠️ برای استفاده از ربات باید در کانال عضو شوید!", keyboard)
            return
    
    # Check admin actions first
    handle_admin_action(update)
    
    # Then normal commands
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
            timeout=6
        ).json()
        return response.get('result', []) if response.get('ok') else []
    except:
        return []

def main():
    print("🚀 ربات فعال شد! تمام مشکلات رفع شده‌اند")
    while True:
        updates = get_updates()
        for update in updates:
            process_update(update)
        time.sleep(0.1)

if __name__ == '__main__':
    main()
