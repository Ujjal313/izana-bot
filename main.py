# -*- coding: utf-8 -*-
import telebot
import subprocess
import os
import zipfile
import tempfile
import shutil
from telebot import types
import time
from datetime import datetime, timedelta
import psutil
import sqlite3
import json
import logging
import signal
import threading
import re
import sys
import atexit
import requests

# --- Flask Keep Alive ---
from flask import Flask
from threading import Thread

app = Flask('')
NAME = '•ɪ ᴢ ᴀ ɴ ᴀ ᴍ ɪ •シ︎ Hosting Bot'
@app.route('/')
def home():
    return f"I am {NAME}"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()
    print("Flask Keep-Alive server started.")

# --- Configuration ---
TOKEN = '7719108598:AAEpZuE70kAi7xHzj_MxEKm7g1HzBCAKtb8'
OWNER_ID = 8679992702
ADMIN_ID = 8679992702
YOUR_USERNAME = 'Nagato_Uzumakie'
UPDATE_CHANNEL = '@izanami_13'

# Folder setup
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_BOTS_DIR = os.path.join(BASE_DIR, 'upload_bots')
IROTECH_DIR = os.path.join(BASE_DIR, 'inf')
DATABASE_PATH = os.path.join(IROTECH_DIR, 'bot_data.db')

# File upload limits
FREE_USER_LIMIT = 6
SUBSCRIBED_USER_LIMIT = 29
ADMIN_LIMIT = 9999999
OWNER_LIMIT = float('inf')

os.makedirs(UPLOAD_BOTS_DIR, exist_ok=True)
os.makedirs(IROTECH_DIR, exist_ok=True)

bot = telebot.TeleBot(TOKEN)

# --- Data structures ---
bot_scripts = {}
user_subscriptions = {}
user_files = {}
active_users = set()
admin_ids = {ADMIN_ID, OWNER_ID}
banned_users = set()
user_limits = {}
bot_locked = False

# --- Mandatory Channels ---
mandatory_channels = {}

# --- Pending ZIP files ---
pending_zip_files = {}

# --- Security Settings ---
SECURITY_CONFIG = {
    'blocked_modules': ['os.system', 'os', 'zipfile', 'subprocess.Popen', 'subprocess', 'eval', 'exec','compile', '__import__'],
    'max_file_size': 20 * 1024 * 1024,
    'max_script_runtime': 3600,
    'allowed_extensions': ['.py', '.js'],
    'blocked_imports': ['shutil.rmtree', 'subprocess','os.remove', 'os.unlink']
}

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Command Button Layouts ---
COMMAND_BUTTONS_LAYOUT_USER_SPEC = [
    ["📢 Updates Channel"],
    ["📤 Upload File", "📂 Check Files"],
    ["⚡ Bot Speed", "📊 Statistics"],
    ["📞 Contact Owner"],
    ["📦 Manual Install", "🆘 Help"]
]

ADMIN_COMMAND_BUTTONS_LAYOUT_USER_SPEC = [
    ["📢 Updates Channel"],
    ["📤 Upload File", "📂 Check Files"],
    ["⚡ Bot Speed", "📊 Statistics"],
    ["💳 Subscriptions", "📢 Broadcast"],
    ["🔒 Lock Bot", "🟢 Running All Code"],
    ["👑 Admin Panel", "📞 Contact Owner"],
    ["📢 Channel Add", "🛠️ Manual Install"],
    ["👥 User Management", "⚙️ Settings"]
]

