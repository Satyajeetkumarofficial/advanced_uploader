import os

API_ID = int(os.getenv("API_ID", "25617967"))
API_HASH = os.getenv("API_HASH", "10555bea1cdfc7d2303fc13b7fd187cc")
BOT_TOKEN = os.getenv("BOT_TOKEN", "8090736841:AAEi5FkCzBhccIU8RbZBxmPTDq2V7a2c4UE")

MONGO_URI = os.getenv("MONGO_URI", "mongodb+srv://manishak4251:EXfIp5PR2kqBLU3x@cluster0.cqfxq.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0")

# DEFAULT LIMITS (0 = unlimited)
DEFAULT_DAILY_COUNT_LIMIT = int(os.getenv("DEFAULT_DAILY_COUNT_LIMIT", "10"))
DEFAULT_DAILY_SIZE_LIMIT_MB = int(os.getenv("DEFAULT_DAILY_SIZE_LIMIT_MB", "2000"))  # MB

PREMIUM_DAILY_COUNT_LIMIT = int(os.getenv("PREMIUM_DAILY_COUNT_LIMIT", "100"))
PREMIUM_DAILY_SIZE_LIMIT_MB = int(os.getenv("PREMIUM_DAILY_SIZE_LIMIT_MB", "10000"))

# ⏳ Normal users cooldown seconds (0 = disable)
NORMAL_COOLDOWN_SECONDS = int(os.getenv("NORMAL_COOLDOWN_SECONDS", "120"))  # 2 min

# 📊 Progress update interval (seconds)
PROGRESS_UPDATE_INTERVAL = int(os.getenv("PROGRESS_UPDATE_INTERVAL", "5"))
if PROGRESS_UPDATE_INTERVAL < 1:
    PROGRESS_UPDATE_INTERVAL = 5

# Telegram per-file limit (approx 2GB)
MAX_FILE_SIZE = 2 * 1024 * 1024 * 1024  # bytes

# Admin user IDs (comma separated in env: "123,456")
ADMIN_IDS = [
    int(x) for x in os.getenv("ADMINS", "7413682152").split(",") if x.strip().isdigit()
]

LOG_CHANNEL = int(os.getenv("LOG_CHANNEL", "-1002256697098"))  # -100...

BOT_USERNAME = os.getenv("BOT_USERNAME", "ProDemooBot")

# Proxy support (optional)
PROXY_URL = os.getenv("PROXY_URL", "").strip()
PROXIES = {"http": PROXY_URL, "https": PROXY_URL} if PROXY_URL else None

# cookies.txt path (for yt-dlp)
COOKIES_FILE = os.getenv("COOKIES_FILE", "/app/cookies.txt")

# FORCE SUBSCRIBE CHANNEL
# Example:
#   FORCE_SUB_CHANNEL=@MyChannel
#   ya FORCE_SUB_CHANNEL=-1001234567890
_raw_force = os.getenv("FORCE_SUB_CHANNEL", "-1003267218855").strip()

if _raw_force and _raw_force.lstrip("-").isdigit():
    # numeric ID hua to int bana do
    FORCE_SUB_CHANNEL = int(_raw_force)
else:
    # @username ya empty
    FORCE_SUB_CHANNEL = _raw_force or None

# progress update duration (seconds)
PROGRESS_UPDATE_INTERVAL = 3

# Free users ke liye daily limit
DEFAULT_DAILY_COUNT_LIMIT = 50          # 50 uploads per day
DEFAULT_DAILY_SIZE_LIMIT_MB = 10240     # 10240 MB = 10 GB per day

# Primium users ke liye daily limit
PREMIUM_DAILY_COUNT_LIMIT = 0   # 0 = unlimited
PREMIUM_DAILY_SIZE_LIMIT_MB = 0
