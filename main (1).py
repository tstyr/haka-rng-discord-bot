import discord
import random
import datetime
import os
import asyncio
import json
import math
import time

intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.reactions = True  # リアクションイベントを有効にする
bot = discord.Client(intents=intents)

USER_DATA_FILE = 'user_data.json'
BOT_SETTINGS_FILE = 'bot_settings.json'
ADMIN_IDS = [929555026612715530, 974264083853492234]

# 各アイテムの基本確率 (分母)
# base_item_chances_denominator は、接頭辞を持たない「基本アイテム」の確率を定義します。
# golden, rainbow版は、この基本確率から自動計算されます。
base_item_chances_denominator = {
    "haka": 1000000,
    "shiny haka": 3000000,
    "hage uku": 50,
    "うくうく": 2,
    "ごあ": 100000000,
    "はかうく": 4,
    "じゃうく": 10000000,
    "ピグパイセン": 1000000000,
    "みず": 30
}

# 合成レシピと直接ドロップ確率を動的に生成する関数
def generate_item_data(base_chances):
    all_item_chances = {}
    crafting_recipes = {}

    for item_name, base_chance in base_chances.items():
        # 基本アイテム
        all_item_chances[item_name] = base_chance

        # Golden版
        golden_item_name = f"golden {item_name}"
        # 基本の10倍出にくくする (分母を10倍にする)
        golden_chance = base_chance * 10
        all_item_chances[golden_item_name] = golden_chance

        # Rainbow版
        rainbow_item_name = f"rainbow {item_name}"
        # 基本の100倍出にくくする (分母を100倍にする)
        rainbow_chance = base_chance * 100
        all_item_chances[rainbow_item_name] = rainbow_chance

        # 合成レシピ: 基本 -> Golden
        crafting_recipes[golden_item_name] = {
            "materials": {item_name: 10},
            "output": {golden_item_name: 1}
        }
        # 合成レシピ: Golden -> Rainbow
        crafting_recipes[rainbow_item_name] = {
            "materials": {golden_item_name: 10},
            "output": {rainbow_item_name: 1}
        }
    
    return all_item_chances, crafting_recipes

rare_item_chances_denominator, CRAFTING_RECIPES = generate_item_data(base_item_chances_denominator)

auto_rng_sessions = {}
bot_settings = {}
user_data = {} # グローバル変数として定義

