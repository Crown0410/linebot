from flask import Flask, request, jsonify
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, TextSendMessage
import json
import os
from datetime import datetime, timedelta

app = Flask(__name__)

# 🔹 設定 LINE Bot API
LINE_ACCESS_TOKEN = os.getenv('LINE_ACCESS_TOKEN')
LINE_SECRET = os.getenv('LINE_SECRET')
line_bot_api = LineBotApi(LINE_ACCESS_TOKEN)
line_handler = WebhookHandler(LINE_SECRET)

# 🔹 目標 emoji
TARGET_EMOJI = "我拉屎了"

# 🔹 記錄 emoji 使用次數、使用者名稱和最後使用時間、冷卻時間
COUNT_FILE = "emoji_count.json"
USER_NAMES_FILE = "user_names.json"
LAST_TIME_FILE = "last_time.json" 
COOLDOWN_FILE = "cooldown.json"

# 🔹 設定冷卻時間（分鐘）
COOLDOWN_MINUTES = 10

# 🔹 讀取現有的 JSON 檔案
def load_json(filename, default_data={}):
    if os.path.exists(filename):
        try:
            with open(filename, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            print(f"讀取 {filename} 時發生錯誤，使用預設值")
            return default_data
    return default_data

# 讀取資料
user_names = load_json(USER_NAMES_FILE)
last_times = load_json(LAST_TIME_FILE)
cooldowns = load_json(COOLDOWN_FILE)

# 修復 emoji_count 資料 - 讀取並修正問題
emoji_count_data = load_json(COUNT_FILE)
emoji_count = {}

# 將錯誤的時間數據轉換為整數計數
for user_id in emoji_count_data:
    # 如果是時間格式，重置為 1，否則保留原值
    if isinstance(emoji_count_data[user_id], str) and ":" in emoji_count_data[user_id]:
        emoji_count[user_id] = 1  # 重設為 1
    else:
        try:
            # 嘗試轉換為整數
            emoji_count[user_id] = int(emoji_count_data[user_id])
        except (ValueError, TypeError):
            emoji_count[user_id] = 1  # 無法轉換時重設為 1

# 立即儲存修復後的 emoji_count
with open(COUNT_FILE, "w", encoding="utf-8") as f:
    json.dump(emoji_count, f, ensure_ascii=False, indent=4)

# 🔹 儲存 JSON 到檔案
def save_json(data, filename):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

# 🔹 檢查是否在冷卻時間內
def is_in_cooldown(user_id):
    if user_id not in cooldowns:
        return False
    
    # 將記錄的冷卻時間轉換為 datetime 物件
    cooldown_time = datetime.strptime(cooldowns[user_id], "%Y-%m-%d %H:%M:%S")
    current_time = datetime.now()
    
    # 計算冷卻結束時間
    cooldown_end_time = cooldown_time + timedelta(minutes=COOLDOWN_MINUTES)
    
    # 檢查是否仍在冷卻時間內
    return current_time < cooldown_end_time

# 🔹 計算冷卻剩餘時間（分鐘）
def get_remaining_cooldown(user_id):
    if user_id not in cooldowns:
        return 0
    
    cooldown_time = datetime.strptime(cooldowns[user_id], "%Y-%m-%d %H:%M:%S")
    current_time = datetime.now()
    cooldown_end_time = cooldown_time + timedelta(minutes=COOLDOWN_MINUTES)
    
    # 如果已經過了冷卻時間
    if current_time >= cooldown_end_time:
        return 0
    
    # 計算剩餘分鐘數
    remaining_seconds = (cooldown_end_time - current_time).total_seconds()
    remaining_minutes = remaining_seconds / 60
    
    return round(remaining_minutes, 1)  # 取到小數點第一位

# 📌 Webhook 入口
@app.route("/callback", methods=["POST"])
def callback():
    data = request.get_json(silent=True)
    print("收到 Line 請求:", data)  # Debug 用

    for event in data["events"]:
        if event.get("type") == "message":
            user_id = event["source"]["userId"]
            message_text = event["message"]["text"]

            # ✅ 取得使用者名稱（如果還沒存過，就查詢 API）
            if user_id not in user_names:
                profile = line_bot_api.get_profile(user_id)
                user_names[user_id] = profile.display_name
                save_json(user_names, USER_NAMES_FILE)

            display_name = user_names[user_id]

            # ✅ 如果訊息中包含特定 emoji，就增加計數
            if TARGET_EMOJI in message_text:
                # 檢查冷卻時間
                if is_in_cooldown(user_id):
                    remaining_time = get_remaining_cooldown(user_id)
                    reply_message = f"⚠️ {display_name} 你拉太多次囉，小心脫肛！還需要冷卻 {remaining_time} 分鐘才能再次使用。"
                    line_bot_api.reply_message(event["replyToken"], TextSendMessage(text=reply_message))
                else:
                    # 不在冷卻時間內，可以正常計數
                    if user_id not in emoji_count:
                        emoji_count[user_id] = 0
                    
                    # 計數加上出現次數
                    count_to_add = message_text.count(TARGET_EMOJI)
                    emoji_count[user_id] += count_to_add
                    
                    # 記錄最後使用時間
                    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    last_times[user_id] = current_time
                    
                    # 設定冷卻時間（當前時間）
                    cooldowns[user_id] = current_time
                    
                    # 儲存所有資料
                    save_json(emoji_count, COUNT_FILE)
                    save_json(last_times, LAST_TIME_FILE)
                    save_json(cooldowns, COOLDOWN_FILE)
                    
                    # 顯示整數計數
                    reply_message = f"💩 {display_name} 你的 拉屎次數 已經被計算 {emoji_count[user_id]} 次！"
                    line_bot_api.reply_message(event["replyToken"], TextSendMessage(text=reply_message))

            # ✅ 如果輸入 `/count`，回傳所有人的 emoji 統計
            elif message_text == "/要幾次":
                reply_message = "💩 拉屎 次數統計 💩\n"
                for user, count in emoji_count.items():
                    name = user_names.get(user, "未知使用者")
                    last_time = last_times.get(user, "未記錄")

                    # 檢查是否在冷卻中，如果是，顯示剩餘時間
                    cooldown_status = ""
                    if is_in_cooldown(user):
                        remaining = get_remaining_cooldown(user)
                        cooldown_status = f"[冷卻中: 還剩 {remaining} 分鐘]"
                    
                    reply_message += f"👤 {name}: {count} 次 {{最後拉屎時間：{last_time}}} {cooldown_status}\n"

                line_bot_api.reply_message(event["replyToken"], TextSendMessage(text=reply_message))

    return jsonify({"message": "OK"}), 200

if __name__ == "__main__":
    app.run(port=5000, debug=True)