# --- Database Setup ---
def init_db():
    logger.info(f"Initializing database at: {DATABASE_PATH}")
    try:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS subscriptions
                     (user_id INTEGER PRIMARY KEY, expiry TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS user_files
                     (user_id INTEGER, file_name TEXT, file_type TEXT,
                      PRIMARY KEY (user_id, file_name))''')
        c.execute('''CREATE TABLE IF NOT EXISTS active_users
                     (user_id INTEGER PRIMARY KEY, join_date TEXT, last_seen TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS admins
                     (user_id INTEGER PRIMARY KEY, added_by INTEGER, added_date TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS banned_users
                     (user_id INTEGER PRIMARY KEY, reason TEXT, banned_by INTEGER, ban_date TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS user_limits
                     (user_id INTEGER PRIMARY KEY, file_limit INTEGER, set_by INTEGER, set_date TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS mandatory_channels
                     (channel_id TEXT PRIMARY KEY, 
                      channel_username TEXT,
                      channel_name TEXT,
                      added_by INTEGER,
                      added_date TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS install_logs
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      user_id INTEGER,
                      module_name TEXT,
                      package_name TEXT,
                      status TEXT,
                      log TEXT,
                      install_date TEXT)''')
        
        c.execute('INSERT OR IGNORE INTO admins (user_id, added_by, added_date) VALUES (?, ?, ?)', 
                  (OWNER_ID, OWNER_ID, datetime.now().isoformat()))
        if ADMIN_ID != OWNER_ID:
            c.execute('INSERT OR IGNORE INTO admins (user_id, added_by, added_date) VALUES (?, ?, ?)', 
                      (ADMIN_ID, OWNER_ID, datetime.now().isoformat()))
        conn.commit()
        conn.close()
        logger.info("Database initialized successfully.")
    except Exception as e:
        logger.error(f"Database initialization error: {e}")

def load_data():
    logger.info("Loading data from database...")
    try:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        c.execute('SELECT user_id, expiry FROM subscriptions')
        for user_id, expiry in c.fetchall():
            try:
                user_subscriptions[user_id] = {'expiry': datetime.fromisoformat(expiry)}
            except ValueError:
                logger.warning(f"Invalid expiry date for user {user_id}: {expiry}")
        c.execute('SELECT user_id, file_name, file_type FROM user_files')
        for user_id, file_name, file_type in c.fetchall():
            if user_id not in user_files:
                user_files[user_id] = []
            user_files[user_id].append((file_name, file_type))
        c.execute('SELECT user_id FROM active_users')
        active_users.update(user_id for (user_id,) in c.fetchall())
        c.execute('SELECT user_id FROM admins')
        admin_ids.update(user_id for (user_id,) in c.fetchall())
        c.execute('SELECT user_id FROM banned_users')
        banned_users.update(user_id for (user_id,) in c.fetchall())
        c.execute('SELECT user_id, file_limit FROM user_limits')
        for user_id, file_limit in c.fetchall():
            user_limits[user_id] = file_limit
        c.execute('SELECT channel_id, channel_username, channel_name FROM mandatory_channels')
        for channel_id, channel_username, channel_name in c.fetchall():
            mandatory_channels[channel_id] = {
                'username': channel_username,
                'name': channel_name
            }
        conn.close()
        logger.info(f"Data loaded: {len(active_users)} users, {len(user_subscriptions)} subscriptions")
    except Exception as e:
        logger.error(f"Error loading data: {e}")

# Initialize DB
init_db()
load_data()

# --- Database Lock ---
DB_LOCK = threading.Lock()

# --- Helper Functions ---
def get_user_folder(user_id):
    user_folder = os.path.join(UPLOAD_BOTS_DIR, str(user_id))
    os.makedirs(user_folder, exist_ok=True)
    return user_folder

def get_user_file_limit(user_id):
    if user_id == OWNER_ID: return OWNER_LIMIT
    if user_id in admin_ids: return ADMIN_LIMIT
    if user_id in user_limits: return user_limits[user_id]
    if user_id in user_subscriptions and user_subscriptions[user_id]['expiry'] > datetime.now():
        return SUBSCRIBED_USER_LIMIT
    return FREE_USER_LIMIT

def get_user_file_count(user_id):
    return len(user_files.get(user_id, []))

def is_bot_running(script_owner_id, file_name):
    script_key = f"{script_owner_id}_{file_name}"
    script_info = bot_scripts.get(script_key)
    if script_info and script_info.get('process'):
        try:
            proc = psutil.Process(script_info['process'].pid)
            is_running = proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE
            if not is_running:
                if 'log_file' in script_info and hasattr(script_info['log_file'], 'close') and not script_info['log_file'].closed:
                    try:
                        script_info['log_file'].close()
                    except:
                        pass
                if script_key in bot_scripts:
                    del bot_scripts[script_key]
            return is_running
        except psutil.NoSuchProcess:
            if 'log_file' in script_info and hasattr(script_info['log_file'], 'close') and not script_info['log_file'].closed:
                try:
                    script_info['log_file'].close()
                except:
                    pass
            if script_key in bot_scripts:
                del bot_scripts[script_key]
            return False
        except Exception:
            return False
    return False

def kill_process_tree(process_info):
    try:
        if 'log_file' in process_info and hasattr(process_info['log_file'], 'close') and not process_info['log_file'].closed:
            try:
                process_info['log_file'].close()
            except:
                pass
        process = process_info.get('process')
        if process and hasattr(process, 'pid'):
            pid = process.pid
            try:
                parent = psutil.Process(pid)
                children = parent.children(recursive=True)
                for child in children:
                    try:
                        child.terminate()
                    except:
                        try:
                            child.kill()
                        except:
                            pass
                gone, alive = psutil.wait_procs(children, timeout=1)
                for p in alive:
                    try:
                        p.kill()
                    except:
                        pass
                try:
                    parent.terminate()
                    try:
                        parent.wait(timeout=1)
                    except:
                        parent.kill()
                except:
                    pass
            except psutil.NoSuchProcess:
                pass
    except:
        pass

# --- Database Operations ---
def save_user_file(user_id, file_name, file_type='py'):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('INSERT OR REPLACE INTO user_files (user_id, file_name, file_type) VALUES (?, ?, ?)',
                      (user_id, file_name, file_type))
            conn.commit()
            if user_id not in user_files: user_files[user_id] = []
            user_files[user_id] = [(fn, ft) for fn, ft in user_files[user_id] if fn != file_name]
            user_files[user_id].append((file_name, file_type))
        except:
            pass
        finally:
            conn.close()

def remove_user_file_db(user_id, file_name):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('DELETE FROM user_files WHERE user_id = ? AND file_name = ?', (user_id, file_name))
            conn.commit()
            if user_id in user_files:
                user_files[user_id] = [f for f in user_files[user_id] if f[0] != file_name]
                if not user_files[user_id]:
                    del user_files[user_id]
        except:
            pass
        finally:
            conn.close()

def add_active_user(user_id):
    active_users.add(user_id)
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            join_date = datetime.now().isoformat()
            c.execute('INSERT OR REPLACE INTO active_users (user_id, join_date, last_seen) VALUES (?, ?, ?)',
                      (user_id, join_date, join_date))
            conn.commit()
        except:
            pass
        finally:
            conn.close()

def save_subscription(user_id, expiry):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            expiry_str = expiry.isoformat()
            c.execute('INSERT OR REPLACE INTO subscriptions (user_id, expiry) VALUES (?, ?)', (user_id, expiry_str))
            conn.commit()
            user_subscriptions[user_id] = {'expiry': expiry}
        except:
            pass
        finally:
            conn.close()

def remove_subscription_db(user_id):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('DELETE FROM subscriptions WHERE user_id = ?', (user_id,))
            conn.commit()
            if user_id in user_subscriptions:
                del user_subscriptions[user_id]
        except:
            pass
        finally:
            conn.close()

def add_admin_db(admin_id, added_by):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            added_date = datetime.now().isoformat()
            c.execute('INSERT OR IGNORE INTO admins (user_id, added_by, added_date) VALUES (?, ?, ?)',
                      (admin_id, added_by, added_date))
            conn.commit()
            admin_ids.add(admin_id)
        except:
            pass
        finally:
            conn.close()

def remove_admin_db(admin_id):
    if admin_id == OWNER_ID:
        return False
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('DELETE FROM admins WHERE user_id = ?', (admin_id,))
            conn.commit()
            admin_ids.discard(admin_id)
            return True
        except:
            return False
        finally:
            conn.close()

def is_user_banned(user_id):
    return user_id in banned_users

def ban_user_db(user_id, reason, banned_by):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            ban_date = datetime.now().isoformat()
            c.execute('INSERT OR REPLACE INTO banned_users (user_id, reason, banned_by, ban_date) VALUES (?, ?, ?, ?)',
                      (user_id, reason, banned_by, ban_date))
            conn.commit()
            banned_users.add(user_id)
            return True
        except:
            return False
        finally:
            conn.close()

def unban_user_db(user_id):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('DELETE FROM banned_users WHERE user_id = ?', (user_id,))
            conn.commit()
            banned_users.discard(user_id)
            return True
        except:
            return False
        finally:
            conn.close()

def set_user_limit_db(user_id, limit, set_by):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            set_date = datetime.now().isoformat()
            c.execute('INSERT OR REPLACE INTO user_limits (user_id, file_limit, set_by, set_date) VALUES (?, ?, ?, ?)',
                      (user_id, limit, set_by, set_date))
            conn.commit()
            user_limits[user_id] = limit
            return True
        except:
            return False
        finally:
            conn.close()

def remove_user_limit_db(user_id):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('DELETE FROM user_limits WHERE user_id = ?', (user_id,))
            conn.commit()
            if user_id in user_limits:
                del user_limits[user_id]
            return True
        except:
            return False
        finally:
            conn.close()

# --- Manual Module Installation ---
TELEGRAM_MODULES = {
    'telebot': 'pyTelegramBotAPI',
    'telegram': 'python-telegram-bot',
    'aiogram': 'aiogram',
    'pyrogram': 'pyrogram',
    'telethon': 'telethon',
    'bs4': 'beautifulsoup4',
    'requests': 'requests',
    'pillow': 'Pillow',
    'cv2': 'opencv-python',
    'yaml': 'PyYAML',
    'dotenv': 'python-dotenv',
    'flask': 'Flask',
    'psutil': 'psutil',
}

def attempt_install_pip(module_name, message):
    package_name = TELEGRAM_MODULES.get(module_name.lower(), module_name)
    if package_name is None:
        return False, "Core module - no installation needed"
    try:
        bot.reply_to(message, f"🔄 Installing `{package_name}`...", parse_mode='Markdown')
        command = [sys.executable, '-m', 'pip', 'install', package_name]
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode == 0:
            bot.reply_to(message, f"✅ Package `{package_name}` installed successfully.", parse_mode='Markdown')
            return True, result.stdout
        else:
            bot.reply_to(message, f"❌ Failed to install `{package_name}`.", parse_mode='Markdown')
            return False, result.stderr
    except Exception as e:
        bot.reply_to(message, f"❌ Error: {str(e)}")
        return False, str(e)

def manual_install_module_init(message):
    user_id = message.from_user.id
    if is_user_banned(user_id):
        bot.reply_to(message, "❌ You are banned.")
        return
    msg = bot.reply_to(message, "📦 Send module name to install (e.g., `requests`)\n/cancel to cancel")
    bot.register_next_step_handler(msg, process_manual_install_module)

def process_manual_install_module(message):
    if message.text.lower() == '/cancel':
        bot.reply_to(message, "❌ Cancelled.")
        return
    module_name = message.text.strip()
    attempt_install_pip(module_name, message)

# --- Script Running Functions ---
def run_script(script_path, script_owner_id, user_folder, file_name, message_obj):
    script_key = f"{script_owner_id}_{file_name}"
    logger.info(f"Running Python script: {script_path} (Key: {script_key})")
    try:
        if not os.path.exists(script_path):
            bot.reply_to(message_obj, f"❌ Script '{file_name}' not found!")
            remove_user_file_db(script_owner_id, file_name)
            return

        log_file_path = os.path.join(user_folder, f"{os.path.splitext(file_name)[0]}.log")
        log_file = open(log_file_path, 'w', encoding='utf-8', errors='ignore')
        process = subprocess.Popen(
            [sys.executable, script_path],
            cwd=user_folder,
            stdout=log_file,
            stderr=log_file,
            stdin=subprocess.PIPE,
            encoding='utf-8',
            errors='ignore'
        )
        bot_scripts[script_key] = {
            'process': process,
            'log_file': log_file,
            'file_name': file_name,
            'script_owner_id': script_owner_id,
            'start_time': datetime.now(),
            'user_folder': user_folder,
            'type': 'py',
            'script_key': script_key
        }
        bot.reply_to(message_obj, f"✅ Python script '{file_name}' started! (PID: {process.pid})")
    except Exception as e:
        logger.error(f"Error running script: {e}")
        bot.reply_to(message_obj, f"❌ Error starting script: {str(e)}")

def run_js_script(script_path, script_owner_id, user_folder, file_name, message_obj):
    script_key = f"{script_owner_id}_{file_name}"
    logger.info(f"Running JS script: {script_path} (Key: {script_key})")
    try:
        if not os.path.exists(script_path):
            bot.reply_to(message_obj, f"❌ Script '{file_name}' not found!")
            remove_user_file_db(script_owner_id, file_name)
            return

        log_file_path = os.path.join(user_folder, f"{os.path.splitext(file_name)[0]}.log")
        log_file = open(log_file_path, 'w', encoding='utf-8', errors='ignore')
        process = subprocess.Popen(
            ['node', script_path],
            cwd=user_folder,
            stdout=log_file,
            stderr=log_file,
            stdin=subprocess.PIPE,
            encoding='utf-8',
            errors='ignore'
        )
        bot_scripts[script_key] = {
            'process': process,
            'log_file': log_file,
            'file_name': file_name,
            'script_owner_id': script_owner_id,
            'start_time': datetime.now(),
            'user_folder': user_folder,
            'type': 'js',
            'script_key': script_key
        }
        bot.reply_to(message_obj, f"✅ JS script '{file_name}' started! (PID: {process.pid})")
    except Exception as e:
        logger.error(f"Error running JS script: {e}")
        bot.reply_to(message_obj, f"❌ Error starting script: {str(e)}")

# --- File Handling ---
def handle_py_file(file_path, script_owner_id, user_folder, file_name, message):
    try:
        save_user_file(script_owner_id, file_name, 'py')
        threading.Thread(target=run_script, args=(file_path, script_owner_id, user_folder, file_name, message)).start()
    except Exception as e:
        logger.error(f"Error handling py file: {e}")
        bot.reply_to(message, f"❌ Error: {str(e)}")

def handle_js_file(file_path, script_owner_id, user_folder, file_name, message):
    try:
        save_user_file(script_owner_id, file_name, 'js')
        threading.Thread(target=run_js_script, args=(file_path, script_owner_id, user_folder, file_name, message)).start()
    except Exception as e:
        logger.error(f"Error handling js file: {e}")
        bot.reply_to(message, f"❌ Error: {str(e)}")

def handle_zip_file(downloaded_file_content, file_name_zip, message):
    user_id = message.from_user.id
    user_folder = get_user_folder(user_id)
    temp_dir = None
    try:
        temp_dir = tempfile.mkdtemp(prefix=f"user_{user_id}_zip_")
        zip_path = os.path.join(temp_dir, file_name_zip)
        with open(zip_path, 'wb') as new_file:
            new_file.write(downloaded_file_content)
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(temp_dir)
        extracted_items = os.listdir(temp_dir)
        py_files = [f for f in extracted_items if f.endswith('.py')]
        js_files = [f for f in extracted_items if f.endswith('.js')]
        req_file = 'requirements.txt' if 'requirements.txt' in extracted_items else None
        if req_file:
            req_path = os.path.join(temp_dir, req_file)
            bot.reply_to(message, f"🔄 Installing Python deps from `{req_file}`...")
            try:
                command = [sys.executable, '-m', 'pip', 'install', '-r', req_path]
                subprocess.run(command, capture_output=True, text=True, check=True)
                bot.reply_to(message, f"✅ Python deps installed.")
            except:
                bot.reply_to(message, f"❌ Failed to install Python deps.")
        main_script_name = None
        file_type = None
        preferred_py = ['main.py', 'bot.py', 'app.py']
        preferred_js = ['index.js', 'main.js', 'bot.js', 'app.js']
        for p in preferred_py:
            if p in py_files:
                main_script_name = p
                file_type = 'py'
                break
        if not main_script_name:
            for p in preferred_js:
                if p in js_files:
                    main_script_name = p
                    file_type = 'js'
                    break
        if not main_script_name:
            if py_files:
                main_script_name = py_files[0]
                file_type = 'py'
            elif js_files:
                main_script_name = js_files[0]
                file_type = 'js'
        if not main_script_name:
            bot.reply_to(message, "❌ No `.py` or `.js` script found in archive!")
            return
        for item_name in os.listdir(temp_dir):
            src_path = os.path.join(temp_dir, item_name)
            dest_path = os.path.join(user_folder, item_name)
            if os.path.isdir(dest_path):
                shutil.rmtree(dest_path)
            elif os.path.exists(dest_path):
                os.remove(dest_path)
            shutil.move(src_path, dest_path)
        save_user_file(user_id, main_script_name, file_type)
        main_script_path = os.path.join(user_folder, main_script_name)
        bot.reply_to(message, f"✅ Files extracted. Starting main script: `{main_script_name}`...", parse_mode='Markdown')
        if file_type == 'py':
            threading.Thread(target=run_script, args=(main_script_path, user_id, user_folder, main_script_name, message)).start()
        elif file_type == 'js':
            threading.Thread(target=run_js_script, args=(main_script_path, user_id, user_folder, main_script_name, message)).start()
    except Exception as e:
        logger.error(f"Error processing zip file: {e}")
        bot.reply_to(message, f"❌ Error processing zip: {str(e)}")
    finally:
        if temp_dir and os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir)
            except:
                pass

# --- Keyboard Layouts ---
def create_main_menu_inline(user_id):
    markup = types.InlineKeyboardMarkup(row_width=2)
    buttons = [
        types.InlineKeyboardButton('📢 Updates Channel', url=f'https://t.me/{UPDATE_CHANNEL.replace("@", "")}'),
        types.InlineKeyboardButton('📤 Upload File', callback_data='upload'),
        types.InlineKeyboardButton('📂 Check Files', callback_data='check_files'),
        types.InlineKeyboardButton('⚡ Bot Speed', callback_data='speed'),
        types.InlineKeyboardButton('📦 Manual Install', callback_data='manual_install'),
        types.InlineKeyboardButton('📞 Contact Owner', url=f'https://t.me/{YOUR_USERNAME.replace("@", "")}')
    ]
    if user_id in admin_ids:
        admin_buttons = [
            types.InlineKeyboardButton('💳 Subscriptions', callback_data='subscription'),
            types.InlineKeyboardButton('📊 Statistics', callback_data='stats'),
            types.InlineKeyboardButton('🔒 Lock Bot' if not bot_locked else '🔓 Unlock Bot',
                                     callback_data='lock_bot' if not bot_locked else 'unlock_bot'),
            types.InlineKeyboardButton('📢 Broadcast', callback_data='broadcast'),
            types.InlineKeyboardButton('👑 Admin Panel', callback_data='admin_panel'),
            types.InlineKeyboardButton('🟢 Run All Scripts', callback_data='run_all_scripts'),
            types.InlineKeyboardButton('📢 Channel Add', callback_data='manage_mandatory_channels'),
            types.InlineKeyboardButton('👥 User Management', callback_data='user_management'),
            types.InlineKeyboardButton('🛠️ Admin Install', callback_data='admin_install'),
            types.InlineKeyboardButton('⚙️ Settings', callback_data='admin_settings')
        ]
        markup.add(buttons[0])
        markup.add(buttons[1], buttons[2])
        markup.add(buttons[3], admin_buttons[0])
        markup.add(admin_buttons[1], admin_buttons[3])
        markup.add(admin_buttons[2], admin_buttons[5])
        markup.add(admin_buttons[6], admin_buttons[8])
        markup.add(admin_buttons[7], admin_buttons[9])
        markup.add(admin_buttons[4])
        markup.add(buttons[5])
    else:
        markup.add(buttons[0])
        markup.add(buttons[1], buttons[2])
        markup.add(buttons[3], buttons[4])
        markup.add(types.InlineKeyboardButton('📊 Statistics', callback_data='stats'))
        markup.add(buttons[5])
    return markup

def create_reply_keyboard_main_menu(user_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    layout_to_use = ADMIN_COMMAND_BUTTONS_LAYOUT_USER_SPEC if user_id in admin_ids else COMMAND_BUTTONS_LAYOUT_USER_SPEC
    for row_buttons_text in layout_to_use:
        markup.add(*[types.KeyboardButton(text) for text in row_buttons_text])
    return markup

def create_control_buttons(script_owner_id, file_name, is_running=True):
    markup = types.InlineKeyboardMarkup(row_width=2)
    if is_running:
        markup.row(
            types.InlineKeyboardButton("🔴 Stop", callback_data=f'stop_{script_owner_id}_{file_name}'),
            types.InlineKeyboardButton("🔄 Restart", callback_data=f'restart_{script_owner_id}_{file_name}')
        )
        markup.row(
            types.InlineKeyboardButton("🗑️ Delete", callback_data=f'delete_{script_owner_id}_{file_name}'),
            types.InlineKeyboardButton("📜 Logs", callback_data=f'logs_{script_owner_id}_{file_name}')
        )
    else:
        markup.row(
            types.InlineKeyboardButton("🟢 Start", callback_data=f'start_{script_owner_id}_{file_name}'),
            types.InlineKeyboardButton("🗑️ Delete", callback_data=f'delete_{script_owner_id}_{file_name}')
        )
        markup.row(
            types.InlineKeyboardButton("📜 View Logs", callback_data=f'logs_{script_owner_id}_{file_name}')
        )
    markup.add(types.InlineKeyboardButton("🔙 Back to Files", callback_data='check_files'))
    return markup

def create_admin_panel():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.row(
        types.InlineKeyboardButton('➕ Add Admin', callback_data='add_admin'),
        types.InlineKeyboardButton('➖ Remove Admin', callback_data='remove_admin')
    )
    markup.row(types.InlineKeyboardButton('📋 List Admins', callback_data='list_admins'))
    markup.row(types.InlineKeyboardButton('🔙 Back to Main', callback_data='back_to_main'))
    return markup

def create_user_management_menu():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.row(
        types.InlineKeyboardButton('🚫 Ban User', callback_data='ban_user'),
        types.InlineKeyboardButton('✅ Unban User', callback_data='unban_user')
    )
    markup.row(
        types.InlineKeyboardButton('📊 User Info', callback_data='user_info'),
        types.InlineKeyboardButton('👥 All Users', callback_data='all_users')
    )
    markup.row(
        types.InlineKeyboardButton('🔧 Set User Limit', callback_data='set_user_limit'),
        types.InlineKeyboardButton('🗑️ Remove User Limit', callback_data='remove_user_limit')
    )
    markup.row(types.InlineKeyboardButton('🔙 Back to Main', callback_data='back_to_main'))
    return markup

def create_subscription_menu():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.row(
        types.InlineKeyboardButton('➕ Add Subscription', callback_data='add_subscription'),
        types.InlineKeyboardButton('➖ Remove Subscription', callback_data='remove_subscription')
    )
    markup.row(types.InlineKeyboardButton('🔍 Check Subscription', callback_data='check_subscription'))
    markup.row(types.InlineKeyboardButton('🔙 Back to Main', callback_data='back_to_main'))
    return markup

def create_admin_settings_menu():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.row(
        types.InlineKeyboardButton('📊 System Info', callback_data='system_info'),
        types.InlineKeyboardButton('📈 Bot Performance', callback_data='bot_performance')
    )
    markup.row(
        types.InlineKeyboardButton('🧹 Cleanup Files', callback_data='cleanup_files'),
        types.InlineKeyboardButton('📋 Installation Logs', callback_data='install_logs')
    )
    markup.row(types.InlineKeyboardButton('🔙 Back to Main', callback_data='back_to_main'))
    return markup

def create_mandatory_channels_menu():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.row(
        types.InlineKeyboardButton('➕ Add Channel', callback_data='add_mandatory_channel'),
        types.InlineKeyboardButton('➖ Remove Channel', callback_data='remove_mandatory_channel')
    )
    markup.row(types.InlineKeyboardButton('📋 List Channels', callback_data='list_mandatory_channels'))
    markup.row(types.InlineKeyboardButton('🔙 Back to Main', callback_data='back_to_main'))
    return markup

# --- Logic Functions ---
def _logic_send_welcome(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    user_name = message.from_user.first_name
    if is_user_banned(user_id):
        bot.send_message(chat_id, "❌ You are banned.")
        return
    if bot_locked and user_id not in admin_ids:
        bot.send_message(chat_id, "⚠️ Bot locked by admin.")
        return
    if user_id not in active_users:
        add_active_user(user_id)
        try:
            bot.send_message(OWNER_ID, f"🎉 New user!\n👤 Name: {user_name}\n🆔 ID: `{user_id}`", parse_mode='Markdown')
        except:
            pass
    file_limit = get_user_file_limit(user_id)
    current_files = get_user_file_count(user_id)
    limit_str = str(file_limit) if file_limit != float('inf') else "Unlimited"
    if user_id == OWNER_ID:
        user_status = "👑 Owner"
    elif user_id in admin_ids:
        user_status = "🛡️ Admin"
    elif user_id in user_subscriptions and user_subscriptions[user_id].get('expiry', datetime.min) > datetime.now():
        user_status = "⭐ Premium"
    else:
        user_status = "🆓 Free User"
    welcome_msg = (f"〽️ Welcome, {user_name}!\n\n🆔 ID: `{user_id}`\n"
                   f"🔰 Status: {user_status}\n"
                   f"📁 Files: {current_files} / {limit_str}\n\n"
                   f"🤖 Host & run Python (`.py`) or JS (`.js`) scripts.\n"
                   f"📦 Manual module installation available\n\n👇 Use buttons.")
    main_reply_markup = create_reply_keyboard_main_menu(user_id)
    try:
        bot.send_message(chat_id, welcome_msg, reply_markup=main_reply_markup, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Error sending welcome: {e}")

def _logic_updates_channel(message):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton('📢 Updates Channel', url=f'https://t.me/{UPDATE_CHANNEL.replace("@", "")}'))
    bot.reply_to(message, "Visit our Updates Channel:", reply_markup=markup)

def _logic_upload_file(message):
    user_id = message.from_user.id
    if is_user_banned(user_id):
        bot.reply_to(message, "❌ You are banned.")
        return
    if bot_locked and user_id not in admin_ids:
        bot.reply_to(message, "⚠️ Bot locked.")
        return
    file_limit = get_user_file_limit(user_id)
    current_files = get_user_file_count(user_id)
    if current_files >= file_limit:
        limit_str = str(file_limit) if file_limit != float('inf') else "Unlimited"
        bot.reply_to(message, f"⚠️ File limit ({current_files}/{limit_str}) reached.")
        return
    bot.reply_to(message, "📤 Send your Python (`.py`), JS (`.js`), or ZIP (`.zip`) file.")

def _logic_check_files(message):
    user_id = message.from_user.id
    if is_user_banned(user_id):
        bot.reply_to(message, "❌ You are banned.")
        return
    user_files_list = user_files.get(user_id, [])
    if not user_files_list:
        bot.reply_to(message, "📂 No files uploaded yet.")
        return
    markup = types.InlineKeyboardMarkup(row_width=1)
    for file_name, file_type in sorted(user_files_list):
        is_running = is_bot_running(user_id, file_name)
        status_icon = "🟢 Running" if is_running else "🔴 Stopped"
        btn_text = f"{file_name} ({file_type}) - {status_icon}"
        markup.add(types.InlineKeyboardButton(btn_text, callback_data=f'file_{user_id}_{file_name}'))
    bot.reply_to(message, "📂 Your files:\nClick to manage.", reply_markup=markup)

def _logic_bot_speed(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    if is_user_banned(user_id):
        bot.reply_to(message, "❌ You are banned.")
        return
    start_time = time.time()
    wait_msg = bot.reply_to(message, "🏃 Testing speed...")
    try:
        bot.send_chat_action(chat_id, 'typing')
        response_time = round((time.time() - start_time) * 1000, 2)
        status = "🔓 Unlocked" if not bot_locked else "🔒 Locked"
        if user_id == OWNER_ID:
            user_level = "👑 Owner"
        elif user_id in admin_ids:
            user_level = "🛡️ Admin"
        elif user_id in user_subscriptions and user_subscriptions[user_id].get('expiry', datetime.min) > datetime.now():
            user_level = "⭐ Premium"
        else:
            user_level = "🆓 Free User"
        speed_msg = (f"⚡ Bot Speed & Status:\n\n⏱️ API Response Time: {response_time} ms\n"
                     f"🚦 Bot Status: {status}\n"
                     f"👤 Your Level: {user_level}")
        bot.edit_message_text(speed_msg, chat_id, wait_msg.message_id)
    except:
        pass

def _logic_contact_owner(message):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton('📞 Contact Owner', url=f'https://t.me/{YOUR_USERNAME.replace("@", "")}'))
    bot.reply_to(message, "Click to contact Owner:", reply_markup=markup)

def _logic_manual_install(message):
    manual_install_module_init(message)

def _logic_help(message):
    help_text = """
🤖 **Hosting Bot Help**

**📌 Basic:**
• /start - Start the bot
• /help - Show help

**📁 File Management:**
• Upload `.py`, `.js`, `.zip`
• Auto-installs deps from `requirements.txt`

**👑 Admin Features:**
• User management (ban/unban)
• Set custom file limits
• Broadcast messages
• Run all user scripts

**Support:** @Nagato_Uzumakie
**Updates:** @izanami_13
"""
    bot.reply_to(message, help_text, parse_mode='Markdown')

# --- Admin Logic ---
def _logic_statistics(message):
    user_id = message.from_user.id
    if is_user_banned(user_id):
        bot.reply_to(message, "❌ You are banned.")
        return
    total_users = len(active_users)
    total_files = sum(len(files) for files in user_files.values())
    running_bots = len(bot_scripts)
    stats_msg = (f"📊 Bot Statistics:\n\n"
                 f"👥 Total Users: {total_users}\n"
                 f"🚫 Banned Users: {len(banned_users)}\n"
                 f"📂 Total Files: {total_files}\n"
                 f"🟢 Running Bots: {running_bots}\n"
                 f"🔒 Bot Status: {'🔴 Locked' if bot_locked else '🟢 Unlocked'}")
    bot.reply_to(message, stats_msg)

def _logic_toggle_lock_bot(message):
    if message.from_user.id not in admin_ids:
        bot.reply_to(message, "⚠️ Admin required.")
        return
    global bot_locked
    bot_locked = not bot_locked
    status = "locked" if bot_locked else "unlocked"
    bot.reply_to(message, f"🔒 Bot has been {status}.")

def _logic_run_all_scripts(message):
    if message.from_user.id not in admin_ids:
        bot.reply_to(message, "⚠️ Admin required.")
        return
    bot.reply_to(message, "⏳ Starting all user scripts...")
    started = 0
    for target_user_id, files_for_user in user_files.items():
        if not files_for_user:
            continue
        user_folder = get_user_folder(target_user_id)
        for file_name, file_type in files_for_user:
            if not is_bot_running(target_user_id, file_name):
                file_path = os.path.join(user_folder, file_name)
                if os.path.exists(file_path):
                    try:
                        if file_type == 'py':
                            threading.Thread(target=run_script, args=(file_path, target_user_id, user_folder, file_name, message)).start()
                            started += 1
                        elif file_type == 'js':
                            threading.Thread(target=run_js_script, args=(file_path, target_user_id, user_folder, file_name, message)).start()
                            started += 1
                    except:
                        pass
    bot.reply_to(message, f"✅ Started {started} scripts.")

# --- Command Handlers ---
@bot.message_handler(commands=['start', 'help'])
def command_send_welcome(message):
    if message.text == '/help':
        _logic_help(message)
    else:
        _logic_send_welcome(message)

@bot.message_handler(commands=['status'])
def command_show_status(message):
    _logic_statistics(message)

BUTTON_TEXT_TO_LOGIC = {
    "📢 Updates Channel": _logic_updates_channel,
    "📤 Upload File": _logic_upload_file,
    "📂 Check Files": _logic_check_files,
    "⚡ Bot Speed": _logic_bot_speed,
    "📞 Contact Owner": _logic_contact_owner,
    "📊 Statistics": _logic_statistics,
    "🔒 Lock Bot": _logic_toggle_lock_bot,
    "🟢 Running All Code": _logic_run_all_scripts,
    "📦 Manual Install": _logic_manual_install,
    "🆘 Help": _logic_help
}

@bot.message_handler(func=lambda message: message.text in BUTTON_TEXT_TO_LOGIC)
def handle_button_text(message):
    logic_func = BUTTON_TEXT_TO_LOGIC.get(message.text)
    if logic_func:
        logic_func(message)

# --- Document Handler ---
@bot.message_handler(content_types=['document'])
def handle_file_upload_doc(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    if is_user_banned(user_id):
        bot.reply_to(message, "❌ You are banned.")
        return
    if bot_locked and user_id not in admin_ids:
        bot.reply_to(message, "⚠️ Bot locked.")
        return
    doc = message.document
    file_name = doc.file_name
    if not file_name:
        bot.reply_to(message, "⚠️ No file name.")
        return
    file_ext = os.path.splitext(file_name)[1].lower()
    if file_ext not in ['.py', '.js', '.zip']:
        bot.reply_to(message, "⚠️ Only `.py`, `.js`, `.zip` allowed.")
        return
    max_file_size = 20 * 1024 * 1024
    if doc.file_size > max_file_size:
        bot.reply_to(message, f"⚠️ File too large (Max: 20 MB).")
        return
    try:
        file_info = bot.get_file(doc.file_id)
        downloaded_file_content = bot.download_file(file_info.file_path)
        user_folder = get_user_folder(user_id)
        if file_ext == '.zip':
            handle_zip_file(downloaded_file_content, file_name, message)
        else:
            file_path = os.path.join(user_folder, file_name)
            with open(file_path, 'wb') as f:
                f.write(downloaded_file_content)
            if file_ext == '.js':
                handle_js_file(file_path, user_id, user_folder, file_name, message)
            elif file_ext == '.py':
                handle_py_file(file_path, user_id, user_folder, file_name, message)
    except Exception as e:
        logger.error(f"Error handling file: {e}")
        bot.reply_to(message, f"❌ Error: {str(e)}")

# --- Callback Handlers ---
@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    user_id = call.from_user.id
    data = call.data
    logger.info(f"Callback: User={user_id}, Data='{data}'")
    if is_user_banned(user_id) and data not in ['back_to_main']:
        bot.answer_callback_query(call.id, "❌ You are banned.", show_alert=True)
        return
    try:
        if data == 'upload':
            file_limit = get_user_file_limit(user_id)
            current_files = get_user_file_count(user_id)
            if current_files >= file_limit:
                limit_str = str(file_limit) if file_limit != float('inf') else "Unlimited"
                bot.answer_callback_query(call.id, f"⚠️ Limit ({current_files}/{limit_str}) reached.", show_alert=True)
                return
            bot.answer_callback_query(call.id)
            bot.send_message(call.message.chat.id, "📤 Send your Python (`.py`), JS (`.js`), or ZIP (`.zip`) file.")
        elif data == 'check_files':
            bot.answer_callback_query(call.id)
            _logic_check_files(call.message)
        elif data.startswith('file_'):
            _, script_owner_id_str, file_name = data.split('_', 2)
            script_owner_id = int(script_owner_id_str)
            if user_id != script_owner_id and user_id not in admin_ids:
                bot.answer_callback_query(call.id, "⚠️ Only your own files.", show_alert=True)
                return
            is_running = is_bot_running(script_owner_id, file_name)
            file_type = next((f[1] for f in user_files.get(script_owner_id, []) if f[0] == file_name), '?')
            try:
                bot.edit_message_text(
                    f"⚙️ Controls for: `{file_name}` ({file_type})\nStatus: {'🟢 Running' if is_running else '🔴 Stopped'}",
                    call.message.chat.id, call.message.message_id,
                    reply_markup=create_control_buttons(script_owner_id, file_name, is_running),
                    parse_mode='Markdown'
                )
            except:
                pass
        elif data.startswith('start_'):
            _, script_owner_id_str, file_name = data.split('_', 2)
            script_owner_id = int(script_owner_id_str)
            if user_id != script_owner_id and user_id not in admin_ids:
                bot.answer_callback_query(call.id, "⚠️ Permission denied.", show_alert=True)
                return
            user_folder = get_user_folder(script_owner_id)
            file_path = os.path.join(user_folder, file_name)
            if not os.path.exists(file_path):
                bot.answer_callback_query(call.id, "⚠️ File missing!", show_alert=True)
                return
            if is_bot_running(script_owner_id, file_name):
                bot.answer_callback_query(call.id, "⚠️ Already running.", show_alert=True)
                return
            bot.answer_callback_query(call.id, f"⏳ Starting {file_name}...")
            file_type = next((f[1] for f in user_files.get(script_owner_id, []) if f[0] == file_name), 'py')
            if file_type == 'py':
                threading.Thread(target=run_script, args=(file_path, script_owner_id, user_folder, file_name, call.message)).start()
            elif file_type == 'js':
                threading.Thread(target=run_js_script, args=(file_path, script_owner_id, user_folder, file_name, call.message)).start()
        elif data.startswith('stop_'):
            _, script_owner_id_str, file_name = data.split('_', 2)
            script_owner_id = int(script_owner_id_str)
            if user_id != script_owner_id and user_id not in admin_ids:
                bot.answer_callback_query(call.id, "⚠️ Permission denied.", show_alert=True)
                return
            script_key = f"{script_owner_id}_{file_name}"
            if script_key in bot_scripts:
                kill_process_tree(bot_scripts[script_key])
                del bot_scripts[script_key]
                bot.answer_callback_query(call.id, f"✅ Stopped {file_name}.")
            else:
                bot.answer_callback_query(call.id, "⚠️ Not running.", show_alert=True)
        elif data.startswith('restart_'):
            _, script_owner_id_str, file_name = data.split('_', 2)
            script_owner_id = int(script_owner_id_str)
            if user_id != script_owner_id and user_id not in admin_ids:
                bot.answer_callback_query(call.id, "⚠️ Permission denied.", show_alert=True)
                return
            script_key = f"{script_owner_id}_{file_name}"
            if script_key in bot_scripts:
                kill_process_tree(bot_scripts[script_key])
                del bot_scripts[script_key]
            user_folder = get_user_folder(script_owner_id)
            file_path = os.path.join(user_folder, file_name)
            if not os.path.exists(file_path):
                bot.answer_callback_query(call.id, "⚠️ File missing!", show_alert=True)
                return
            bot.answer_callback_query(call.id, f"🔄 Restarting {file_name}...")
            file_type = next((f[1] for f in user_files.get(script_owner_id, []) if f[0] == file_name), 'py')
            if file_type == 'py':
                threading.Thread(target=run_script, args=(file_path, script_owner_id, user_folder, file_name, call.message)).start()
            elif file_type == 'js':
                threading.Thread(target=run_js_script, args=(file_path, script_owner_id, user_folder, file_name, call.message)).start()
        elif data.startswith('delete_'):
            _, script_owner_id_str, file_name = data.split('_', 2)
            script_owner_id = int(script_owner_id_str)
            if user_id != script_owner_id and user_id not in admin_ids:
                bot.answer_callback_query(call.id, "⚠️ Permission denied.", show_alert=True)
                return
            script_key = f"{script_owner_id}_{file_name}"
            if script_key in bot_scripts:
                kill_process_tree(bot_scripts[script_key])
                del bot_scripts[script_key]
            user_folder = get_user_folder(script_owner_id)
            file_path = os.path.join(user_folder, file_name)
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except:
                    pass
            remove_user_file_db(script_owner_id, file_name)
            bot.answer_callback_query(call.id, f"🗑️ Deleted {file_name}.")
            _logic_check_files(call.message)
        elif data.startswith('logs_'):
            _, script_owner_id_str, file_name = data.split('_', 2)
            script_owner_id = int(script_owner_id_str)
            if user_id != script_owner_id and user_id not in admin_ids:
                bot.answer_callback_query(call.id, "⚠️ Permission denied.", show_alert=True)
                return
            user_folder = get_user_folder(script_owner_id)
            log_path = os.path.join(user_folder, f"{os.path.splitext(file_name)[0]}.log")
            if not os.path.exists(log_path):
                bot.answer_callback_query(call.id, "⚠️ No logs.", show_alert=True)
                return
            try:
                with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
                    log_content = f.read()[-4000:]
                bot.send_message(call.message.chat.id, f"📜 Logs for `{file_name}`:\n```\n{log_content}\n```", parse_mode='Markdown')
                bot.answer_callback_query(call.id)
            except:
                bot.answer_callback_query(call.id, "❌ Error reading logs.", show_alert=True)
        elif data == 'speed':
            _logic_bot_speed(call.message)
        elif data == 'back_to_main':
            _logic_send_welcome(call.message)
        elif data == 'manual_install':
            manual_install_module_init(call.message)
        elif data == 'stats':
            _logic_statistics(call.message)
        elif data == 'lock_bot':
            global bot_locked
            bot_locked = True
            bot.answer_callback_query(call.id, "🔒 Bot locked.")
        elif data == 'unlock_bot':
            global bot_locked
            bot_locked = False
            bot.answer_callback_query(call.id, "🔓 Bot unlocked.")
        elif data == 'run_all_scripts':
            _logic_run_all_scripts(call.message)
        elif data == 'admin_panel':
            if user_id not in admin_ids:
                bot.answer_callback_query(call.id, "⚠️ Admin required.", show_alert=True)
                return
            bot.answer_callback_query(call.id)
            bot.edit_message_text("👑 Admin Panel", call.message.chat.id, call.message.message_id, reply_markup=create_admin_panel())
        elif data == 'subscription':
            if user_id not in admin_ids:
                bot.answer_callback_query(call.id, "⚠️ Admin required.", show_alert=True)
                return
            bot.answer_callback_query(call.id)
            bot.edit_message_text("💳 Subscription Management", call.message.chat.id, call.message.message_id, reply_markup=create_subscription_menu())
        elif data == 'user_management':
            if user_id not in admin_ids:
                bot.answer_callback_query(call.id, "⚠️ Admin required.", show_alert=True)
                return
            bot.answer_callback_query(call.id)
            bot.edit_message_text("👥 User Management", call.message.chat.id, call.message.message_id, reply_markup=create_user_management_menu())
        elif data == 'admin_settings':
            if user_id not in admin_ids:
                bot.answer_callback_query(call.id, "⚠️ Admin required.", show_alert=True)
                return
            bot.answer_callback_query(call.id)
            bot.edit_message_text("⚙️ Admin Settings", call.message.chat.id, call.message.message_id, reply_markup=create_admin_settings_menu())
        elif data == 'broadcast':
            if user_id not in admin_ids:
                bot.answer_callback_query(call.id, "⚠️ Admin required.", show_alert=True)
                return
            bot.answer_callback_query(call.id)
            msg = bot.send_message(call.message.chat.id, "📢 Send broadcast message.\n/cancel to abort.")
            bot.register_next_step_handler(msg, process_broadcast_message)
        elif data == 'add_admin':
            if user_id != OWNER_ID:
                bot.answer_callback_query(call.id, "⚠️ Owner only.", show_alert=True)
                return
            bot.answer_callback_query(call.id)
            msg = bot.send_message(call.message.chat.id, "👑 Enter User ID to add as Admin.\n/cancel to abort.")
            bot.register_next_step_handler(msg, process_add_admin_id)
        elif data == 'remove_admin':
            if user_id != OWNER_ID:
                bot.answer_callback_query(call.id, "⚠️ Owner only.", show_alert=True)
                return
            bot.answer_callback_query(call.id)
            msg = bot.send_message(call.message.chat.id, "👑 Enter Admin ID to remove.\n/cancel to abort.")
            bot.register_next_step_handler(msg, process_remove_admin_id)
        elif data == 'list_admins':
            if user_id not in admin_ids:
                bot.answer_callback_query(call.id, "⚠️ Admin required.", show_alert=True)
                return
            bot.answer_callback_query(call.id)
            admin_list = "\n".join(f"- `{aid}` {'(Owner)' if aid == OWNER_ID else ''}" for aid in sorted(list(admin_ids)))
            bot.edit_message_text(f"👑 Admins:\n\n{admin_list}", call.message.chat.id, call.message.message_id, parse_mode='Markdown')
        elif data == 'add_subscription':
            if user_id not in admin_ids:
                bot.answer_callback_query(call.id, "⚠️ Admin required.", show_alert=True)
                return
            bot.answer_callback_query(call.id)
            msg = bot.send_message(call.message.chat.id, "💳 Enter User ID & days (e.g., `12345678 30`).\n/cancel to abort.")
            bot.register_next_step_handler(msg, process_add_subscription_details)
        elif data == 'remove_subscription':
            if user_id not in admin_ids:
                bot.answer_callback_query(call.id, "⚠️ Admin required.", show_alert=True)
                return
            bot.answer_callback_query(call.id)
            msg = bot.send_message(call.message.chat.id, "💳 Enter User ID to remove sub.\n/cancel to abort.")
            bot.register_next_step_handler(msg, process_remove_subscription_id)
        elif data == 'check_subscription':
            if user_id not in admin_ids:
                bot.answer_callback_query(call.id, "⚠️ Admin required.", show_alert=True)
                return
            bot.answer_callback_query(call.id)
            msg = bot.send_message(call.message.chat.id, "💳 Enter User ID to check sub.\n/cancel to abort.")
            bot.register_next_step_handler(msg, process_check_subscription_id)
        elif data == 'ban_user':
            if user_id not in admin_ids:
                bot.answer_callback_query(call.id, "⚠️ Admin required.", show_alert=True)
                return
            bot.answer_callback_query(call.id)
            msg = bot.send_message(call.message.chat.id, "🚫 Enter User ID to ban.\n/cancel to abort.")
            bot.register_next_step_handler(msg, process_ban_user)
        elif data == 'unban_user':
            if user_id not in admin_ids:
                bot.answer_callback_query(call.id, "⚠️ Admin required.", show_alert=True)
                return
            bot.answer_callback_query(call.id)
            msg = bot.send_message(call.message.chat.id, "✅ Enter User ID to unban.\n/cancel to abort.")
            bot.register_next_step_handler(msg, process_unban_user)
        elif data == 'user_info':
            if user_id not in admin_ids:
                bot.answer_callback_query(call.id, "⚠️ Admin required.", show_alert=True)
                return
            bot.answer_callback_query(call.id)
            msg = bot.send_message(call.message.chat.id, "👤 Enter User ID to get info.\n/cancel to abort.")
            bot.register_next_step_handler(msg, process_user_info)
        elif data == 'all_users':
            if user_id not in admin_ids:
                bot.answer_callback_query(call.id, "⚠️ Admin required.", show_alert=True)
                return
            bot.answer_callback_query(call.id)
            users_list = list(active_users)
            if not users_list:
                bot.edit_message_text("👥 No active users.", call.message.chat.id, call.message.message_id)
                return
            user_text = "👥 Active Users:\n\n"
            for i, uid in enumerate(users_list[:20], 1):
                status = "👑" if uid == OWNER_ID else "🛡️" if uid in admin_ids else "⭐" if uid in user_subscriptions else "🆓"
                user_text += f"{i}. `{uid}` {status}\n"
            if len(users_list) > 20:
                user_text += f"\n... and {len(users_list)-20} more"
            bot.edit_message_text(user_text, call.message.chat.id, call.message.message_id, parse_mode='Markdown')
        elif data == 'set_user_limit':
            if user_id not in admin_ids:
                bot.answer_callback_query(call.id, "⚠️ Admin required.", show_alert=True)
                return
            bot.answer_callback_query(call.id)
            msg = bot.send_message(call.message.chat.id, "🔧 Enter User ID and limit (e.g., `12345678 50`).\n/cancel to abort.")
            bot.register_next_step_handler(msg, process_set_user_limit)
        elif data == 'remove_user_limit':
            if user_id not in admin_ids:
                bot.answer_callback_query(call.id, "⚠️ Admin required.", show_alert=True)
                return
            bot.answer_callback_query(call.id)
            msg = bot.send_message(call.message.chat.id, "🗑️ Enter User ID to remove limit.\n/cancel to abort.")
            bot.register_next_step_handler(msg, process_remove_user_limit)
        elif data == 'system_info':
            if user_id not in admin_ids:
                bot.answer_callback_query(call.id, "⚠️ Admin required.", show_alert=True)
                return
            bot.answer_callback_query(call.id)
            import platform
            info = f"🤖 System Info:\n\nPython: {platform.python_version()}\nPlatform: {platform.platform()}\nUsers: {len(active_users)}\nRunning: {len(bot_scripts)}\nLocked: {'Yes' if bot_locked else 'No'}"
            bot.edit_message_text(info, call.message.chat.id, call.message.message_id)
        elif data == 'bot_performance':
            if user_id not in admin_ids:
                bot.answer_callback_query(call.id, "⚠️ Admin required.", show_alert=True)
                return
            bot.answer_callback_query(call.id)
            try:
                bot_process = psutil.Process()
                mem = bot_process.memory_info().rss / 1024 / 1024
                cpu = bot_process.cpu_percent(interval=0.5)
                perf = f"📈 Performance:\n\nMemory: {mem:.1f} MB\nCPU: {cpu:.1f}%\nRunning Scripts: {len(bot_scripts)}\nTotal Files: {sum(len(f) for f in user_files.values())}"
                bot.edit_message_text(perf, call.message.chat.id, call.message.message_id)
            except:
                bot.edit_message_text("⚠️ Performance info unavailable.", call.message.chat.id, call.message.message_id)
        elif data == 'cleanup_files':
            if user_id not in admin_ids:
                bot.answer_callback_query(call.id, "⚠️ Admin required.", show_alert=True)
                return
            bot.answer_callback_query(call.id, "🧹 Cleaning...")
            cleaned = 0
            for user_dir in os.listdir(UPLOAD_BOTS_DIR):
                user_path = os.path.join(UPLOAD_BOTS_DIR, user_dir)
                if os.path.isdir(user_path) and not os.listdir(user_path):
                    try:
                        os.rmdir(user_path)
                        cleaned += 1
                    except:
                        pass
            bot.edit_message_text(f"🧹 Cleaned {cleaned} empty directories.", call.message.chat.id, call.message.message_id)
        elif data == 'install_logs':
            if user_id not in admin_ids:
                bot.answer_callback_query(call.id, "⚠️ Admin required.", show_alert=True)
                return
            bot.answer_callback_query(call.id)
            bot.edit_message_text("📋 Installation logs feature available in DB.", call.message.chat.id, call.message.message_id)
        elif data == 'admin_install':
            if user_id not in admin_ids:
                bot.answer_callback_query(call.id, "⚠️ Admin required.", show_alert=True)
                return
            bot.answer_callback_query(call.id)
            msg = bot.send_message(call.message.chat.id, "🛠️ Enter user ID and module name (e.g., `12345678 requests`)\n/cancel to abort.")
            bot.register_next_step_handler(msg, process_admin_install)
        elif data == 'manage_mandatory_channels':
            if user_id not in admin_ids:
                bot.answer_callback_query(call.id, "⚠️ Admin required.", show_alert=True)
                return
            bot.answer_callback_query(call.id)
            bot.edit_message_text("📢 Mandatory Channels Management", call.message.chat.id, call.message.message_id, reply_markup=create_mandatory_channels_menu())
        elif data == 'add_mandatory_channel':
            if user_id not in admin_ids:
                bot.answer_callback_query(call.id, "⚠️ Admin required.", show_alert=True)
                return
            bot.answer_callback_query(call.id)
            msg = bot.send_message(call.message.chat.id, "📢 Send channel username or ID (e.g., @channel or -1001234567890)\n/cancel to abort.")
            bot.register_next_step_handler(msg, process_add_channel)
        elif data == 'remove_mandatory_channel':
            if user_id not in admin_ids:
                bot.answer_callback_query(call.id, "⚠️ Admin required.", show_alert=True)
                return
            if not mandatory_channels:
                bot.answer_callback_query(call.id, "❌ No mandatory channels.", show_alert=True)
                return
            bot.answer_callback_query(call.id)
            markup = types.InlineKeyboardMarkup()
            for channel_id, channel_info in mandatory_channels.items():
                markup.add(types.InlineKeyboardButton(f"🗑️ {channel_info.get('name', 'Unknown')}", callback_data=f'remove_channel_{channel_id}'))
            markup.add(types.InlineKeyboardButton("🔙 Back", callback_data='manage_mandatory_channels'))
            bot.edit_message_text("📢 Select channel to remove:", call.message.chat.id, call.message.message_id, reply_markup=markup)
        elif data == 'list_mandatory_channels':
            if user_id not in admin_ids:
                bot.answer_callback_query(call.id, "⚠️ Admin required.", show_alert=True)
                return
            bot.answer_callback_query(call.id)
            if not mandatory_channels:
                bot.edit_message_text("📢 No mandatory channels.", call.message.chat.id, call.message.message_id)
                return
            msg = "📢 Mandatory Channels:\n\n"
            for channel_id, info in mandatory_channels.items():
                msg += f"• {info.get('name', 'Unknown')} ({info.get('username', channel_id)})\n"
            bot.edit_message_text(msg, call.message.chat.id, call.message.message_id)
        elif data.startswith('remove_channel_'):
            if user_id not in admin_ids:
                bot.answer_callback_query(call.id, "⚠️ Admin required.", show_alert=True)
                return
            channel_id = data.replace('remove_channel_', '')
            if channel_id in mandatory_channels:
                del mandatory_channels[channel_id]
                with DB_LOCK:
                    conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
                    c = conn.cursor()
                    try:
                        c.execute('DELETE FROM mandatory_channels WHERE channel_id = ?', (channel_id,))
                        conn.commit()
                    except:
                        pass
                    finally:
                        conn.close()
                bot.answer_callback_query(call.id, "✅ Channel removed.")
                bot.edit_message_text("📢 Channel removed.", call.message.chat.id, call.message.message_id)
            else:
                bot.answer_callback_query(call.id, "❌ Channel not found.", show_alert=True)
        else:
            bot.answer_callback_query(call.id, "Unknown action.")
    except Exception as e:
        logger.error(f"Callback error: {e}")
        try:
            bot.answer_callback_query(call.id, "Error.", show_alert=True)
        except:
            pass

# --- Step Handlers ---
def process_add_admin_id(message):
    if message.from_user.id != OWNER_ID:
        bot.reply_to(message, "⚠️ Owner only.")
        return
    if message.text.lower() == '/cancel':
        bot.reply_to(message, "❌ Cancelled.")
        return
    try:
        new_admin_id = int(message.text.strip())
        if new_admin_id in admin_ids:
            bot.reply_to(message, f"⚠️ Already admin.")
            return
        add_admin_db(new_admin_id, OWNER_ID)
        bot.reply_to(message, f"✅ Admin `{new_admin_id}` added.")
    except:
        bot.reply_to(message, "❌ Invalid ID.")

def process_remove_admin_id(message):
    if message.from_user.id != OWNER_ID:
        bot.reply_to(message, "⚠️ Owner only.")
        return
    if message.text.lower() == '/cancel':
        bot.reply_to(message, "❌ Cancelled.")
        return
    try:
        admin_id_remove = int(message.text.strip())
        if admin_id_remove == OWNER_ID:
            bot.reply_to(message, "⚠️ Cannot remove owner.")
            return
        if remove_admin_db(admin_id_remove):
            bot.reply_to(message, f"✅ Admin `{admin_id_remove}` removed.")
        else:
            bot.reply_to(message, f"❌ Failed to remove.")
    except:
        bot.reply_to(message, "❌ Invalid ID.")

def process_add_subscription_details(message):
    if message.from_user.id not in admin_ids:
        bot.reply_to(message, "⚠️ Not authorized.")
        return
    if message.text.lower() == '/cancel':
        bot.reply_to(message, "❌ Cancelled.")
        return
    try:
        parts = message.text.split()
        if len(parts) != 2:
            raise ValueError
        sub_user_id = int(parts[0])
        days = int(parts[1])
        current_expiry = user_subscriptions.get(sub_user_id, {}).get('expiry')
        start_date = datetime.now()
        if current_expiry and current_expiry > start_date:
            start_date = current_expiry
        new_expiry = start_date + timedelta(days=days)
        save_subscription(sub_user_id, new_expiry)
        bot.reply_to(message, f"✅ Sub for `{sub_user_id}` by {days} days.\nExpiry: {new_expiry:%Y-%m-%d}")
        try:
            bot.send_message(sub_user_id, f"🎉 Subscription extended by {days} days! Expires: {new_expiry:%Y-%m-%d}")
        except:
            pass
    except:
        bot.reply_to(message, "❌ Invalid format. Use: `12345678 30`")

def process_remove_subscription_id(message):
    if message.from_user.id not in admin_ids:
        bot.reply_to(message, "⚠️ Not authorized.")
        return
    if message.text.lower() == '/cancel':
        bot.reply_to(message, "❌ Cancelled.")
        return
    try:
        sub_user_id = int(message.text.strip())
        if sub_user_id not in user_subscriptions:
            bot.reply_to(message, f"⚠️ No active sub for `{sub_user_id}`.")
            return
        remove_subscription_db(sub_user_id)
        bot.reply_to(message, f"✅ Sub for `{sub_user_id}` removed.")
        try:
            bot.send_message(sub_user_id, "ℹ️ Your subscription has been removed by admin.")
        except:
            pass
    except:
        bot.reply_to(message, "❌ Invalid ID.")

def process_check_subscription_id(message):
    if message.from_user.id not in admin_ids:
        bot.reply_to(message, "⚠️ Not authorized.")
        return
    if message.text.lower() == '/cancel':
        bot.reply_to(message, "❌ Cancelled.")
        return
    try:
        sub_user_id = int(message.text.strip())
        if sub_user_id in user_subscriptions:
            expiry = user_subscriptions[sub_user_id].get('expiry')
            if expiry and expiry > datetime.now():
                days_left = (expiry - datetime.now()).days
                bot.reply_to(message, f"✅ Active sub for `{sub_user_id}`.\nExpires: {expiry:%Y-%m-%d} ({days_left} days left)")
            else:
                bot.reply_to(message, f"⚠️ Expired sub for `{sub_user_id}`.")
                remove_subscription_db(sub_user_id)
        else:
            bot.reply_to(message, f"ℹ️ No sub for `{sub_user_id}`.")
    except:
        bot.reply_to(message, "❌ Invalid ID.")

def process_broadcast_message(message):
    if message.from_user.id not in admin_ids:
        bot.reply_to(message, "⚠️ Not authorized.")
        return
    if message.text and message.text.lower() == '/cancel':
        bot.reply_to(message, "❌ Cancelled.")
        return
    broadcast_text = message.text
    if not broadcast_text:
        bot.reply_to(message, "⚠️ No text to broadcast.")
        return
    markup = types.InlineKeyboardMarkup()
    markup.row(types.InlineKeyboardButton("✅ Confirm", callback_data=f'confirm_broadcast_{message.message_id}'),
               types.InlineKeyboardButton("❌ Cancel", callback_data='cancel_broadcast'))
    bot.reply_to(message, f"📢 Confirm broadcast to {len(active_users)} users:\n\n{broadcast_text[:500]}", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('confirm_broadcast_'))
def handle_confirm_broadcast(call):
    if call.from_user.id not in admin_ids:
        bot.answer_callback_query(call.id, "⚠️ Admin only.", show_alert=True)
        return
    original_msg = call.message.reply_to_message
    if not original_msg:
        bot.answer_callback_query(call.id, "❌ No message.", show_alert=True)
        return
    broadcast_text = original_msg.text
    if not broadcast_text:
        bot.answer_callback_query(call.id, "❌ No text.", show_alert=True)
        return
    bot.answer_callback_query(call.id, "📢 Broadcasting...")
    bot.edit_message_text(f"📢 Broadcasting to {len(active_users)} users...", call.message.chat.id, call.message.message_id)
    sent = 0
    for user_id in list(active_users):
        try:
            bot.send_message(user_id, f"📢 Announcement:\n\n{broadcast_text}")
            sent += 1
            time.sleep(0.1)
        except:
            pass
    bot.edit_message_text(f"✅ Broadcast complete!\nSent to {sent}/{len(active_users)} users.", call.message.chat.id, call.message.message_id)

@bot.callback_query_handler(func=lambda call: call.data == 'cancel_broadcast')
def handle_cancel_broadcast(call):
    bot.answer_callback_query(call.id, "❌ Cancelled.")
    bot.delete_message(call.message.chat.id, call.message.message_id)

def process_admin_install(message):
    if message.from_user.id not in admin_ids:
        bot.reply_to(message, "⚠️ Not authorized.")
        return
    if message.text.lower() == '/cancel':
        bot.reply_to(message, "❌ Cancelled.")
        return
    try:
        parts = message.text.split()
        if len(parts) < 2:
            bot.reply_to(message, "❌ Format: `user_id module_name`")
            return
        user_id = int(parts[0])
        module_name = ' '.join(parts[1:])
        attempt_install_pip(module_name, message)
        try:
            bot.send_message(user_id, f"📦 Admin installed module `{module_name}` for you.")
        except:
            pass
    except:
        bot.reply_to(message, "❌ Invalid format.")

def process_add_channel(message):
    if message.from_user.id not in admin_ids:
        bot.reply_to(message, "⚠️ Not authorized.")
        return
    if message.text.lower() == '/cancel':
        bot.reply_to(message, "❌ Cancelled.")
        return
    channel_identifier = message.text.strip()
    try:
        chat = bot.get_chat(channel_identifier)
        channel_id = str(chat.id)
        channel_username = f"@{chat.username}" if chat.username else ""
        channel_name = chat.title
        mandatory_channels[channel_id] = {
            'username': channel_username,
            'name': channel_name
        }
        with DB_LOCK:
            conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
            c = conn.cursor()
            try:
                c.execute('INSERT OR REPLACE INTO mandatory_channels (channel_id, channel_username, channel_name, added_by, added_date) VALUES (?, ?, ?, ?, ?)',
                          (channel_id, channel_username, channel_name, message.from_user.id, datetime.now().isoformat()))
                conn.commit()
            except:
                pass
            finally:
                conn.close()
        bot.reply_to(message, f"✅ Channel added:\n{channel_name}\n{channel_username or channel_id}")
    except Exception as e:
        bot.reply_to(message, f"❌ Error: {str(e)}")

def process_ban_user(message):
    if message.from_user.id not in admin_ids:
        bot.reply_to(message, "⚠️ Not authorized.")
        return
    if message.text.lower() == '/cancel':
        bot.reply_to(message, "❌ Cancelled.")
        return
    try:
        parts = message.text.split()
        if len(parts) < 2:
            bot.reply_to(message, "❌ Format: `user_id reason`")
            return
        user_id = int(parts[0])
        reason = ' '.join(parts[1:])
        if user_id == OWNER_ID:
            bot.reply_to(message, "⚠️ Cannot ban owner.")
            return
        if ban_user_db(user_id, reason, message.from_user.id):
            bot.reply_to(message, f"✅ User `{user_id}` banned.\nReason: {reason}")
            # Stop all scripts
            for file_name, _ in user_files.get(user_id, []):
                script_key = f"{user_id}_{file_name}"
                if script_key in bot_scripts:
                    kill_process_tree(bot_scripts[script_key])
                    del bot_scripts[script_key]
            try:
                bot.send_message(user_id, f"🚫 You have been banned.\nReason: {reason}")
            except:
                pass
        else:
            bot.reply_to(message, "❌ Failed to ban.")
    except:
        bot.reply_to(message, "❌ Invalid ID.")

def process_unban_user(message):
    if message.from_user.id not in admin_ids:
        bot.reply_to(message, "⚠️ Not authorized.")
        return
    if message.text.lower() == '/cancel':
        bot.reply_to(message, "❌ Cancelled.")
        return
    try:
        user_id = int(message.text.strip())
        if user_id not in banned_users:
            bot.reply_to(message, f"ℹ️ User `{user_id}` not banned.")
            return
        if unban_user_db(user_id):
            bot.reply_to(message, f"✅ User `{user_id}` unbanned.")
            try:
                bot.send_message(user_id, "✅ Your ban has been lifted.")
            except:
                pass
        else:
            bot.reply_to(message, "❌ Failed to unban.")
    except:
        bot.reply_to(message, "❌ Invalid ID.")

def process_user_info(message):
    if message.from_user.id not in admin_ids:
        bot.reply_to(message, "⚠️ Not authorized.")
        return
    if message.text.lower() == '/cancel':
        bot.reply_to(message, "❌ Cancelled.")
        return
    try:
        user_id = int(message.text.strip())
        info = f"👤 User Info: `{user_id}`\n"
        if user_id == OWNER_ID:
            info += "👑 Owner\n"
        elif user_id in admin_ids:
            info += "🛡️ Admin\n"
        elif user_id in banned_users:
            info += "🚫 Banned\n"
        elif user_id in user_subscriptions:
            expiry = user_subscriptions[user_id].get('expiry')
            if expiry and expiry > datetime.now():
                days_left = (expiry - datetime.now()).days
                info += f"⭐ Premium (Expires in {days_left} days)\n"
            else:
                info += "🆓 Free (Expired)\n"
        else:
            info += "🆓 Free\n"
        file_count = get_user_file_count(user_id)
        file_limit = get_user_file_limit(user_id)
        info += f"📁 Files: {file_count}/{file_limit if file_limit != float('inf') else 'Unlimited'}\n"
        if user_id in user_limits:
            info += f"⚙️ Custom Limit: {user_limits[user_id]}\n"
        running = sum(1 for f, _ in user_files.get(user_id, []) if is_bot_running(user_id, f))
        info += f"🤖 Running: {running}"
        bot.reply_to(message, info, parse_mode='Markdown')
    except:
        bot.reply_to(message, "❌ Invalid ID.")

def process_set_user_limit(message):
    if message.from_user.id not in admin_ids:
        bot.reply_to(message, "⚠️ Not authorized.")
        return
    if message.text.lower() == '/cancel':
        bot.reply_to(message, "❌ Cancelled.")
        return
    try:
        parts = message.text.split()
        if len(parts) != 2:
            raise ValueError
        user_id = int(parts[0])
        limit = int(parts[1])
        if set_user_limit_db(user_id, limit, message.from_user.id):
            bot.reply_to(message, f"✅ Limit set to {limit} for user `{user_id}`.")
            try:
                bot.send_message(user_id, f"⚙️ Your file limit set to {limit}.")
            except:
                pass
        else:
            bot.reply_to(message, "❌ Failed to set limit.")
    except:
        bot.reply_to(message, "❌ Format: `user_id limit`")

def process_remove_user_limit(message):
    if message.from_user.id not in admin_ids:
        bot.reply_to(message, "⚠️ Not authorized.")
        return
    if message.text.lower() == '/cancel':
        bot.reply_to(message, "❌ Cancelled.")
        return
    try:
        user_id = int(message.text.strip())
        if user_id not in user_limits:
            bot.reply_to(message, f"ℹ️ No custom limit for `{user_id}`.")
            return
        if remove_user_limit_db(user_id):
            bot.reply_to(message, f"✅ Removed custom limit for `{user_id}`.")
            try:
                bot.send_message(user_id, "⚙️ Your custom limit has been removed.")
            except:
                pass
        else:
            bot.reply_to(message, "❌ Failed to remove.")
    except:
        bot.reply_to(message, "❌ Invalid ID.")

# --- Cleanup ---
def cleanup():
    logger.warning("Shutting down. Cleaning up processes...")
    for key in list(bot_scripts.keys()):
        if key in bot_scripts:
            kill_process_tree(bot_scripts[key])
            del bot_scripts[key]

atexit.register(cleanup)

# --- Main ---
if __name__ == '__main__':
    logger.info("🤖 Hosting Bot Starting...")
    keep_alive()
    while True:
        try:
            bot.infinity_polling(timeout=60, long_polling_timeout=30)
        except Exception as e:
            logger.error(f"Polling error: {e}")
            time.sleep(10)
