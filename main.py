# ==== Optional Keep Alive Server (for uptime checks) ====
from threading import Thread
from flask import Flask

keep_app = Flask(__name__)

@keep_app.route("/")
def home():
    return "Bot is alive", 200

def run_keep_alive():
    keep_app.run(host="0.0.0.0", port=8080)

Thread(target=run_keep_alive).start()
# =======================================================

from pyrogram import Client
from config import API_ID, API_HASH, BOT_TOKEN
from handlers.start import register_start_handlers
from handlers.user_settings import register_user_settings_handlers
from handlers.admin import register_admin_handlers
from handlers.url_handler import register_url_handlers


def main():
    app = Client(
        "advanced_uploader_bot",
        api_id=API_ID,
        api_hash=API_HASH,
        bot_token=BOT_TOKEN,
    )

    register_start_handlers(app)
    register_user_settings_handlers(app)
    register_admin_handlers(app)
    register_url_handlers(app)

    print("✅ Advanced Uploader Bot started...")
    app.run()


if __name__ == "__main__":
    main()