# --- データ保存・ロード関数 ---
def save_user_data():
    """ユーザーデータをJSONファイルに保存する"""
    with open(USER_DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(user_data, f, ensure_ascii=False, indent=4)

def load_user_data():
    """JSONファイルからユーザーデータを読み込む"""
    global user_data
    if os.path.exists(USER_DATA_FILE):
        with open(USER_DATA_FILE, 'r', encoding='utf-8') as f:
            try:
                user_data = json.load(f)
            except json.JSONDecodeError as e:
                print(f"ERROR: user_data.jsonの読み込み中にエラーが発生しました: {e}")
                print("既存のuser_data.jsonをバックアップし、新しく空のデータを作成します。")
                if os.path.exists(USER_DATA_FILE):
                    os.rename(USER_DATA_FILE, USER_DATA_FILE + ".bak." + datetime.datetime.now().strftime("%Y%m%d%H%M%S"))
                user_data = {} # エラー時は空のデータで初期化
                save_user_data() # 空のデータを保存
    else:
        user_data = {}

def save_bot_settings():
    """ボット設定をJSONファイルに保存する"""
    with open(BOT_SETTINGS_FILE, 'w', encoding='utf-8') as f:
        json.dump(bot_settings, f, ensure_ascii=False, indent=4)

def load_bot_settings():
    """JSONファイルからボット設定を読み込む"""
    global bot_settings
    if os.path.exists(BOT_SETTINGS_FILE):
        with open(BOT_SETTINGS_FILE, 'r', encoding='utf-8') as f:
            try:
                bot_settings = json.load(f)
            except json.JSONDecodeError as e:
                print(f"ERROR: bot_settings.jsonの読み込み中にエラーが発生しました: {e}")
                print("既存のbot_settings.jsonをバックアップし、新しく空のデータを作成します。")
                if os.path.exists(BOT_SETTINGS_FILE):
                    os.rename(BOT_SETTINGS_FILE, BOT_SETTINGS_FILE + ".bak." + datetime.datetime.now().strftime("%Y%m%d%H%M%S"))
                bot_settings = {"notification_channel_id": None} # エラー時は空のデータで初期化
                save_bot_settings() # 空のデータを保存
    else:
        bot_settings = {"notification_channel_id": None} # 初期設定

# --- イベントハンドラ ---
@bot.event
async def on_ready():
    print(f'ログイン完了: {bot.user}')
    load_user_data()
    load_bot_settings()
    print("ユーザーデータをロードしました。")
    print("ボット設定をロードしました。")
    auto_rng_sessions.clear()

async def send_auto_rng_results(user: discord.User, found_items_log: list, total_rolls: int, stop_reason: str):
    """オートRNGの結果をユーザーにDMで送信する"""
    if not found_items_log:
        await user.send(f"オートRNGが{stop_reason}しました。残念ながら何も見つかりませんでした。総ロール数: {total_rolls}回")
        return

    result_text = f"オートRNGが{stop_reason}しました！\n\n**今回見つかったアイテム:**\n"
    item_counts = {}
    for item in found_items_log:
        item_counts[item] = item_counts.get(item, 0) + 1

    for item, count in item_counts.items():
        result_text += f"- {item}: {count}個\n"

    result_text += f"\n**総ロール数:** {total_rolls}回"

    if len(result_text) > 2000:
        chunks = [result_text[i:i + 1900] for i in range(0, len(result_text), 1900)]
        for chunk in chunks:
            await user.send(chunk)
    else:
        await user.send(result_text)

# --- ロール実行ロジックの共通化 ---
def perform_roll(luck):
    """
    アイテムを抽選し、結果を返す。
    必ず何かしらのアイテムがドロップするように保証する。
    """
    items = list(rare_item_chances_denominator.keys())
    weights = []
    
    for item in items:
        # 確率 = 1 / 分母 * ラック
        actual_chance = 1 / rare_item_chances_denominator[item] * luck
        weights.append(actual_chance)
    
    # 重みに基づいてアイテムを選択
    chosen_item = random.choices(items, weights=weights, k=1)[0]
    
    real_chance_denominator = rare_item_chances_denominator[chosen_item]
    
    return chosen_item, real_chance_denominator

# --- ページネーション用グローバル辞書 ---
# {メッセージID: {
#   "user_id": int,
#   "current_page": int,
#   "items_per_page": int,
#   "current_category": "normal" | "golden" | "rainbow",
#   "normal_items": list[tuple[str, int]],
#   "golden_items": list[tuple[str, int]],
#   "rainbow_items": list[tuple[str, int]],
#   "total_item_counts": dict
# }}
pagination_sessions = {}

async def generate_itemlist_embed(user_id, page_num, items_per_page, category_name, category_items, total_item_counts):
    """
    指定されたページ番号、カテゴリのアイテムリストEmbedを生成する。
    """
    user_inventory = user_data[str(user_id)]["inventory"]
    
    start_index = page_num * items_per_page
    end_index = start_index + items_per_page
    items_to_display = category_items[start_index:end_index]

    total_pages = math.ceil(len(category_items) / items_per_page)
    if total_pages == 0: # アイテムがない場合の表示
        total_pages = 1

    embed_title = ""
    if category_name == "normal":
        embed_title = f"🐾 ノーマルアイテムリスト (ページ {page_num + 1}/{total_pages})"
    elif category_name == "golden":
        embed_title = f"⭐ ゴールデンアイテムリスト (ページ {page_num + 1}/{total_pages})"
    elif category_name == "rainbow":
        embed_title = f"🌈 レインボーアイテムリスト (ページ {page_num + 1}/{total_pages})"
    
    embed = discord.Embed(
        title=embed_title,
        description="全アイテムの確率とあなたの所持数、そしてサーバー全体の総所持数です。",
        color=discord.Color.orange()
    )

    if not items_to_display:
        embed.add_field(name="情報なし", value="このカテゴリにはアイテムがありません。", inline=False)
    else:
        for item_name, chance_denominator in items_to_display:
            display_chance = f"1 in {chance_denominator:,}"
            owned_count = user_inventory.get(item_name, 0)
            total_owned_count = total_item_counts.get(item_name, 0)
            embed.add_field(name=item_name, value=f"確率: {display_chance}\nあなたの所持数: {owned_count}個\nサーバー総所持数: {total_owned_count}個", inline=True)
    
    embed.set_footer(text=f"ページ {page_num + 1}/{total_pages} | レアリティ順")
    return embed

@bot.event
async def on_reaction_add(reaction, user):
    # ボット自身のリアクションは無視
    if user.bot:
        return

    # pagination_sessions に該当メッセージがあるかチェック
    if reaction.message.id in pagination_sessions:
        session = pagination_sessions[reaction.message.id]

        # このページネーションを開始したユーザーのみが操作できるようにする
        if user.id != session["user_id"]:
            await reaction.remove(user) # 無関係なユーザーのリアクションは削除
            return

        current_page = session["current_page"]
        items_per_page = session["items_per_page"]
        current_category = session["current_category"]
        total_item_counts = session["total_item_counts"]

        # 現在のカテゴリのアイテムリストを取得
        category_items_map = {
            "normal": session["normal_items"],
            "golden": session["golden_items"],
            "rainbow": session["rainbow_items"]
        }
        category_items = category_items_map.get(current_category, [])

        max_pages = math.ceil(len(category_items) / items_per_page)
        if max_pages == 0:
            max_pages = 1 # アイテムがない場合でもページ数は1として扱う

        new_page = current_page
        new_category = current_category
        
        # カテゴリ切り替えリアクションの処理
        if str(reaction.emoji) == '🐾':
            new_category = "normal"
            new_page = 0 # カテゴリ切り替え時はページをリセット
        elif str(reaction.emoji) == '⭐': # 変更点: '⭐️' から '⭐' へ
            new_category = "golden"
            new_page = 0
        elif str(reaction.emoji) == '🌈':
            new_category = "rainbow"
            new_page = 0
        # ページ送りリアクションの処理
        elif str(reaction.emoji) == '◀️':
            new_page = max(0, current_page - 1)
        elif str(reaction.emoji) == '▶️':
            new_page = min(max_pages - 1, current_page + 1)
        
        # 変更があった場合のみEmbedを更新
        # 新しいカテゴリまたは新しいページ番号
        if new_category != current_category or new_page != current_page:
            session["current_page"] = new_page
            session["current_category"] = new_category

            # 新しいカテゴリのアイテムリストを再取得
            updated_category_items = category_items_map.get(new_category, [])

            # 新しいカテゴリの総ページ数を再計算
            updated_max_pages = math.ceil(len(updated_category_items) / items_per_page)
            if updated_max_pages == 0:
                updated_max_pages = 1
            
            # 新しいカテゴリに切り替えた際、ページ番号が有効範囲外にならないように調整
            if new_page >= updated_max_pages:
                session["current_page"] = 0 # ページを0にリセット

            updated_embed = await generate_itemlist_embed(
                session["user_id"], 
                session["current_page"], # 調整後のページ番号
                session["items_per_page"], 
                session["current_category"], 
                updated_category_items, 
                total_item_counts
            )
            await reaction.message.edit(embed=updated_embed)
            await reaction.remove(user) # リアクションを削除して次の操作に備える
        else:
            await reaction.remove(user) # リアクションを削除 (ページが変わらない場合も)


@bot.event
async def on_message(message):
    if message.author.bot:
        return

    user_id = str(message.author.id)

    # ユーザーデータがなければ初期化
    if user_id not in user_data:
        user_data[user_id] = {
            "rolls": 0,
            "luck": 1.0,
            "inventory": {},
            "daily_login": { # デイリーログイン関連のデータ
                "last_login_date": None, # 最終ログイン日 (YYYY-MM-DD形式)
                "consecutive_days": 0,   # 連続ログイン日数
                "active_boost": {        # 現在アクティブなラックブースト
                    "multiplier": 1.0,
                    "end_time": None     # UNIXタイムスタンプ
                }
            }
        }
        save_user_data()
    
    # 既存のユーザーのデイリーログインデータに不足があれば初期値を追加（互換性維持のため）
    if "daily_login" not in user_data[user_id]:
        user_data[user_id]["daily_login"] = {
            "last_login_date": None,
            "consecutive_days": 0,
            "active_boost": {
                "multiplier": 1.0,
                "end_time": None
            }
        }
        save_user_data()

    # --- ラックブーストの適用と期限切れチェック ---
    current_time = datetime.datetime.now(datetime.timezone.utc)
    user_boost = user_data[user_id]["daily_login"]["active_boost"]

    # ブーストが設定されており、かつ終了時刻を過ぎている場合
    if user_boost["end_time"] and current_time > datetime.datetime.fromtimestamp(user_boost["end_time"], tz=datetime.timezone.utc):
        user_data[user_id]["luck"] /= user_boost["multiplier"] # ラックを元に戻す
        user_data[user_id]["luck"] = round(user_data[user_id]["luck"], 1) # 小数点以下を丸める
        user_boost["multiplier"] = 1.0
        user_boost["end_time"] = None
        save_user_data()
        await message.channel.send(f"{message.author.mention} の一時的なラックブーストが終了しました。")
    
    # 現在のラック値を取得 (ブーストが終了していても、まだ反映されていない場合があるので念のためここで取得)
    user_luck = user_data[user_id]["luck"]


    # --- ヘルプコマンド ---
    if message.content.lower() == "!help":
        embed = discord.Embed(
            title="コマンド一覧",
            description="このボットで使えるコマンドはこちらです。",
            color=discord.Color.green()
        )
        embed.add_field(name="`!rng`", value="ランダムアイテムをロールします。", inline=False)
        embed.add_field(name="`!status`", value="あなたの現在のロール数、ラック、インベントリを表示します。", inline=False)
        embed.add_field(name="`!itemlist`", value="全アイテムの確率とあなたの所持数、そしてサーバー全体の総所持数を表示します。", inline=False)
        embed.add_field(name="`!ranking`", value="ロール数のトッププレイヤーを表示します。", inline=False)
        embed.add_field(name="`!autorng`", value="6時間、1秒に1回自動でロールします。結果は終了後にDMで送られます。", inline=False)
        embed.add_field(name="`!autostop`", value="実行中のオートRNGを停止し、現在の結果をDMで送られます。", inline=False)
        embed.add_field(name="`!autorngtime`", value="実行中のオートRNGの残り時間を表示します。", inline=False)
        embed.add_field(name="`!ping`", value="ボットの応答速度を測定します。", inline=False)
        embed.add_field(name="`!setup`", value="高確率アイテムの通知チャンネルを設定します。", inline=False)
        embed.add_field(name="`!login`", value="デイリーログインボーナスを獲得します。連続ログインでラックブーストが向上します。", inline=False)
        embed.add_field(name="`!craft [合成したいアイテム名] [個数/all]`", value="素材を消費してよりレアなアイテムを合成します。例: `!craft golden haka 5` または `!craft golden haka all`", inline=False)
        await message.channel.send(embed=embed)
        return

    # --- 管理者用ヘルプコマンド ---
    elif message.content.lower() == "!adminhelp":
        if message.author.id not in ADMIN_IDS:
            await message.channel.send("このコマンドは管理者のみが使用できます。")
            return
        
        embed = discord.Embed(
            title="管理者コマンド一覧",
            description="管理者のみが使用できるコマンドはこちらです。",
            color=discord.Color.red()
        )
        embed.add_field(name="`!boostluck [倍率] [秒数]`", value="全員のLuckを一時的に指定倍率にします。例: `!boostluck 1.5 60` (1.5倍、60秒)", inline=False)
        embed.add_field(name="`!resetall`", value="**警告: 全ユーザーのデータ（ロール数、ラック、インベントリ）をリセットします。**", inline=False)
        await message.channel.send(embed=embed)
        return

    # --- Ping測定コマンド ---
    elif message.content.lower() == "!ping":
        start_time = time.time()
        latency = bot.latency * 1000
        
        msg = await message.channel.send("Pingを測定中...")
        end_time = time.time()
        api_latency = (end_time - start_time) * 1000
        
        embed = discord.Embed(
            title="Pong!",
            description=f"WebSocket Latency: `{latency:.2f}ms`\nAPI Latency: `{api_latency:.2f}ms`",
            color=discord.Color.blue()
        )
        await msg.edit(content="", embed=embed)
        return

    # --- setupコマンド (通知チャンネル設定) ---
    elif message.content.lower() == "!setup":
        if message.author.id not in ADMIN_IDS:
            await message.channel.send("このコマンドは管理者のみが使用できます。")
            return

        bot_settings["notification_channel_id"] = message.channel.id
        save_bot_settings()
        await message.channel.send(f"このチャンネル（`#{message.channel.name}`）を高確率アイテムの通知チャンネルに設定しました。")
        return

    # --- デイリーログインコマンド ---
    elif message.content.lower() == "!login":
        today_utc = datetime.datetime.now(datetime.timezone.utc).date()
        user_daily_data = user_data[user_id]["daily_login"]
        last_login_date_str = user_daily_data["last_login_date"]
        
        last_login_date_obj = None
        if last_login_date_str:
            last_login_date_obj = datetime.datetime.strptime(last_login_date_str, "%Y-%m-%d").date()

        # 今日すでにログイン済みかチェック
        if last_login_date_obj == today_utc:
            await message.channel.send("すでに今日のデイリーログイン報酬は受け取り済みです。")
            return

        # 連続ログインの判定
        is_consecutive = False
        if last_login_date_obj:
            # 前回のログインが昨日だった場合、連続ログイン
            if last_login_date_obj == today_utc - datetime.timedelta(days=1):
                user_daily_data["consecutive_days"] += 1
                is_consecutive = True
            else:
                # 連続ログインが途切れた場合
                user_daily_data["consecutive_days"] = 1
        else:
            # 初回ログイン
            user_daily_data["consecutive_days"] = 1
        
        user_daily_data["last_login_date"] = today_utc.strftime("%Y-%m-%d")

        consecutive_days = user_daily_data["consecutive_days"]
        
        # 連続ログイン日数に応じたラックブースト倍率と時間
        boost_multiplier = 1.0 + (consecutive_days * 0.1)
        boost_duration_minutes = 5 + (consecutive_days - 1) * 1
        
        max_boost_multiplier = 2.0
        max_boost_duration_minutes = 15

        boost_multiplier = min(boost_multiplier, max_boost_multiplier)
        boost_duration_minutes = min(boost_duration_minutes, max_boost_duration_minutes)

        boost_duration_seconds = boost_duration_minutes * 60
        boost_end_time = current_time + datetime.timedelta(seconds=boost_duration_seconds)

        # 古いブーストがあれば元に戻す (BoostLuckコマンドとの競合を避けるため)
        # ただし、デイリーログインでのブーストは排他的に扱うため、ユーザーの現在のluckは一旦リセット
        user_data[user_id]["luck"] = 1.0 # 基本のラックに戻す (既存のブーストはここで上書き)

        # 新しいブーストを適用
        user_data[user_id]["luck"] *= boost_multiplier
        user_data[user_id]["luck"] = round(user_data[user_id]["luck"], 1)

        user_daily_data["active_boost"]["multiplier"] = boost_multiplier
        user_daily_data["active_boost"]["end_time"] = boost_end_time.timestamp()

        save_user_data()

        status_message = ""
        if is_consecutive:
            status_message = f"連続ログイン{consecutive_days}日目！"
        else:
            status_message = f"デイリーログイン成功！"

        await message.channel.send(
            f"{message.author.mention} {status_message}\n"
            f"ラックが一時的に **{boost_multiplier:.1f}倍** になりました！ ({boost_duration_minutes}分間有効)\n"
            f"現在のラック: **{user_data[user_id]['luck']:.1f}**"
        )
        return

    # --- 既存のコマンド ---
    elif message.content.lower() == "!rng":
        # ラックブーストが有効期限切れでないか再チェックし、適用する
        current_time = datetime.datetime.now(datetime.timezone.utc)
        user_boost = user_data[user_id]["daily_login"]["active_boost"]

        if user_boost["end_time"] and current_time > datetime.datetime.fromtimestamp(user_boost["end_time"], tz=datetime.timezone.utc):
            user_data[user_id]["luck"] /= user_boost["multiplier"]
            user_data[user_id]["luck"] = round(user_data[user_id]["luck"], 1)
            user_boost["multiplier"] = 1.0
            user_boost["end_time"] = None
            save_user_data()
            await message.channel.send(f"{message.author.mention} の一時的なラックブーストが終了しました。")

        user_data[user_id]["rolls"] += 1
        user_rolls = user_data[user_id]["rolls"]
        luck = user_data[user_id]["luck"] # 更新されたラック値を取得
        today = datetime.datetime.now().strftime("%B %d, %Y")

        found_item, real_chance_denominator = perform_roll(luck)

        inventory = user_data[user_id]["inventory"]
        inventory[found_item] = inventory.get(found_item, 0) + 1

        embed = discord.Embed(
            title=f"{message.author.name} HAS FOUND {found_item}!!!",
            color=discord.Color.purple()
        )
        embed.add_field(name="CHANCE OF", value=f"1 in {real_chance_denominator:,}", inline=False)
        embed.add_field(name="OBTAIN ON", value=today, inline=False)
        embed.add_field(name="MY ROLL IS", value=f"{user_rolls} Rolls", inline=False)
        embed.add_field(name="My Total Luck", value=f"{luck:.1f} Luck", inline=False)
        await message.channel.send(embed=embed)

        save_user_data()

        # --- 高確率アイテム通知ロジック ---
        # 確率が10万分の1以上のアイテム (分母が100000以上)
        if real_chance_denominator >= 100000: 
            notification_channel_id = bot_settings.get("notification_channel_id")
            if notification_channel_id:
                notification_channel = bot.get_channel(notification_channel_id)
                if notification_channel:
                    # 全ユーザーのアイテム総保持数を計算 (通知に含めるため)
                    total_item_counts = {item: 0 for item in rare_item_chances_denominator.keys()}
                    for uid in user_data:
                        for item, count in user_data[uid]["inventory"].items():
                            if item in total_item_counts:
                                total_item_counts[item] += count
                    
                    total_owned_count = total_item_counts.get(found_item, 0)

                    notification_embed = discord.Embed(
                        title="✨ 超レアアイテムドロップ通知！ ✨",
                        description=f"{message.author.mention} がレアアイテムを獲得しました！",
                        color=discord.Color.gold()
                    )
                    notification_embed.add_field(name="獲得者", value=message.author.mention, inline=False)
                    notification_embed.add_field(name="アイテム", value=found_item, inline=False)
                    notification_embed.add_field(name="確率", value=f"1 in {real_chance_denominator:,}", inline=False)
                    notification_embed.add_field(name="獲得日時", value=datetime.datetime.now(datetime.timezone.utc).strftime("%Y年%m月%d日 %H:%M:%S UTC"), inline=False)
                    notification_embed.add_field(name="サーバー総所持数", value=f"{total_owned_count}個", inline=False)
                    notification_embed.set_footer(text="おめでとうございます！")
                    await notification_channel.send(embed=notification_embed)
                else:
                    print(f"警告: 設定された通知チャンネルID {notification_channel_id} が見つかりません。")
            # else: 通知チャンネルが設定されていない場合は何もしない

    elif message.content.lower() == "!status":
        data = user_data[user_id]
        inventory_str = "\n".join(f"{item}: {count}" for item, count in data["inventory"].items()) or "なし"

        # デイリーログインブースト情報を取得
        boost_info = data["daily_login"]["active_boost"]
        boost_status = "なし"
        if boost_info["end_time"]:
            end_dt = datetime.datetime.fromtimestamp(boost_info["end_time"], tz=datetime.timezone.utc)
            remaining_time = end_dt - datetime.datetime.now(datetime.timezone.utc)
            
            if remaining_time.total_seconds() > 0:
                hours, remainder = divmod(int(remaining_time.total_seconds()), 3600)
                minutes, seconds = divmod(remainder, 60)
                boost_status = f"**{boost_info['multiplier']:.1f}倍** (残り {hours}h {minutes}m {seconds}s)"
            else:
                # 期限切れだがまだラックが戻っていない場合（!rngで更新される）
                boost_status = "期限切れ (次のロールで更新されます)"

        embed = discord.Embed(
            title=f"{message.author.name}'s Status",
            color=discord.Color.blue()
        )
        embed.add_field(name="Total Rolls", value=f"{data['rolls']}", inline=False)
        embed.add_field(name="Luck", value=f"{data['luck']:.1f}", inline=False)
        embed.add_field(name="連続ログイン日数", value=f"{data['daily_login']['consecutive_days']}日", inline=False)
        embed.add_field(name="現在のログインブースト", value=boost_status, inline=False)
        embed.add_field(name="Inventory", value=inventory_str, inline=False)
        await message.channel.send(embed=embed)

    elif message.content.lower() == "!itemlist":
        user_inventory = user_data[user_id]["inventory"]
        
        # 全ユーザーのアイテム総保持数を計算
        total_item_counts = {item: 0 for item in rare_item_chances_denominator.keys()}
        for uid in user_data:
            for item, count in user_data[uid]["inventory"].items():
                if item in total_item_counts:
                    total_item_counts[item] += count

        # アイテムをカテゴリ別に分類
        normal_items = []
        golden_items = []
        rainbow_items = []

        for item_name, chance_denominator in rare_item_chances_denominator.items():
            if item_name.startswith("golden "):
                golden_items.append((item_name, chance_denominator))
            elif item_name.startswith("rainbow "):
                rainbow_items.append((item_name, chance_denominator))
            else:
                normal_items.append((item_name, chance_denominator))
        
        # 各カテゴリのアイテムをレアリティが高い（分母が大きい）順にソート
        normal_items.sort(key=lambda item: item[1], reverse=True)
        golden_items.sort(key=lambda item: item[1], reverse=True)
        rainbow_items.sort(key=lambda item: item[1], reverse=True)

        items_per_page = 20 # 1ページあたりのアイテム数 (Discord Embedのフィールド上限は25なので、少し余裕を持たせる)
        
        # 初期表示はノーマルアイテム
        current_category = "normal"
        current_category_items = normal_items
        
        total_pages = math.ceil(len(current_category_items) / items_per_page)
        if total_pages == 0:
            total_pages = 1 # アイテムがない場合でもページ数は1として扱う

        # 最初のページを生成して送信
        embed = await generate_itemlist_embed(
            message.author.id, 
            0, # 最初のページ
            items_per_page, 
            current_category, 
            current_category_items, 
            total_item_counts
        )
        msg = await message.channel.send(embed=embed)

        # カテゴリ切り替えとページ送りのリアクションを追加
        await msg.add_reaction('🐾') # ノーマル
        await msg.add_reaction('⭐') # ゴールデン (修正済み)
        await msg.add_reaction('🌈') # レインボー
        if total_pages > 1: # 複数ページある場合のみページ送りリアクション
            await msg.add_reaction('◀️')
            await msg.add_reaction('▶️')

        # セッション情報を保存
        pagination_sessions[msg.id] = {
            "current_page": 0,
            "items_per_page": items_per_page,
            "user_id": message.author.id,
            "current_category": current_category,
            "normal_items": normal_items,
            "golden_items": golden_items,
            "rainbow_items": rainbow_items,
            "total_item_counts": total_item_counts
        }

        # ページネーションのタイムアウト処理
        await asyncio.sleep(120)  # 2分後にリアクションを削除
        if msg.id in pagination_sessions: # 削除される前に操作された可能性があるのでチェック
            del pagination_sessions[msg.id]
        try:
            await msg.clear_reactions()
        except discord.Forbidden:
            pass # リアクションを削除する権限がない場合


    elif message.content.lower() == "!ranking":
        if not user_data:
            await message.channel.send("まだ誰も遊んでないよ！")
            return

        active_users = {uid: data for uid, data in user_data.items() if data["rolls"] > 0}

        if not active_users:
            await message.channel.send("まだ誰も遊んでないよ！")
            return

        sorted_users = sorted(active_users.items(), key=lambda x: x[1]["rolls"], reverse=True)
        ranking_text = ""
        for i, (uid, data) in enumerate(sorted_users[:10], start=1):
            user = await bot.fetch_user(int(uid))
            ranking_text += f"{i}. {user.name} - {data['rolls']} Rolls\n"

        embed = discord.Embed(title="Top Rollers", description=ranking_text, color=discord.Color.gold())
        await message.channel.send(embed=embed)

    elif message.content.lower().startswith("!boostluck"):
        if message.author.id not in ADMIN_IDS:
            await message.channel.send("このコマンドは管理者のみが使用できます。")
            return

        try:
            _, multiplier_str, duration_str = message.content.split()
            multiplier = float(multiplier_str)
            duration = int(duration_str)
            if not (0.1 <= multiplier <= 10.0 and 10 <= duration <= 3600):
                await message.channel.send("倍率は0.1～10.0、秒数は10～3600の範囲で指定してください。")
                return
        except ValueError:
            await message.channel.send("使い方: `!boostluck 倍率 秒数` 例: `!boostluck 1.5 60`")
            return

        for uid in user_data:
            user_data[uid]["luck"] *= multiplier
            user_data[uid]["luck"] = round(user_data[uid]["luck"], 1)

        save_user_data()

        await message.channel.send(f"全員のLuckが一時的に **{multiplier}倍** になりました！ ({duration}秒間)")

        await asyncio.sleep(duration)

        for uid in user_data:
            user_data[uid]["luck"] /= multiplier
            user_data[uid]["luck"] = round(user_data[uid]["luck"], 1)

        save_user_data()

        await message.channel.send(f"Luckブーストが終了しました。元に戻しました！")

    elif message.content.lower() == "!autorng":
        if user_id in auto_rng_sessions and auto_rng_sessions[user_id]["task"] and not auto_rng_sessions[user_id]["task"].done():
            await message.channel.send("すでにオートRNGが実行中です！`!autostop` で停止できます。")
            return

        await message.channel.send("オートRNGを開始します。6時間後に結果をDMで送信します。途中で停止する場合は `!autostop` と送信してください。")

        auto_rng_sessions[user_id] = {
            "task": None,
            "found_items_log": [],
            "start_time": datetime.datetime.now()
        }

        async def auto_roll_task():
            user = message.author
            session_data = auto_rng_sessions[user_id]
            start_time = session_data["start_time"]
            found_items_log = session_data["found_items_log"]
            
            max_duration_seconds = 6 * 60 * 60

            try:
                while (datetime.datetime.now() - start_time).total_seconds() < max_duration_seconds:
                    # Auto RNG実行中もラックブーストの期限切れをチェックし適用
                    current_time_loop = datetime.datetime.now(datetime.timezone.utc)
                    user_boost_loop = user_data[user_id]["daily_login"]["active_boost"]

                    if user_boost_loop["end_time"] and current_time_loop > datetime.datetime.fromtimestamp(user_boost_loop["end_time"], tz=datetime.timezone.utc):
                        user_data[user_id]["luck"] /= user_boost_loop["multiplier"]
                        user_data[user_id]["luck"] = round(user_data[user_id]["luck"], 1)
                        user_boost_loop["multiplier"] = 1.0
                        user_boost_loop["end_time"] = None
                        save_user_data() 
                        await user.send(f"あなたのデイリーログインによる一時的なラックブーストが終了しました。")


                    user_data[user_id]["rolls"] += 1
                    current_luck = user_data[user_id]["luck"]

                    found_item, real_chance_denominator = perform_roll(current_luck)

                    user_data[user_id]["inventory"][found_item] = user_data[user_id]["inventory"].get(found_item, 0) + 1
                    found_items_log.append(found_item)
                    
                    save_user_data()

                    # 高確率アイテム通知ロジック (オートRNG中も適用)
                    if real_chance_denominator >= 100000:
                        notification_channel_id = bot_settings.get("notification_channel_id")
                        if notification_channel_id:
                            notification_channel = bot.get_channel(notification_channel_id)
                            if notification_channel:
                                # 全ユーザーのアイテム総保持数を計算 (通知に含めるため)
                                total_item_counts = {item: 0 for item in rare_item_chances_denominator.keys()}
                                for uid in user_data:
                                    for item, count in user_data[uid]["inventory"].items():
                                        if item in total_item_counts:
                                            total_item_counts[item] += count
                                
                                total_owned_count = total_item_counts.get(found_item, 0)

                                notification_embed = discord.Embed(
                                    title="✨ オートRNGで超レアアイテムドロップ！ ✨",
                                    description=f"{user.mention} がオートRNG中にレアアイテムを引きました！",
                                    color=discord.Color.gold()
                                )
                                notification_embed.add_field(name="獲得者", value=user.mention, inline=False)
                                notification_embed.add_field(name="アイテム", value=found_item, inline=False)
                                notification_embed.add_field(name="確率", value=f"1 in {real_chance_denominator:,}", inline=False)
                                notification_embed.add_field(name="獲得日時", value=datetime.datetime.now(datetime.timezone.utc).strftime("%Y年%m月%d日 %H:%M:%S UTC"), inline=False)
                                notification_embed.add_field(name="サーバー総所持数", value=f"{total_owned_count}個", inline=False)
                                notification_embed.set_footer(text="おめでとうございます！")
                                await notification_channel.send(embed=notification_embed)
                            else:
                                print(f"警告: 設定された通知チャンネルID {notification_channel_id} が見つかりません。")
                    await asyncio.sleep(1)
            except asyncio.CancelledError:
                stop_reason = "停止コマンドにより終了"
            else:
                stop_reason = "時間経過により終了"
            finally:
                await send_auto_rng_results(user, found_items_log, user_data[user_id]["rolls"], stop_reason)
                if user_id in auto_rng_sessions:
                    del auto_rng_sessions[user_id]

        auto_rng_sessions[user_id]["task"] = bot.loop.create_task(auto_roll_task())

    elif message.content.lower() == "!autostop":
        if user_id in auto_rng_sessions and auto_rng_sessions[user_id]["task"] and not auto_rng_sessions[user_id]["task"].done():
            auto_rng_sessions[user_id]["task"].cancel()
            await message.channel.send("オートRNGを停止します。まもなく結果をDMで送信します。")
        else:
            await message.channel.send("オートRNGは実行されていません。")

    elif message.content.lower() == "!autorngtime":
        if user_id not in auto_rng_sessions or not auto_rng_sessions[user_id]["task"] or auto_rng_sessions[user_id]["task"].done():
            await message.channel.send("現在、オートRNGは実行されていません。")
            return
        
        session_data = auto_rng_sessions[user_id]
        start_time = session_data["start_time"]
        max_duration_seconds = 6 * 60 * 60

        elapsed_time_seconds = (datetime.datetime.now() - start_time).total_seconds()
        remaining_time_seconds = max_duration_seconds - elapsed_time_seconds

        if remaining_time_seconds <= 0:
            await message.channel.send("オートRNGはもうすぐ終了します、または既に終了しています。")
            return

        remaining_hours = int(remaining_time_seconds // 3600)
        remaining_minutes = int((remaining_time_seconds % 3600) // 60)
        remaining_seconds = int(remaining_time_seconds % 60)

        time_str = ""
        if remaining_hours > 0:
            time_str += f"{remaining_hours}時間"
        if remaining_minutes > 0:
            time_str += f"{remaining_minutes}分"
        time_str += f"{remaining_seconds}秒"

        await message.channel.send(f"オートRNGの残り時間: **{time_str}**")
        return

    # --- アイテム合成コマンド ---
    elif message.content.lower().startswith("!craft"):
        # コマンド部分を除外し、残りの文字列を取得
        # 例: "!craft golden hage uku all" -> "golden hage uku all"
        content_after_command = message.content[len("!craft"):].strip().lower()

        target_item_with_prefix = ""
        craft_amount_str = "1" # デフォルトは1個

        # 文字列の末尾が数字か "all" であるかをチェックして、個数とアイテム名を分離
        # 例: "golden hage uku all" を "golden hage uku" と "all" に分離
        # 例: "golden haka 5" を "golden haka" と "5" に分離
        # 例: "golden haka" (個数なし) は分離せず、target_item_with_prefix = "golden haka", craft_amount_str = "1" のまま
        
        # content_after_command を右から1回だけ空白で分割
        parts = content_after_command.rsplit(' ', 1) 

        if len(parts) == 2:
            # 2つの部分に分かれた場合、2番目の部分が数字または"all"かを確認
            potential_amount_str = parts[1].strip()
            if potential_amount_str.isdigit() or potential_amount_str == "all":
                target_item_with_prefix = parts[0].strip()
                craft_amount_str = potential_amount_str
            else:
                # 2番目の部分が数字でも"all"でもない場合、全体がアイテム名と判断
                target_item_with_prefix = content_after_command
                # craft_amount_str はデフォルトの "1" のまま
        else:
            # 1つの部分しかない場合（個数指定なし）、全体がアイテム名
            target_item_with_prefix = content_after_command
            # craft_amount_str はデフォルトの "1" のまま
            
        # アイテム名が空の場合、エラー
        if not target_item_with_prefix:
            await message.channel.send("合成したいアイテム名を指定してください。例: `!craft golden haka 5`")
            return

        user_inventory = user_data[user_id]["inventory"]

        # ターゲットアイテムが合成レシピに存在するかチェック
        if target_item_with_prefix not in CRAFTING_RECIPES:
            found_hint = False
            for base_item in base_item_chances_denominator.keys():
                # ユーザーが "golden haka" ではなく "haka" のように基本アイテム名を指定した場合のヒント
                if target_item_with_prefix == base_item:
                    await message.channel.send(f"'{base_item}' は合成できません。`golden {base_item}` や `rainbow {base_item}` を合成できます。")
                    found_hint = True
                    break
            if not found_hint:
                await message.channel.send(f"'{target_item_with_prefix}' は合成できません。合成可能なアイテムは`{', '.join(CRAFTING_RECIPES.keys())}`です。")
            return

        recipe = CRAFTING_RECIPES[target_item_with_prefix]
        materials_needed_per_craft = recipe["materials"]
        output_item = list(recipe["output"].keys())[0] # レシピのアウトプットアイテムは一つと仮定

        # --- 合成個数の決定 ---
        desired_craft_amount = 0
        if craft_amount_str.lower() == "all":
            # 持っている素材で何個作れるか計算
            max_possible_crafts = float('inf')
            for material, amount_needed_per_craft in materials_needed_per_craft.items():
                if amount_needed_per_craft > 0: # 0割りを避ける
                    current_material_count = user_inventory.get(material, 0)
                    possible_with_this_material = current_material_count // amount_needed_per_craft
                    max_possible_crafts = min(max_possible_crafts, possible_with_this_material)
                
            desired_craft_amount = max_possible_crafts if max_possible_crafts != float('inf') else 0

        else:
            try:
                desired_craft_amount = int(craft_amount_str)
                if desired_craft_amount <= 0:
                    await message.channel.send("合成する個数は1以上の数字を指定してください。")
                    return
            except ValueError:
                await message.channel.send("合成する個数は数字か `all` で指定してください。例: `!craft golden haka 5` または `!craft golden haka all`")
                return
        
        if desired_craft_amount == 0:
            await message.channel.send(f"'{target_item_with_prefix}' を合成できる素材が足りません。")
            return

        # --- 合成に必要な総素材数の確認 ---
        can_craft = True
        missing_materials = []
        for material, amount_needed_per_craft in materials_needed_per_craft.items():
            total_needed = amount_needed_per_craft * desired_craft_amount
            if user_inventory.get(material, 0) < total_needed:
                can_craft = False
                missing_materials.append(f"{material}が{total_needed - user_inventory.get(material, 0)}個不足")
        
        if not can_craft:
            await message.channel.send(f"素材が足りません: {', '.join(missing_materials)}")
            return
        
        # --- 合成実行 ---
        for material, amount_needed_per_craft in materials_needed_per_craft.items():
            user_inventory[material] -= amount_needed_per_craft * desired_craft_amount
            if user_inventory[material] == 0:
                del user_inventory[material] # 0になったらキーを削除
        
        user_inventory[output_item] = user_inventory.get(output_item, 0) + (1 * desired_craft_amount)
        
        save_user_data()
        await message.channel.send(f"✨ {message.author.mention} は素材を消費して **{output_item}** を {desired_craft_amount}個合成しました！おめでとうございます！")
        return

    # --- 全ユーザーデータリセットコマンド ---
    elif message.content.lower() == "!resetall":
        if message.author.id not in ADMIN_IDS:
            await message.channel.send("このコマンドは管理者のみが使用できます。")
            return

        await message.channel.send("本当に全ユーザーデータをリセットしますか？実行する場合は `!resetall confirm` と送信してください。")

        def check(m):
            return m.author == message.author and m.channel == message.channel and m.content.lower() == "!resetall confirm"

        try:
            await bot.wait_for('message', check=check, timeout=30.0)
        except asyncio.TimeoutError:
            await message.channel.send("確認がタイムアウトしました。リセットはキャンセルされました。")
        else:
            if os.path.exists(USER_DATA_FILE):
                os.remove(USER_DATA_FILE)
            
            load_user_data() 
            await message.channel.send("全ユーザーデータがリセットされました。")
            print("全ユーザーデータがリセットされました。")
        return


bot.run(os.getenv("TOKEN"))