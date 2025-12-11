from datetime import datetime
import time
from pymongo import MongoClient
from config import (
    MONGO_URI,
    DB_NAME,
    DEFAULT_DAILY_COUNT_LIMIT,
    DEFAULT_DAILY_SIZE_LIMIT_MB,
    PREMIUM_DAILY_COUNT_LIMIT,
    PREMIUM_DAILY_SIZE_LIMIT_MB,
    ADMIN_IDS,
)


mongo_client = MongoClient(MONGO_URI)
db = mongo_client[DB_NAME]

users_col = db["users"]
bans_col = db["banned"]
stats_col = db["stats"]  # global stats


def today_str():
    return datetime.utcnow().strftime("%Y-%m-%d")


def mb_to_bytes(mb: int) -> int:
    return mb * 1024 * 1024


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


def is_banned(user_id: int) -> bool:
    return bans_col.find_one({"user_id": user_id}) is not None


def ban_user(user_id: int, reason: str | None = None):
    bans_col.update_one(
        {"user_id": user_id},
        {"$set": {"reason": reason or "no reason", "date": datetime.utcnow()}},
        upsert=True,
    )


def unban_user(user_id: int):
    bans_col.delete_one({"user_id": user_id})


def get_banlist(limit: int = 50):
    return list(bans_col.find().sort("date", -1).limit(limit))


def get_user_doc(user_id: int):
    t = today_str()
    user = users_col.find_one({"user_id": user_id})
    if not user:
        user = {
            "user_id": user_id,
            "is_premium": False,

            # DAILY LIMITS
            "daily_count_limit": DEFAULT_DAILY_COUNT_LIMIT,
            "daily_size_limit": mb_to_bytes(DEFAULT_DAILY_SIZE_LIMIT_MB),

            # TODAY USAGE
            "used_count_today": 0,
            "used_size_today": 0,
            "last_date": t,

            # last successful upload time (for cooldown)
            "last_upload_ts": 0.0,

            # SETTINGS
            "thumb_file_id": None,
            "caption": None,
            "spoiler": False,
            "send_screenshots": False,
            "send_sample": False,
            "sample_duration": 15,
            "prefix": "",
            "suffix": "",
            # upload type: video / document
            "upload_type": "video",
        }
        users_col.insert_one(user)
        return user

    if user.get("last_date") != t:
        users_col.update_one(
            {"_id": user["_id"]},
            {"$set": {
                "used_count_today": 0,
                "used_size_today": 0,
                "last_date": t,
            }}
        )
        user["used_count_today"] = 0
        user["used_size_today"] = 0
        user["last_date"] = t

    user.setdefault("is_premium", False)
    user.setdefault("daily_count_limit", DEFAULT_DAILY_COUNT_LIMIT)
    user.setdefault("daily_size_limit", mb_to_bytes(DEFAULT_DAILY_SIZE_LIMIT_MB))
    user.setdefault("used_count_today", 0)
    user.setdefault("used_size_today", 0)
    user.setdefault("last_upload_ts", 0.0)
    user.setdefault("thumb_file_id", None)
    user.setdefault("caption", None)
    user.setdefault("spoiler", False)
    user.setdefault("send_screenshots", False)
    user.setdefault("send_sample", False)
    user.setdefault("sample_duration", 15)
    user.setdefault("prefix", "")
    user.setdefault("suffix", "")
    user.setdefault("upload_type", "video")
    return user


def increment_usage(user_id: int, file_size: int):
    users_col.update_one(
        {"user_id": user_id},
        {
            "$inc": {
                "used_count_today": 1,
                "used_size_today": file_size,
            },
            "$set": {
                "last_upload_ts": time.time()
            }
        }
    )


def set_premium(user_id: int, count_limit: int | None, size_limit_mb: int | None, flag: bool):
    user = get_user_doc(user_id)
    if flag:
        user["is_premium"] = True
        user["daily_count_limit"] = count_limit if count_limit is not None else PREMIUM_DAILY_COUNT_LIMIT
        user["daily_size_limit"] = (
            mb_to_bytes(size_limit_mb) if size_limit_mb is not None
            else mb_to_bytes(PREMIUM_DAILY_SIZE_LIMIT_MB)
        )
    else:
        user["is_premium"] = False
        user["daily_count_limit"] = count_limit if count_limit is not None else DEFAULT_DAILY_COUNT_LIMIT
        user["daily_size_limit"] = (
            mb_to_bytes(size_limit_mb) if size_limit_mb is not None
            else mb_to_bytes(DEFAULT_DAILY_SIZE_LIMIT_MB)
        )

    users_col.update_one(
        {"user_id": user_id},
        {"$set": {
            "is_premium": user["is_premium"],
            "daily_count_limit": user["daily_count_limit"],
            "daily_size_limit": user["daily_size_limit"],
        }}
    )
    return user


def set_limits(user_id: int, count_limit: int | None, size_limit_mb: int | None):
    user = get_user_doc(user_id)
    if count_limit is not None:
        user["daily_count_limit"] = count_limit
    if size_limit_mb is not None:
        user["daily_size_limit"] = mb_to_bytes(size_limit_mb)

    update_fields = {}
    if count_limit is not None:
        update_fields["daily_count_limit"] = user["daily_count_limit"]
    if size_limit_mb is not None:
        update_fields["daily_size_limit"] = user["daily_size_limit"]

    if update_fields:
        users_col.update_one(
            {"user_id": user_id},
            {"$set": update_fields}
        )
    return user


def set_thumb(user_id: int, file_id: str | None):
    users_col.update_one({"user_id": user_id}, {"$set": {"thumb_file_id": file_id}})


def set_caption(user_id: int, caption: str | None):
    users_col.update_one({"user_id": user_id}, {"$set": {"caption": caption}})


def set_flag(user_id: int, key: str, value):
    users_col.update_one({"user_id": user_id}, {"$set": {key: value}})


def set_prefix(user_id: int, prefix: str):
    set_flag(user_id, "prefix", prefix)


def set_suffix(user_id: int, suffix: str):
    set_flag(user_id, "suffix", suffix)


def set_spoiler(user_id: int, flag: bool):
    set_flag(user_id, "spoiler", flag)


def set_screenshots(user_id: int, flag: bool):
    set_flag(user_id, "send_screenshots", flag)


def set_sample(user_id: int, flag: bool, duration: int | None = None):
    update = {"send_sample": flag}
    if duration is not None:
        update["sample_duration"] = duration
    users_col.update_one({"user_id": user_id}, {"$set": update})


def set_upload_type(user_id: int, utype: str):
    if utype not in ("video", "document"):
        return
    users_col.update_one({"user_id": user_id}, {"$set": {"upload_type": utype}})


def get_users_count():
    return users_col.count_documents({})


def get_all_users():
    return users_col.find({}, {"user_id": 1})


def update_stats(downloaded: int, uploaded: int):
    stats_col.update_one(
        {"_id": "global"},
        {"$inc": {
            "downloaded_bytes": downloaded,
            "uploaded_bytes": uploaded,
            "total_jobs": 1,
        }},
        upsert=True,
    )


def get_stats():
    s = stats_col.find_one({"_id": "global"}) or {}
    return {
        "downloaded": s.get("downloaded_bytes", 0),
        "uploaded": s.get("uploaded_bytes", 0),
        "jobs": s.get("total_jobs", 0),
        }
