import discord
import random
import datetime
import os
import asyncio
import json
import math
import time

# @@@ 初期化デバッグ: このスクリプトが読み込まれ、実行を開始しました！ @@@

intents = discord.Intents.default()
intents.messages = True
intents.message_content = True  # Message Content Intent を有効にする
intents.reactions = True  # リアクションイベントを有効にする
bot = discord.Client(intents=intents)

USER_DATA_FILE = 'user_data.json'
BOT_SETTINGS_FILE = 'bot_settings.json'
AUTO_RNG_SESSIONS_FILE = 'auto_rng_sessions.json' # 新しいファイルパスを追加
ADMIN_IDS = [929555026612715530, 974264083853492234, 997803924281118801, 950387247985864725] # 950387247985864725 を追加

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
    "みず": 30,
    "激ヤバみず": 10000000000, # 100億分の1
    "ねこぶる": 100000,       # 10万分の1
    "pro bot": 5000           # 5000分の1
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

# --- Luck Potionのレシピ定義 ---
# キーはユーザーが !make コマンドで指定するポーション名
# output のキーは内部的なポーション名 (スペースや特殊文字を避ける)
LUCK_POTION_RECIPES = {
    "rtx4070": {
        "materials": {"rainbow じゃうく": 1},
        "output": {"one_billion_luck_potion": 1}, # 内部的なアイテム名
        "luck_multiplier": 1000000000 # 10億倍
    },
    "ねこぶるpc": {
        "materials": {"rainbow hage uku": 3, "rainbow みず": 3},
        "output": {"ten_thousand_luck_potion": 1}, # 内部的なアイテム名
        "luck_multiplier": 10000 # 1万倍
    }
}

# 内部的なポーション名と倍率のマッピング
LUCK_POTION_EFFECTS = {
    "one_billion_luck_potion": 1000000000,
    "ten_thousand_luck_potion": 10000
}


auto_rng_sessions = {} # グローバル変数として定義
bot_settings = {}
user_data = {} # グローバル変数として定義

# user_dataへのアクセスを同期するためのロック
# on_message以外の場所（例: ステータス更新タスク）からuser_dataにアクセスする際に使用
user_data_lock = asyncio.Lock()

# --- データ保存・ロード関数 ---
def save_user_data():
    """ユーザーデータをJSONファイルに保存する"""
    # on_message内でロックを取得していないため、ここではロック不要
    # ただし、user_data_lockは他の非同期タスク（例: ステータス更新）で使用される
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

def save_auto_rng_sessions():
    """オートRNGセッションデータをJSONファイルに保存する"""
    serializable_sessions = {}
    for user_id, session_data in auto_rng_sessions.items():
        serializable_sessions[user_id] = {
            "found_items_log": session_data["found_items_log"], # ここは辞書型で保存
            "start_time": session_data["start_time"].timestamp(), # datetimeをtimestampに変換
            "max_duration_seconds": session_data["max_duration_seconds"] # durationも保存
        }
    with open(AUTO_RNG_SESSIONS_FILE, 'w', encoding='utf-8') as f:
        json.dump(serializable_sessions, f, ensure_ascii=False, indent=4)
    print("オートRNGセッションデータを保存しました。")

def load_auto_rng_sessions():
    """JSONファイルからオートRNGセッションデータを読み込む"""
    global auto_rng_sessions
    if os.path.exists(AUTO_RNG_SESSIONS_FILE):
        with open(AUTO_RNG_SESSIONS_FILE, 'r', encoding='utf-8') as f:
            try:
                loaded_sessions = json.load(f)
                auto_rng_sessions = {}
                for user_id, session_data in loaded_sessions.items():
                    # タイムゾーン情報を持つdatetimeオブジェクトとしてロード
                    auto_rng_sessions[user_id] = {
                        "task": None, # taskは再起動時に再作成されるのでNone
                        "found_items_log": session_data["found_items_log"], # 辞書型としてロード
                        "start_time": datetime.datetime.fromtimestamp(session_data["start_time"], tz=datetime.timezone.utc), # 修正: UTCタイムゾーンを明示的に設定
                        "max_duration_seconds": session_data["max_duration_seconds"]
                    }
                print("オートRNGセッションデータをロードしました。")
            except json.JSONDecodeError as e:
                print(f"ERROR: auto_rng_sessions.jsonの読み込み中にエラーが発生しました: {e}")
                print("既存のauto_rng_sessions.jsonをバックアップし、新しく空のデータを作成します。")
                if os.path.exists(AUTO_RNG_SESSIONS_FILE):
                    os.rename(AUTO_RNG_SESSIONS_FILE, AUTO_RNG_SESSIONS_FILE + ".bak." + datetime.datetime.now().strftime("%Y%m%d%H%M%S"))
                auto_rng_sessions = {} # エラー時は空のデータで初期化
                save_auto_rng_sessions() # 空のデータを保存
    else:
        auto_rng_sessions = {}
        print("オートRNGセッションデータファイルが見つかりませんでした。")


# --- Botのステータスを更新する非同期タスク ---
async def update_total_rolls_status():
    await bot.wait_until_ready() # Botが完全に準備できるまで待機

    while not bot.is_closed(): # Botが閉じられていない間はループを続ける
        total_rolls = 0
        async with user_data_lock: # user_dataにアクセスする際はロックを取得
            for user_id in user_data:
                # user_data[user_id]が辞書であることを確認し、'rolls'キーが存在するかチェック
                # .get() を使用して、キーが存在しない場合はデフォルト値 0 を返すようにする
                total_rolls += user_data[user_id].get("rolls", 0)


        # Botのステータスを更新
        activity_name = f"{total_rolls:,} 回のロール！" # カンマ区切りで表示
        await bot.change_presence(activity=discord.Game(name=activity_name))
        print(f"Updated bot status to: {activity_name}")

        await asyncio.sleep(20) # 20秒待機

# --- イベントハンドラ ---
@bot.event
async def on_ready():
    print(f'ログイン完了: {bot.user}')
    load_user_data()
    load_bot_settings()
    load_auto_rng_sessions() # オートRNGセッションデータをロード

    print("ユーザーデータをロードしました。")
    print("ボット設定をロードしました。")

    # ロードしたオートRNGセッションのうち、まだ時間が残っているものを再開
    current_time_utc = datetime.datetime.now(datetime.timezone.utc) # UTC時刻を使用
    sessions_to_restart = []
    for user_id in list(auto_rng_sessions.keys()): # ループ中に辞書を変更するため、keys()をリストに変換
        session_data = auto_rng_sessions[user_id]
        # start_timeはload_auto_rng_sessions()でdatetimeオブジェクトに戻されているので、そのまま比較
        elapsed_time = (current_time_utc - session_data["start_time"]).total_seconds()
        remaining_time = session_data["max_duration_seconds"] - elapsed_time

        if remaining_time > 0:
            sessions_to_restart.append(user_id)
            # await user.send()はBotが準備できてからでないと送れない可能性があるので、タスク内でメッセージ送信
        else:
            # 既に終了時間を過ぎているセッションは削除
            del auto_rng_sessions[user_id]
            save_auto_rng_sessions() # 削除を反映して保存

    for user_id in sessions_to_restart:
        # ユーザーオブジェクトを取得してタスクを再開
        try:
            user = await bot.fetch_user(int(user_id))
            auto_rng_sessions[user_id]["task"] = bot.loop.create_task(auto_roll_task(user, is_resumed=True))
            print(f"User {user.name} ({user_id}) のオートRNGセッションを再開しました。")
        except discord.NotFound:
            print(f"警告: ユーザーID {user_id} が見つからないため、オートRNGセッションを再開できませんでした。セッションを削除します。")
            if user_id in auto_rng_sessions:
                del auto_rng_sessions[user_id] # 見つからないユーザーのセッションは削除
            save_auto_rng_sessions()
        except Exception as e:
            print(f"ERROR: オートRNGセッション再開中にエラーが発生しました (ユーザーID: {user_id}): {e}")


    # Botのステータス更新タスクを開始
    bot.loop.create_task(update_total_rolls_status())

# BotがDiscordから切断された際に実行されるイベント
# 予期せぬ切断の場合もデータを保存するようにする
@bot.event
async def on_disconnect():
    print("Bot disconnected. Attempting to save user data and auto RNG sessions...")
    # ロックを取得してデータを安全に保存
    async with user_data_lock:
        save_user_data()
    save_auto_rng_sessions() # オートRNGセッションも保存
    print("User data and auto RNG sessions saved on disconnect.")


async def send_auto_rng_results(user: discord.User, found_items_log: dict, total_rolls: int, stop_reason: str):
    """オートRNGの結果をユーザーにDMで送信する"""
    if not found_items_log:
        await user.send(f"オートRNGが**{stop_reason}**しました。残念ながら何も見つかりませんでした。総ロール数: **{total_rolls}**回")
        return

    result_text = f"オートRNGが**{stop_reason}**しました！\n\n**今回見つかったアイテム:**\n"

    # 辞書形式になったfound_items_logを直接ループ
    for item, count in found_items_log.items():
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
    Luckが高いほど、分母が小さくなる（出やすくなる）が、コモンアイテムには限定的な効果。
    """
    items = list(rare_item_chances_denominator.keys())

    effective_probabilities = {} # 各アイテムの確率 (0.0 ～ 1.0)
    for item in items:
        original_denominator = rare_item_chances_denominator[item]

        # ラック適用後の分母を計算
        # レア度に応じてラックの影響度を変える

        if original_denominator <= 50: # コモンアイテム (うくうく, hage ukuなど)
            # ラック効果を非常に緩やかに適用 (例えば、ラックの0.1乗)
            # ラックが1未満の場合はデバフとしてそのまま適用
            luck_factor = 1.0
            if luck > 1:
                luck_factor = luck ** 0.1 # ラックの0.1乗 (非常に緩やかな効果)
            elif luck < 1:
                luck_factor = luck # デバフとしてそのまま適用 (分母が大きくなる)

            effective_denominator = original_denominator / luck_factor
            # 計算上の値はそのまま保持

        else: # レアアイテム (haka, じゃうくなど)
            # ラック効果を最大限に適用
            effective_denominator = original_denominator / luck
            # 計算上の分母は0割りを避けるために非常に小さい値に制限
            effective_denominator = max(0.0000000001, effective_denominator)

        # 実際の抽選には確率(0～1)を使用する
        effective_probabilities[item] = 1.0 / effective_denominator

        # 確率が1.0を超える場合は1.0に丸める (確定ドロップ)
        if effective_probabilities[item] > 1.0:
            effective_probabilities[item] = 1.0

    # 重みを計算 (確率をそのまま使用)
    weights = list(effective_probabilities.values())

    # 合計重みが0の場合のフォールバック (通常発生しない)
    if sum(weights) == 0:
        weights = [1.0] * len(items)

    chosen_item = random.choices(items, weights=weights, k=1)[0]

    # ★★★ 確率の表示: 小数点以下を切り捨て (floor) ★★★
    # 表示用には、実質的な分母を計算し、1未満の場合は1と表示するロジックにする
    display_denominator = 1.0 / effective_probabilities[chosen_item]
    
    # 計算上の分母が1未満の場合、表示上は1 in 1 とする
    if display_denominator < 1.0:
        display_denominator = 1 # 1未満なら1とする
    else:
        # 小数点以下を切り捨て
        display_denominator = math.floor(display_denominator)

    # return chosen_item, display_denominator (ラック適用後の表示分母), original_denominator (元のアイテムの基本分母)
    return chosen_item, display_denominator, rare_item_chances_denominator[chosen_item]

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
    # on_messageから呼び出される際、既にuser_data_lockは取得済みのはず
    # ここでさらにロックを取得しようとするとデッドロックまたはブロッキングの原因になるため、削除
    # async with user_data_lock: # <<<< この行を削除
    user_inventory = user_data[str(user_id)]["inventory"] # <<<< ロックなしでアクセス

    print(f"DEBUG: generate_itemlist_embed: user_inventory retrieved. User ID: {user_id}")

    start_index = page_num * items_per_page
    end_index = start_index + items_per_page
    items_to_display = category_items[start_index:end_index]
    print(f"DEBUG: generate_itemlist_embed: Items to display count: {len(items_to_display)}")

    total_pages = math.ceil(len(category_items) / items_per_page)
    if total_pages == 0: # アイテムがない場合の表示
        total_pages = 1
    print(f"DEBUG: generate_itemlist_embed: Total pages: {total_pages}, Current page: {page_num}")

    embed_title = ""
    if category_name == "normal":
        embed_title = f"ノーマルアイテムリスト (ページ {page_num + 1}/{total_pages})"
    elif category_name == "golden":
        embed_title = f"ゴールデンアイテムリスト (ページ {page_num + 1}/{total_pages})"
    elif category_name == "rainbow":
        embed_title = f"レインボーアイテムリスト (ページ {page_num + 1}/{total_pages})"
    print(f"DEBUG: generate_itemlist_embed: Embed title: {embed_title}")

    embed = discord.Embed(
        title=embed_title,
        description="全アイテムの確率とあなたの所持数、そしてサーバー全体の総所持数です。",
        color=discord.Color.orange()
    )

    if not items_to_display:
        print("DEBUG: generate_itemlist_embed: No items to display in this category.")
        embed.add_field(name="情報なし", value="このカテゴリにはアイテムがありません。", inline=False)
    else:
        for item_name, chance_denominator in items_to_display:
            display_chance = f"1 in {chance_denominator:,}"
            owned_count = user_inventory.get(item_name, 0)
            total_owned_count = total_item_counts.get(item_name, 0)
            embed.add_field(name=item_name, value=f"確率: {display_chance}\nあなたの所持数: {owned_count}個\nサーバー総所持数: {total_owned_count}個", inline=True)
            print(f"DEBUG: generate_itemlist_embed: Added field for item: {item_name}")

    embed.set_footer(text=f"ページ {page_num + 1}/{total_pages} | レアリティ順")
    print("DEBUG: generate_itemlist_embed: Embed footer set. Returning embed.")
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
        # session["user_id"] をintに変換して比較する
        if user.id != int(session["user_id"]):
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
        elif str(reaction.emoji) == '⭐':
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
    # デバッグ: on_messageが呼び出されたことを確認
    print(f"DEBUG: on_message called! Author: {message.author.name}, Content: '{message.content}'")
    # 生のメッセージ内容とその型、長さを表示
    print(f"DEBUG: Raw message content (type/len): {type(message.content)}, {len(message.content)}")
    # 各文字のUnicodeコードポイントを表示 (隠れた文字がないか確認用)
    print(f"DEBUG: Raw message content (unicode codepoints): {[ord(c) for c in message.content]}")


    global user_data
    global auto_rng_sessions
    if message.author.bot:
        # UnbelievaBoatのような他のボットからの空のメッセージは無視
        if message.author.name == "UnbelievaBoat" and message.content.strip() == "":
            print(f"DEBUG: Ignoring empty message from bot: {message.author.name}")
            return # UnbelievaBoatからの空のメッセージは無視
        # それ以外のボットからのメッセージも基本的には無視
        print(f"DEBUG: Ignoring message from another bot: {message.author.name} (Content: '{message.content}')")
        return

    user_id = str(message.author.id)
    # メッセージ内容の前後の空白を除去し、小文字に変換
    command_content = message.content.lower().strip()
    print(f"DEBUG: Processed command_content: '{command_content}' (Length: {len(command_content)})")
    # 処理後のコマンド内容のUnicodeコードポイントも表示
    print(f"DEBUG: Processed command_content (unicode codepoints): {[ord(c) for c in command_content]}")


    try:
        async with user_data_lock: # user_dataの読み書き全体をロックで保護
            # ユーザーデータがなければ初期化
            if user_id not in user_data:
                print(f"DEBUG: Initializing user data for {user_id}")
                user_data[user_id] = {
                    "rolls": 0,
                    "luck": 1.0,
                    "inventory": {},
                    "luck_potions": {},
                    "active_luck_potion_uses": {},
                    "daily_login": {
                        "last_login_date": None,
                        "consecutive_days": 0,
                        "active_boost": {
                            "multiplier": 1.0,
                            "end_time": None
                        }
                    },
                    "admin_boost": { # 新規ユーザーの初期化時にadmin_boostを追加
                        "multiplier": 1.0,
                        "end_time": None
                    }
                }
                save_user_data()

            # 既存のユーザーデータに不足があれば初期値を追加（互換性維持のため）
            if "daily_login" not in user_data[user_id]:
                print(f"DEBUG: Adding 'daily_login' to user data for {user_id}")
                user_data[user_id]["daily_login"] = {
                    "last_login_date": None,
                    "consecutive_days": 0,
                    "active_boost": {
                        "multiplier": 1.0,
                        "end_time": None
                    }
                }
                save_user_data()

            if "luck_potions" not in user_data[user_id]:
                print(f"DEBUG: Adding 'luck_potions' to user data for {user_id}")
                user_data[user_id]["luck_potions"] = {}
                save_user_data()

            # 新しいフィールド active_luck_potion_uses の追加 (既存ユーザー向け)
            if "active_luck_potion_uses" not in user_data[user_id]:
                print(f"DEBUG: Adding 'active_luck_potion_uses' to user data for {user_id}")
                user_data[user_id]["active_luck_potion_uses"] = {}
                save_user_data()

            # admin_boost がない既存ユーザーのために追加
            if "admin_boost" not in user_data[user_id]:
                print(f"DEBUG: Adding 'admin_boost' to existing user data for {user_id}")
                user_data[user_id]["admin_boost"] = {
                    "multiplier": 1.0,
                    "end_time": None
                }
                save_user_data()


        # --- ラックブーストの適用と期限切れチェック ---
        current_time = datetime.datetime.now(datetime.timezone.utc)
        
        async with user_data_lock: # user_dataの読み書きをロックで保護
            user_boost = user_data[user_id]["daily_login"]["active_boost"]

            # ブーストが設定されており、かつ終了時刻を過ぎている場合
            if user_boost["end_time"] and current_time > datetime.datetime.fromtimestamp(user_boost["end_time"], tz=datetime.timezone.utc):
                # Luckはここで元に戻さない。perform_rollで都度計算される
                user_boost["multiplier"] = 1.0
                user_boost["end_time"] = None
                save_user_data()
                try:
                    await message.channel.send(f"{message.author.mention} の一時的なラックブーストが終了しました。")
                except Exception as e:
                    print(f"WARNING: Could not send daily boost expired message for {message.author.name}: {e}")
            
            # 管理者ブーストの期限切れチェックとリセット (もしあれば)
            admin_boost_info = user_data[user_id].get("admin_boost", {"multiplier": 1.0, "end_time": None})
            if admin_boost_info["end_time"] and current_time > datetime.datetime.fromtimestamp(admin_boost_info["end_time"], tz=datetime.timezone.utc):
                user_data[user_id]["luck"] = 1.0 # 基本ラックを1.0に戻す
                user_data[user_id]["admin_boost"]["multiplier"] = 1.0
                user_data[user_id]["admin_boost"]["end_time"] = None
                save_user_data()
                try:
                    await message.channel.send(f"{message.author.mention} の管理者ラックブーストが終了し、元のラックに戻りました。")
                except Exception as e:
                    print(f"WARNING: Could not send admin boost expired message for {message.author.name}: {e}")


            # 現在のラック値を取得 (ブーストが終了していても、まだ反映されていない場合があるので念のためここで取得)
            user_luck = user_data[user_id]["luck"]


        # --- ヘルプコマンド ---
        if command_content == "!help":
            print("DEBUG: Entering !help command block.")
            try:
                embed = discord.Embed(
                    title="コマンド一覧",
                    description="このボットで使えるコマンドはこちらです。",
                    color=discord.Color.green()
                )
                embed.add_field(name="**!rng**", value="ランダムアイテムをロールします。", inline=False)
                embed.add_field(name="**!status**", value="あなたの現在のロール数、ラック、インベントリを表示します。", inline=False)
                embed.add_field(name="**!itemlist**", value="全アイテムの確率とあなたの所持数、そしてサーバー全体の総所持数を表示します。", inline=False)
                embed.add_field(name="**!ranking**", value="ロール数のトッププレイヤーを表示します。", inline=False)
                embed.add_field(name="**!autorng**", value="6時間、1秒に1回自動でロールします。結果は終了後にDMで送られます。", inline=False)
                embed.add_field(name="**!autostop**", value="実行中のオートRNGを停止し、現在の結果をDMで送られます。", inline=False)
                embed.add_field(name="**!autorngtime**", value="実行中のオートRNGの残り時間を表示します。", inline=False)
                embed.add_field(name="**!ping**", value="ボットの応答速度を測定します。", inline=False)
                embed.add_field(name="**!setup**", value="高確率アイテムの通知チャンネルを設定します。", inline=False)
                embed.add_field(name="**!login**", value="デイリーログインボーナスを獲得します。連続ログインでラックブーストが向上します。", inline=False)
                embed.add_field(name="**!craft [合成したいアイテム名] [個数/all]**", value="素材を消費してよりレアなアイテムを合成します。例: `!craft golden haka 5` または `!craft golden haka all`", inline=False)
                embed.add_field(name="**!make [作成したいポーション名] [個数/all]**", value="素材を消費してLuck Potionを生成します。例: `!make rtx4070 1`", inline=False)
                embed.add_field(name="**!use [使用したいポーション名] [個数/all]**", value="Luck Potionを使用キューに追加し、次のロールから効果を適用します。例: `!use rtx4070 1`", inline=False)
                embed.add_field(name="**!recipe**", value="Luck Potionの作成レシピを表示します。", inline=False)

                print("DEBUG: Attempting to send !help embed.")
                await message.channel.send(embed=embed)
                print("DEBUG: !help embed sent.")
            except Exception as e:
                print(f"ERROR: Failed to send !help embed or during processing: {e}")
                import traceback
                traceback.print_exc()
            return

        # --- 管理者用ヘルプコマンド ---
        elif command_content == "!adminhelp":
            print("DEBUG: Entering !adminhelp command block.")
            if message.author.id not in ADMIN_IDS:
                await message.channel.send("このコマンドは管理者のみが使用できます。")
                return
            try:
                embed = discord.Embed(
                    title="管理者コマンド一覧",
                    description="管理者のみが使用できるコマンドはこちらです。",
                    color=discord.Color.red()
                )
                embed.add_field(name="**!boostluck [倍率] [秒数]**", value="全員のLuckを一時的に指定倍率にします。例: `!boostluck 1.5 60` (1.5倍、60秒)", inline=False)
                embed.add_field(name="**!resetall**", value="**警告: 全ユーザーのデータ（ロール数、ラック、インベントリ）をリセットします。**", inline=False)
                embed.add_field(name="**!adminautorng**", value="現在実行中の全ユーザーのオートRNG状況を表示します。", inline=False)
                embed.add_field(name="**!giveautorng [user mention or ID / all]**", value="指定したユーザーまたは全員のオートRNGを開始します。例: `!giveautorng @ユーザー名`, `!giveautorng 123456789012345678`, `!giveautorng all`", inline=False) # 説明を更新
                embed.add_field(name="**!delete [user mention or ID / all]**", value="指定したユーザーまたは全員のデータを削除します。**回復不能な操作です！**", inline=False)
                print("DEBUG: Attempting to send !adminhelp embed.")
                await message.channel.send(embed=embed)
                print("DEBUG: !adminhelp embed sent.")
            except Exception as e:
                print(f"ERROR: Failed to send !adminhelp embed or during processing: {e}")
                import traceback
                traceback.print_exc()
            return

        # --- Ping測定コマンド ---
        elif command_content == "!ping":
            print("DEBUG: Entering !ping command block.")
            try:
                start_time = time.time()
                latency = bot.latency * 1000

                msg = await message.channel.send("Pingを測定中...")
                end_time = time.time()
                api_latency = (end_time - start_time) * 1000

                embed = discord.Embed(
                    title="Ping結果",
                    description=f"WebSocket Latency: `{latency:.2f}ms`\nAPI Latency: `{api_latency:.2f}ms`",
                    color=discord.Color.blue()
                )
                print("DEBUG: Attempting to edit Ping message with embed.")
                await msg.edit(content="", embed=embed)
                print("DEBUG: Ping message edited.")
            except Exception as e:
                print(f"ERROR: Failed to send/edit !ping message or during processing: {e}")
                import traceback
                traceback.print_exc()
            return

        # --- setupコマンド (通知チャンネル設定) ---
        elif command_content == "!setup":
            print("DEBUG: Entering !setup command block.")
            if message.author.id not in ADMIN_IDS:
                await message.channel.send("このコマンドは管理者のみが使用できます。")
                return
            try:
                bot_settings["notification_channel_id"] = message.channel.id
                save_bot_settings()
                print("DEBUG: Attempting to send !setup confirmation message.")
                await message.channel.send(f"このチャンネル（`#{message.channel.name}`）を高確率アイテムの通知チャンネルに設定しました。")
                print("DEBUG: !setup confirmation message sent.")
            except Exception as e:
                print(f"ERROR: Failed to send !setup confirmation message or during processing: {e}")
                import traceback
                traceback.print_exc()
            return

        # --- デイリーログインコマンド ---
        elif command_content == "!login":
            print("DEBUG: Entering !login command block.")
            try:
                today_utc = datetime.datetime.now(datetime.timezone.utc).date()
                async with user_data_lock: # user_dataの読み書きをロックで保護
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

                    # デイリーログインのブースト情報を更新
                    user_daily_data["active_boost"]["multiplier"] = boost_multiplier
                    user_daily_data["active_boost"]["end_time"] = boost_end_time.timestamp()

                    # user_dataの'luck'は基本ラック値 (1.0) のままにしておく。
                    # 実際の計算は `perform_roll` に渡す前に動的に行われる。
                    # ただし、表示のために一度計算しておく
                    display_luck = 1.0 * boost_multiplier # デイリーログインブーストのみを考慮したラック

                    save_user_data()

                status_message = ""
                if is_consecutive:
                    status_message = f"**連続ログイン{consecutive_days}日目！**"
                else:
                    status_message = f"**デイリーログイン成功！**"

                print("DEBUG: Attempting to send !login confirmation message.")
                await message.channel.send(
                    f"{message.author.mention} {status_message}\n"
                    f"ラックが一時的に **{boost_multiplier:.1f}倍** になりました！ ({boost_duration_minutes}分間有効)\n"
                    f"現在のラック: **{display_luck:.1f}** (基本ラック x デイリーログインブースト)"
                )
                print("DEBUG: !login confirmation message sent.")
            except Exception as e:
                print(f"ERROR: Failed to send !login message or during processing: {e}")
                import traceback
                traceback.print_exc()
            return

        # --- RNGコマンド ---
        elif command_content == "!rng":
            print("DEBUG: Entering !rng command block.")
            try:
                async with user_data_lock: # user_dataの読み書きをロックで保護
                    # ユーザーの基本ラック (通常は1.0)
                    current_base_luck = user_data[user_id]["luck"]

                    # デイリーログインブーストの適用
                    user_boost = user_data[user_id]["daily_login"]["active_boost"]
                    if user_boost["end_time"] and datetime.datetime.now(datetime.timezone.utc) < datetime.datetime.fromtimestamp(user_boost["end_time"], tz=datetime.timezone.utc):
                        current_base_luck *= user_boost["multiplier"]

                    # 管理者ブーストの適用
                    admin_boost_info = user_data[user_id].get("admin_boost", {"multiplier": 1.0, "end_time": None})
                    if admin_boost_info["end_time"] and current_time < datetime.datetime.fromtimestamp(admin_boost_info["end_time"], tz=datetime.timezone.utc):
                        current_base_luck *= admin_boost_info["multiplier"]

                    # Luck Potionの適用ロジック (active_luck_potion_usesから消費)
                    applied_potion_multiplier = 1.0
                    applied_potion_display_name = None

                    active_uses = user_data[user_id]["active_luck_potion_uses"]

                    # 最も高い倍率のポーションを検索し、1回分消費
                    highest_multiplier = 1.0
                    best_potion_internal_name = None

                    # LUCK_POTION_EFFECTSを倍率の降順でソートして探索
                    sorted_potions_by_multiplier = sorted(LUCK_POTION_EFFECTS.items(), key=lambda item: item[1], reverse=True)

                    for internal_name, multiplier_value in sorted_potions_by_multiplier:
                        if active_uses.get(internal_name, 0) > 0:
                            highest_multiplier = multiplier_value
                            best_potion_internal_name = internal_name
                            break # 最も高い倍率のポーションを見つけたらループ終了

                    if best_potion_internal_name:
                        applied_potion_multiplier = highest_multiplier
                        current_luck_for_roll = current_base_luck * applied_potion_multiplier # ポーション効果をここで適用

                        # 使用回数を1減らす
                        active_uses[best_potion_internal_name] -= 1
                        if active_uses[best_potion_internal_name] <= 0:
                            del active_uses[best_potion_internal_name] # 残り回数が0になったら削除

                        # ポーションの表示名を取得
                        for recipe_name, recipe_data in LUCK_POTION_RECIPES.items():
                            if list(recipe_data["output"].keys())[0] == best_potion_internal_name:
                                applied_potion_display_name = recipe_name
                                break

                        print(f"DEBUG: {message.author.mention} used {applied_potion_display_name}.")
                        await message.channel.send(f"{message.author.mention} は **{applied_potion_display_name}** を使用しました！今回のロールのラックは **{current_luck_for_roll:.1f}倍** になります！")
                    else:
                        current_luck_for_roll = current_base_luck # ポーションがなければ基本ラック

                    user_data[user_id]["rolls"] += 1
                    user_rolls = user_data[user_id]["rolls"]
                    today = datetime.datetime.now().strftime("%B %d, %Y")

                    chosen_item, luck_applied_denominator, original_denominator = perform_roll(current_luck_for_roll) # 修正: perform_rollが3つの値を返す
                    # ★★★ ラック適用時の表示上の確率は元のまま ★★★
                    display_chance_for_user = f"1 in {original_denominator:,}" # 元の分母を表示


                    inventory = user_data[user_id]["inventory"]
                    inventory[chosen_item] = inventory.get(chosen_item, 0) + 1

                    embed = discord.Embed(
                        title=f"{message.author.name} が {chosen_item} を見つけました!!!",
                        color=discord.Color.purple()
                    )
                    embed.add_field(name="出現確率", value=display_chance_for_user, inline=False) # 表示は元の確率
                    embed.add_field(name="獲得日", value=today, inline=False)
                    embed.add_field(name="総ロール数", value=f"{user_rolls} 回", inline=False)
                    embed.add_field(name="あなたの合計ラック (ポーション適用後)", value=f"{current_luck_for_roll:.1f} Luck", inline=False)
                    
                    print("DEBUG: Attempting to send !rng embed.")
                    await message.channel.send(embed=embed)
                    print("DEBUG: !rng embed sent.")

                    save_user_data() # ポーション使用後の状態もここで保存

                    # --- 高確率アイテム通知ロジック ---
                    # 通知は元の分母で判断 (例: 10万分の1以上のアイテム)
                    if original_denominator >= 100000: # ★★★ 通知判断は元の分母で ★★★
                        notification_channel_id = bot_settings.get("notification_channel_id")
                        if notification_channel_id:
                            notification_channel = bot.get_channel(notification_channel_id)
                            if notification_channel:
                                total_item_counts = {item: 0 for item in rare_item_chances_denominator.keys()}
                                for uid in user_data: # ロックされたuser_dataを安全に読み取る
                                    for item, count in user_data[uid]["inventory"].items():
                                        if item in total_item_counts:
                                            total_item_counts[item] += count

                                total_owned_count = total_item_counts.get(chosen_item, 0)

                                notification_embed = discord.Embed(
                                    title="レアアイテムドロップ通知！",
                                    description=f"{message.author.mention} がレアアイテムを獲得しました！",
                                    color=discord.Color.gold()
                                )
                                notification_embed.add_field(name="獲得者", value=message.author.mention, inline=False)
                                notification_embed.add_field(name="アイテム", value=chosen_item, inline=False)
                                notification_embed.add_field(name="確率", value=display_chance_for_user, inline=False) # 表示は元の確率
                                notification_embed.add_field(name="獲得日時", value=datetime.datetime.now(datetime.timezone.utc).strftime("%Y年%m月%d日 %H:%M:%S UTC"), inline=False)
                                notification_embed.add_field(name="サーバー総所持数", value=f"{total_owned_count}個", inline=False)
                                notification_embed.set_footer(text="おめでとうございます！")
                                print("DEBUG: Attempting to send notification embed.")
                                await notification_channel.send(embed=notification_embed)
                                print("DEBUG: Notification embed sent.")
                            else:
                                print(f"WARNING: Configured notification channel ID {notification_channel_id} not found.")
                    # else: 通知チャンネルが設定されていない場合は何もしない
            except Exception as e:
                print(f"ERROR: Failed to process !rng command or send embed: {e}")
                import traceback
                traceback.print_exc()
        elif command_content == "!status":
            print(f"DEBUG: Entering !status command block for user: {user_id}")
            try:
                async with user_data_lock: # user_dataの読み取りをロックで保護
                    # デバッグプリントを追加して、user_data[user_id] の中身を確認
                    print(f"DEBUG: user_data content for {user_id}: {user_data.get(user_id)}")
                    data = user_data[user_id]
                    
                    # ★★★ インベントリをレアリティ順にソートして表示 ★★★
                    inventory_items_with_chances = []
                    for item_name, count in data["inventory"].items():
                        # rare_item_chances_denominator にアイテムが存在するか確認
                        if item_name in rare_item_chances_denominator:
                            chance = rare_item_chances_denominator[item_name]
                            inventory_items_with_chances.append((item_name, count, chance))
                        else:
                            # もし確率リストにないアイテムがあれば、デフォルトの確率（非常に高いなど）を設定するか、無視
                            print(f"WARNING: Item '{item_name}' not found in rare_item_chances_denominator. Skipping for status display.")
                            inventory_items_with_chances.append((item_name, count, 0)) # 確率0で最後尾にするなど

                    # 確率（分母）が大きい順（出にくい順）にソート
                    inventory_items_with_chances.sort(key=lambda x: x[2], reverse=True)

                    inventory_str_lines = []
                    for item_name, count, chance in inventory_items_with_chances:
                        if chance > 0:
                            inventory_str_lines.append(f"{item_name}: {count}個 (1 in {chance:,})")
                        else:
                            # 確率が0のアイテムは「不明な確率」として表示
                            inventory_str_lines.append(f"{item_name}: {count}個 (確率不明)")

                    inventory_str = "\n".join(inventory_str_lines) or "なし"
                    # ★★★ インベントリ表示修正ここまで ★★★


                    # Luck Potionの表示 (インベントリ)
                    luck_potions_str = ""
                    if data["luck_potions"]:
                        for potion_internal_name, count in data["luck_potions"].items():
                            display_name = ""
                            for recipe_name, recipe_data in LUCK_POTION_RECIPES.items():
                                if list(recipe_data["output"].keys())[0] == potion_internal_name:
                                    display_name = recipe_name
                                    break
                            if display_name:
                                luck_potions_str += f"- {display_name}: {count}個\n"
                        if not luck_potions_str:
                            luck_potions_str = "なし"
                    else:
                        luck_potions_str = "なし"

                    # 使用待ちLuck Potionの表示
                    active_potions_str = ""
                    if data["active_luck_potion_uses"]:
                        for internal_name, count in data["active_luck_potion_uses"].items():
                            display_name = ""
                            for recipe_name, recipe_data in LUCK_POTION_RECIPES.items():
                                if list(recipe_data["output"].keys())[0] == internal_name:
                                    display_name = recipe_name
                                    break
                            if display_name:
                                active_potions_str += f"- {display_name}: 残り{count}回\n"
                        if not active_potions_str:
                            active_potions_str = "なし"
                    else:
                        active_potions_str = "なし"

                    # デイリーログインブースト情報を取得
                    boost_info = data["daily_login"]["active_boost"]
                    boost_status = "なし"
                    current_luck_for_display = data["luck"] # 基本ラック (通常1.0)
                    if boost_info["end_time"]:
                        end_dt = datetime.datetime.fromtimestamp(boost_info["end_time"], tz=datetime.timezone.utc)
                        remaining_time = end_dt - datetime.datetime.now(datetime.timezone.utc)
                        if remaining_time.total_seconds() > 0:
                            hours, remainder = divmod(int(remaining_time.total_seconds()), 3600)
                            minutes, seconds = divmod(remainder, 60)
                            boost_status = f"**{boost_info['multiplier']:.1f}倍** (残り {hours}h {minutes}m {seconds}s)"
                            current_luck_for_display *= boost_info["multiplier"] # 表示ラックにデイリーログインブーストを乗算
                        else:
                            boost_status = "期限切れ"
                    
                    # 管理者ブーストの表示
                    admin_boost_info = data["admin_boost"]
                    admin_boost_status = "なし"
                    if admin_boost_info["end_time"]:
                        admin_end_dt = datetime.datetime.fromtimestamp(admin_boost_info["end_time"], tz=datetime.timezone.utc)
                        admin_remaining_time = admin_end_dt - datetime.datetime.now(datetime.timezone.utc)
                        if admin_remaining_time.total_seconds() > 0:
                            admin_hours, admin_remainder = divmod(int(admin_remaining_time.total_seconds()), 3600)
                            admin_minutes, admin_seconds = divmod(admin_remainder, 60)
                            admin_boost_status = f"**{admin_boost_info['multiplier']:.1f}倍** (残り {admin_hours}h {admin_minutes}m {admin_seconds}s)"
                            current_luck_for_display *= admin_boost_info["multiplier"] # 表示ラックに管理者ブーストを乗算
                        else:
                            admin_boost_status = "期限切れ"

                    embed = discord.Embed(
                        title=f"{message.author.name} のステータス",
                        color=discord.Color.blue()
                    )
                    embed.add_field(name="**総ロール数**", value=f"{data['rolls']}", inline=False)
                    embed.add_field(name="**ラック**", value=f"{current_luck_for_display:.1f}", inline=False)
                    embed.add_field(name="**連続ログイン日数**", value=f"{data['daily_login']['consecutive_days']}日", inline=False)
                    embed.add_field(name="**現在のログインブースト**", value=boost_status, inline=False)
                    embed.add_field(name="**現在の管理者ブースト**", value=admin_boost_status, inline=False) # 管理者ブーストの表示を追加
                    embed.add_field(name="**アイテムインベントリ**", value=inventory_str, inline=False)
                    embed.add_field(name="**Luck Potionインベントリ**", value=luck_potions_str, inline=False)
                    embed.add_field(name="**使用待ちLuck Potion**", value=active_potions_str, inline=False)
                    
                    print("DEBUG: Attempting to send !status embed.")
                    await message.channel.send(embed=embed)
                    print("DEBUG: !status embed sent.")
            except Exception as e:
                print(f"ERROR: Failed to process !status command or send embed: {e}")
                import traceback
                traceback.print_exc()

        elif command_content == "!itemlist":
            print(f"DEBUG: Entering !itemlist command block for user: {user_id}")
            try:
                # user_dataへのアクセスはon_messageのasync with user_data_lockで保護されているため、
                # generate_itemlist_embed内でのロックは不要（削除済み）
                # デバッグプリントを追加して、user_data[user_id] の中身を確認
                print(f"DEBUG: user_data content for {user_id}: {user_data.get(user_id)}")
                # user_data[user_id] が期待される辞書構造を持っているか確認
                if not isinstance(user_data.get(user_id), dict) or "inventory" not in user_data[user_id]:
                    print(f"ERROR: User data for {user_id} is malformed or missing 'inventory' key. Data: {user_data.get(user_id)}")
                    await message.channel.send("ユーザーデータに問題があるため、アイテムリストを表示できませんでした。")
                    return # これ以上処理を進めない

                user_inventory = user_data[user_id]["inventory"]

                # 全ユーザーのアイテム総保持数を計算
                total_item_counts = {item: 0 for item in rare_item_chances_denominator.keys()}
                # ここで再度 user_data_lock を取得して for uid in user_data: ループを囲む
                async with user_data_lock: # <<<< ここでロックを追加
                    for uid in user_data:
                        if isinstance(user_data[uid], dict) and "inventory" in user_data[uid]:
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

                items_per_page = 10 # 1ページあたりのアイテム数

                # 最初のページ（ノーマルアイテムリスト）を生成
                print("DEBUG: Calling generate_itemlist_embed.")
                initial_embed = await generate_itemlist_embed(user_id, 0, items_per_page, "normal", normal_items, total_item_counts)
                
                print("DEBUG: Attempting to send !itemlist embed.")
                # メッセージ送信の成功/失敗をデバッグするために変数に格納
                message_sent_obj = None
                try:
                    message_sent_obj = await message.channel.send(embed=initial_embed)
                    print(f"DEBUG: !itemlist embed sent successfully. Message ID: {message_sent_obj.id}")
                except discord.Forbidden:
                    print(f"ERROR: Bot lacks permissions to send messages in channel {message.channel.id} for !itemlist.")
                    await message.author.send(f"申し訳ありません、このチャンネルでアイテムリストを送信する権限がありません。\n"
                                              f"チャンネル名: `{message.channel.name}`, サーバー名: `{message.guild.name if message.guild else 'DM'}`")
                    return
                except discord.HTTPException as http_e:
                    print(f"ERROR: HTTPException during !itemlist embed send: {http_e.status} {http_e.text}")
                    await message.channel.send("アイテムリストの送信中にDiscord APIエラーが発生しました。時間を置いて再度お試しください。")
                    return
                except Exception as embed_e:
                    print(f"ERROR: Unexpected error while sending !itemlist embed: {embed_e}")
                    import traceback
                    traceback.print_exc()
                    await message.channel.send("アイテムリストの送信中に予期せぬエラーが発生しました。")
                    return

                # message_sent_obj が None の場合は処理を中断
                if message_sent_obj is None:
                    print("DEBUG: Message_sent_obj is None, stopping !itemlist processing.")
                    return


                # ページネーションセッションを保存
                pagination_sessions[message_sent_obj.id] = {
                    "user_id": user_id,
                    "current_page": 0,
                    "items_per_page": items_per_page,
                    "current_category": "normal",
                    "normal_items": normal_items,
                    "golden_items": golden_items,
                    "rainbow_items": rainbow_items,
                    "total_item_counts": total_item_counts
                }
                print("DEBUG: Pagination session saved.")

                # リアクションを追加
                print("DEBUG: Attempting to add reactions.")
                try:
                    await message_sent_obj.add_reaction('◀️')
                    await message_sent_obj.add_reaction('▶️')
                    await message_sent_obj.add_reaction('🐾') # ノーマルアイテム
                    await message_sent_obj.add_reaction('⭐') # ゴールデンアイテム
                    await message_sent_obj.add_reaction('🌈') # レインボーアイテム
                    print("DEBUG: Reactions added successfully.")
                except discord.Forbidden:
                    print(f"ERROR: Bot lacks permissions to add reactions in channel {message.channel.id} for !itemlist.")
                    # リアクション追加権限がない場合はユーザーに通知しない（よくあるため）
                except discord.HTTPException as http_e:
                    print(f"ERROR: HTTPException during !itemlist reaction add: {http_e.status} {http_e.text}")
                except Exception as react_e:
                    print(f"ERROR: Unexpected error while adding reactions for !itemlist: {react_e}")
                    import traceback
                    traceback.print_exc()

            except Exception as e:
                print(f"ERROR: Failed to process !itemlist command or send embed/reactions (outer try): {e}")
                import traceback
                traceback.print_exc()


        elif command_content == "!ranking":
            print("DEBUG: Entering !ranking command block.")
            try:
                # ロール数でソート
                async with user_data_lock: # user_dataの読み取りをロックで保護
                    sorted_users = sorted(user_data.items(), key=lambda item: item[1].get("rolls", 0), reverse=True)

                embed = discord.Embed(
                    title="ロール数ランキング",
                    description="最も多くロールしたユーザーのトップ10です。",
                    color=discord.Color.gold()
                )

                rank = 1
                for user_id_str, data in sorted_users[:10]:
                    try:
                        user = await bot.fetch_user(int(user_id_str))
                        embed.add_field(name=f"**#{rank} {user.name}**", value=f"ロール数: {data.get('rolls', 0)}", inline=False)
                        rank += 1
                    except discord.NotFound:
                        print(f"WARNING: User not found for ranking display: {user_id_str}") # デバッグ用にIDを出力
                        embed.add_field(name=f"**#{rank} 不明なユーザー ({user_id_str})**", value=f"ロール数: {data.get('rolls', 0)}", inline=False)
                        rank += 1
                    except Exception as e:
                        print(f"ERROR: Error during ranking display for user ID: {user_id_str}: {e}")
                        embed.add_field(name=f"**#{rank} エラーユーザー ({user_id_str})**", value=f"ロール数: {data.get('rolls', 0)} (エラー: {e})", inline=False)
                        rank += 1
                if not sorted_users:
                    embed.add_field(name="データなし", value="まだ誰もロールしていません。", inline=False)
                
                print("DEBUG: Attempting to send !ranking embed.")
                await message.channel.send(embed=embed)
                print("DEBUG: !ranking embed sent.")
            except Exception as e:
                print(f"ERROR: Failed to process !ranking command or send embed: {e}")
                import traceback
                traceback.print_exc()

        # --- Luck Potion レシピ表示コマンド ---
        elif command_content == "!recipe":
            print("DEBUG: Entering !recipe command block.")
            try:
                embed = discord.Embed(
                    title="Luck Potion 作成レシピ",
                    description="より強力なラックブーストを得るために、Luck Potionを合成しましょう！",
                    color=discord.Color.green()
                )

                for potion_name, recipe_data in LUCK_POTION_RECIPES.items():
                    materials_str = []
                    for material, quantity in recipe_data["materials"].items():
                        materials_str.append(f"{material} x {quantity}個")
                    
                    output_item = list(recipe_data["output"].keys())[0] # ポーションの内部名
                    output_quantity = list(recipe_data["output"].values())[0] # ポーションの個数
                    luck_multiplier = recipe_data["luck_multiplier"]

                    embed.add_field(
                        name=f"**{potion_name}**",
                        value=f"**効果:** ラック {luck_multiplier:,}倍 (1回のロール)\n"
                              f"**素材:** {', '.join(materials_str)}\n"
                              f"**作成数:** {output_quantity}個",
                        inline=False
                    )
                print("DEBUG: Attempting to send !recipe embed.")
                await message.channel.send(embed=embed)
                print("DEBUG: !recipe embed sent.")
            except Exception as e:
                print(f"ERROR: Failed to process !recipe command or send embed: {e}")
                import traceback
                traceback.print_exc()


        # --- Potion Make コマンド ---
        elif command_content.startswith("!make "):
            print("DEBUG: Entering !make command block.")
            try:
                parts = command_content.split(" ")
                if len(parts) < 3:
                    await message.channel.send("使い方が間違っています。例: `!make rtx4070 1` または `!make rtx4070 all`")
                    return

                target_potion_name_input = parts[1]
                quantity_str = parts[2]

                # 入力されたポーション名からレシピを検索
                target_recipe = None
                for potion_name_in_recipe, recipe_data in LUCK_POTION_RECIPES.items():
                    if potion_name_in_recipe.lower() == target_potion_name_input.lower():
                        target_recipe = recipe_data
                        break

                if not target_recipe:
                    await message.channel.send(f"指定されたポーション `{target_potion_name_input}` のレシピが見つかりません。`!recipe`で確認してください。")
                    return

                materials_needed = target_recipe["materials"]
                output_potion_internal_name = list(target_recipe["output"].keys())[0]
                output_potion_quantity_per_craft = list(target_recipe["output"].values())[0]

                async with user_data_lock: # user_dataの読み書きをロックで保護
                    user_inventory = user_data[user_id]["inventory"]
                    user_luck_potions = user_data[user_id]["luck_potions"]

                    max_craftable_count = float('inf')
                    for material, needed_quantity in materials_needed.items():
                        if needed_quantity > 0: # 0個必要な素材は無視
                            if material not in user_inventory or user_inventory[material] < needed_quantity:
                                max_craftable_count = 0 # 素材が足りなければ0
                                break
                            max_craftable_count = min(max_craftable_count, user_inventory[material] // needed_quantity)

                    if max_craftable_count == 0:
                        missing_materials = []
                        for material, needed_quantity in materials_needed.items():
                            owned = user_inventory.get(material, 0)
                            if owned < needed_quantity:
                                missing_materials.append(f"{material} ({needed_quantity - owned}個不足)")
                        await message.channel.send(f"素材が足りません！足りない素材: {', '.join(missing_materials)}")
                        return

                    craft_count = 0
                    if quantity_str.lower() == "all":
                        craft_count = max_craftable_count
                    else:
                        try:
                            craft_count = int(quantity_str)
                            if craft_count <= 0:
                                await message.channel.send("作成する個数は1以上である必要があります。")
                                return
                            if craft_count > max_craftable_count:
                                await message.channel.send(f"素材が足りません。最大で{max_craftable_count}個作成できます。")
                                return
                        except ValueError:
                            await message.channel.send("作成する個数は数字か 'all' で指定してください。")
                            return

                    # 素材を消費
                    for material, needed_quantity in materials_needed.items():
                        user_inventory[material] -= needed_quantity * craft_count
                        if user_inventory[material] <= 0:
                            del user_inventory[material]

                    # ポーションを付与
                    total_potions_made = output_potion_quantity_per_craft * craft_count
                    user_luck_potions[output_potion_internal_name] = user_luck_potions.get(output_potion_internal_name, 0) + total_potions_made

                    save_user_data()
                print("DEBUG: Attempting to send !make confirmation message.")
                await message.channel.send(f"{message.author.mention} は **{target_potion_name_input}** を {total_potions_made}個作成しました！")
                print("DEBUG: !make confirmation message sent.")
            except Exception as e:
                print(f"ERROR: Failed to process !make command or send message: {e}")
                import traceback
                traceback.print_exc()

        # --- Potion Use コマンド ---
        elif command_content.startswith("!use "):
            print("DEBUG: Entering !use command block.")
            try:
                parts = command_content.split(" ")
                if len(parts) < 3:
                    await message.channel.send("使い方が間違っています。例: `!use rtx4070 1` または `!use rtx4070 all`")
                    return

                target_potion_name_input = parts[1]
                quantity_str = parts[2]

                # 入力されたポーション名からレシピを検索し、内部名を取得
                target_potion_internal_name = None
                for potion_name_in_recipe, recipe_data in LUCK_POTION_RECIPES.items():
                    if potion_name_in_recipe.lower() == target_potion_name_input.lower():
                        target_potion_internal_name = list(recipe_data["output"].keys())[0]
                        break

                if not target_potion_internal_name:
                    await message.channel.send(f"指定されたポーション `{target_potion_name_input}` は存在しません。`!recipe`で確認してください。")
                    return

                async with user_data_lock: # user_dataの読み書きをロックで保護
                    user_luck_potions = user_data[user_id]["luck_potions"]
                    user_active_uses = user_data[user_id]["active_luck_potion_uses"]

                    owned_count = user_luck_potions.get(target_potion_internal_name, 0)

                    if owned_count == 0:
                        await message.channel.send(f"**{target_potion_name_input}** を所持していません。")
                        return

                    use_count = 0
                    if quantity_str.lower() == "all":
                        use_count = owned_count
                    else:
                        try:
                            use_count = int(quantity_str)
                            if use_count <= 0:
                                await message.channel.send("使用する個数は1以上である必要があります。")
                                return
                            if use_count > owned_count:
                                await message.channel.send(f"所持数が足りません。最大で{owned_count}個使用できます。")
                                return
                        except ValueError:
                            await message.channel.send("使用する個数は数字か 'all' で指定してください。")
                            return

                    # ポーションを消費して、active_luck_potion_usesに追加
                    user_luck_potions[target_potion_internal_name] -= use_count
                    if user_luck_potions[target_potion_internal_name] <= 0:
                        del user_luck_potions[target_potion_internal_name]

                    user_active_uses[target_potion_internal_name] = user_active_uses.get(target_potion_internal_name, 0) + (use_count * 1) # 1個のポーションで1回使用

                    save_user_data()
                print("DEBUG: Attempting to send !use confirmation message.")
                await message.channel.send(f"{message.author.mention} は **{target_potion_name_input}** を {use_count}個使用キューに追加しました。次のロールから効果が適用されます。")
                print("DEBUG: !use confirmation message sent.")
            except Exception as e:
                print(f"ERROR: Failed to process !use command or send message: {e}")
                import traceback
                traceback.print_exc()


        # --- Crafting コマンド ---
        elif command_content.startswith("!craft "):
            print("DEBUG: Entering !craft command block.")
            try:
                parts = command_content.split(" ")
                if len(parts) < 3:
                    await message.channel.send("使い方が間違っています。例: `!craft golden haka 5` または `!craft golden haka all`")
                    return

                target_item_name = " ".join(parts[1:-1])
                quantity_str = parts[-1]

                target_recipe = CRAFTING_RECIPES.get(target_item_name)

                if not target_recipe:
                    await message.channel.send(f"アイテム `{target_item_name}` の合成レシピが見つかりません。")
                    return

                materials_needed = target_recipe["materials"]
                output_item = list(target_recipe["output"].keys())[0]
                output_quantity_per_craft = list(target_recipe["output"].values())[0]

                async with user_data_lock: # user_dataの読み書きをロックで保護
                    user_inventory = user_data[user_id]["inventory"]

                    # 最大合成可能数を計算
                    max_craftable_count = float('inf')
                    for material, needed_quantity in materials_needed.items():
                        if needed_quantity > 0: # 0個必要な素材は無視
                            if material not in user_inventory or user_inventory[material] < needed_quantity:
                                max_craftable_count = 0 # 素材が足りなければ0
                                break
                            max_craftable_count = min(max_craftable_count, user_inventory[material] // needed_quantity)

                    if max_craftable_count == 0:
                        missing_materials = []
                        for material, needed_quantity in materials_needed.items():
                            owned = user_inventory.get(material, 0)
                            if owned < needed_quantity:
                                missing_materials.append(f"{material} ({needed_quantity - owned}個不足)")
                        await message.channel.send(f"素材が足りません！足りない素材: {', '.join(missing_materials)}")
                        return

                    craft_count = 0
                    if quantity_str.lower() == "all":
                        craft_count = max_craftable_count
                    else:
                        try:
                            craft_count = int(quantity_str)
                            if craft_count <= 0:
                                await message.channel.send("作成する個数は1以上である必要があります。")
                                return
                            if craft_count > max_craftable_count:
                                await message.channel.send(f"素材が足りません。最大で{max_craftable_count}個作成できます。")
                                return
                        except ValueError:
                            await message.channel.send("作成する個数は数字か 'all' で指定してください。")
                            return

                    # 素材を消費
                    for material, needed_quantity in materials_needed.items():
                        user_inventory[material] -= needed_quantity * craft_count
                        if user_inventory[material] <= 0:
                            del user_inventory[material]

                    # 完成品を付与
                    user_inventory[output_item] = user_inventory.get(output_item, 0) + (output_quantity_per_craft * craft_count)

                    save_user_data()
                print("DEBUG: Attempting to send !craft confirmation message.")
                await message.channel.send(f"{message.author.mention} は **{output_item}** を {output_quantity_per_craft * craft_count}個合成しました！")
                print("DEBUG: !craft confirmation message sent.")
            except Exception as e:
                print(f"ERROR: Failed to process !craft command or send message: {e}")
                import traceback
                traceback.print_exc()


        # --- 通常ユーザー用オートRNGコマンド ---
        elif command_content == "!autorng":
            print("DEBUG: Entering !autorng command block (regular user).")
            try:
                target_user = message.author
                target_user_id_str = str(target_user.id)

                # 既存のオートRNGが実行中か確認
                if target_user_id_str in auto_rng_sessions and auto_rng_sessions[target_user_id_str]["task"] and not auto_rng_sessions[target_user_id_str]["task"].done():
                    await message.channel.send(f"**{target_user.name}** のオートRNGはすでに実行中です。")
                    return

                session_duration_seconds = 6 * 3600 # 6時間

                auto_rng_sessions[target_user_id_str] = {
                    "task": bot.loop.create_task(auto_roll_task(target_user)),
                    "found_items_log": {},
                    "start_time": datetime.datetime.now(datetime.timezone.utc),
                    "max_duration_seconds": session_duration_seconds
                }
                save_auto_rng_sessions()
                print("DEBUG: Attempting to send !autorng start message.")
                await message.channel.send(f"**{target_user.name}** のオートRNGを開始しました。結果はDMで送信されます。")
                print("DEBUG: !autorng start message sent.")
            except Exception as e:
                print(f"ERROR: Failed to process !autorng command or send message: {e}")
                import traceback
                traceback.print_exc()


        # --- 管理者用オートRNG付与コマンド ---
        elif command_content.startswith("!giveautorng"):
            print("DEBUG: Entering !giveautorng command block (admin).")
            try:
                if message.author.id not in ADMIN_IDS:
                    await message.channel.send("このコマンドは管理者のみが使用できます。")
                    return

                parts = command_content.split(" ")
                if len(parts) < 2:
                    await message.channel.send("管理者用`!giveautorng`の使い方が間違っています。`!giveautorng @ユーザー名`、`!giveautorng [ユーザーID]`、または`!giveautorng all`")
                    return
                
                target_user = None
                target_user_id_str = None

                if len(message.mentions) > 0:
                    target_user = message.mentions[0]
                    target_user_id_str = str(target_user.id)
                elif parts[1] == "all":
                    target_user = "all" # 全ユーザー対象
                    target_user_id_str = "all" # この値は特殊なケースとして扱う
                else:
                    try:
                        target_user_id_str = parts[1]
                        target_user = await bot.fetch_user(int(target_user_id_str))
                    except (ValueError, discord.NotFound):
                        await message.channel.send("無効なユーザー指定です。メンション、ユーザーID、または 'all' を使用してください。")
                        return

                if target_user == "all":
                    await message.channel.send("全ユーザーのオートRNGを開始します。")
                    users_to_start = []
                    async with user_data_lock: # ロード時にuser_dataへのアクセスをロック
                        for uid_str in user_data.keys():
                            try:
                                user_obj = await bot.fetch_user(int(uid_str))
                                users_to_start.append(user_obj)
                            except discord.NotFound:
                                print(f"WARNING: User not found for admin !giveautorng: {uid_str}")
                    for user_obj in users_to_start:
                        if str(user_obj.id) in auto_rng_sessions and auto_rng_sessions[str(user_obj.id)]["task"] and not auto_rng_sessions[str(user_obj.id)]["task"].done():
                            await message.channel.send(f"**{user_obj.name}** のオートRNGはすでに実行中です。")
                        else:
                            session_duration_seconds = 6 * 3600 # 6時間
                            auto_rng_sessions[str(user_obj.id)] = {
                                "task": bot.loop.create_task(auto_roll_task(user_obj)),
                                "found_items_log": {},
                                "start_time": datetime.datetime.now(datetime.timezone.utc),
                                "max_duration_seconds": session_duration_seconds
                            }
                            save_auto_rng_sessions()
                            await message.channel.send(f"**{user_obj.name}** のオートRNGを開始しました。結果はDMで送信されます。")
                    return

                # 特定のユーザーの場合
                if target_user_id_str in auto_rng_sessions and auto_rng_sessions[target_user_id_str]["task"] and not auto_rng_sessions[target_user_id_str]["task"].done():
                    await message.channel.send(f"**{target_user.name}** のオートRNGはすでに実行中です。")
                    return

                session_duration_seconds = 6 * 3600 # 6時間

                auto_rng_sessions[target_user_id_str] = {
                    "task": bot.loop.create_task(auto_roll_task(target_user)),
                    "found_items_log": {}, # ここを辞書で初期化
                    "start_time": datetime.datetime.now(datetime.timezone.utc),
                    "max_duration_seconds": session_duration_seconds
                }
                save_auto_rng_sessions()
                print("DEBUG: Attempting to send !giveautorng start message.")
                await message.channel.send(f"**{target_user.name}** のオートRNGを開始しました。結果はDMで送信されます。")
                print("DEBUG: !giveautorng start message sent.")
            except Exception as e:
                print(f"ERROR: Failed to process !giveautorng command or send message: {e}")
                import traceback
                traceback.print_exc()


        # --- オートRNG停止コマンド ---
        elif command_content == "!autostop":
            print("DEBUG: Entering !autostop command block.")
            try:
                if user_id in auto_rng_sessions and auto_rng_sessions[user_id]["task"] and not auto_rng_sessions[user_id]["task"].done():
                    auto_rng_sessions[user_id]["task"].cancel()
                    print("DEBUG: Attempting to send !autostop confirmation message.")
                    await message.channel.send(f"{message.author.mention} のオートRNGを停止しました。結果はDMで送信されます。")
                    print("DEBUG: !autostop confirmation message sent.")
                else:
                    await message.channel.send(f"{message.author.mention} のオートRNGは現在実行されていません。")
            except Exception as e:
                print(f"ERROR: Failed to process !autostop command or send message: {e}")
                import traceback
                traceback.print_exc()

        # --- オートRNG残り時間確認コマンド ---
        elif command_content == "!autorngtime":
            print("DEBUG: Entering !autorngtime command block.")
            try:
                if user_id in auto_rng_sessions and auto_rng_sessions[user_id]["task"] and not auto_rng_sessions[user_id]["task"].done():
                    session_data = auto_rng_sessions[user_id]
                    start_time = session_data["start_time"]
                    max_duration_seconds = session_data["max_duration_seconds"]

                    # 修正: current_time_utcもタイムゾーン情報を持つようにする
                    current_time_utc = datetime.datetime.now(datetime.timezone.utc)
                    elapsed_time = (current_time_utc - start_time).total_seconds()
                    remaining_time_seconds = max_duration_seconds - elapsed_time

                    if remaining_time_seconds <= 0:
                        await message.channel.send(f"{message.author.mention} のオートRNGはすでに終了しています。")
                    else:
                        hours, remainder = divmod(int(remaining_time_seconds), 3600)
                        minutes, seconds = divmod(remainder, 60)
                        print("DEBUG: Attempting to send !autorngtime message.")
                        await message.channel.send(f"{message.author.mention} のオートRNG残り時間: **{hours}時間 {minutes}分 {seconds}秒**")
                        print("DEBUG: !autorngtime message sent.")
                else:
                    await message.channel.send(f"{message.author.mention} のオートRNGは現在実行されていません。")
            except Exception as e:
                print(f"ERROR: Failed to process !autorngtime command or send message: {e}")
                import traceback
                traceback.print_exc()

        # --- 管理者向けオートRNG状況確認コマンド ---
        elif command_content == "!adminautorng":
            print("DEBUG: Entering !adminautorng command block.")
            try:
                if message.author.id not in ADMIN_IDS:
                    await message.channel.send("このコマンドは管理者のみが使用できます。")
                    return

                active_sessions = []
                for uid, session_data in auto_rng_sessions.items():
                    if session_data["task"] and not session_data["task"].done():
                        try:
                            user_obj = await bot.fetch_user(int(uid))
                            start_time = session_data["start_time"]
                            max_duration_seconds = session_data["max_duration_seconds"]
                            
                            # 修正: current_time_utcもタイムゾーン情報を持つようにする
                            current_time_utc = datetime.datetime.now(datetime.timezone.utc)
                            elapsed_time = (current_time_utc - start_time).total_seconds()
                            remaining_time_seconds = max_duration_seconds - elapsed_time

                            if remaining_time_seconds > 0:
                                hours, remainder = divmod(int(remaining_time_seconds), 3600)
                                minutes, seconds = divmod(remainder, 60)
                                active_sessions.append(f"・{user_obj.name} (ID: {uid}): 残り {hours}h {minutes}m {seconds}s")
                            else:
                                active_sessions.append(f"・{user_obj.name} (ID: {uid}): 期限切れ (データ更新待ち)") # 時間切れだがまだセッションに残っている場合
                        except discord.NotFound:
                            print(f"WARNING: User not found for adminautorng display: {uid}") # デバッグ用にIDを出力
                            active_sessions.append(f"・不明なユーザー (ID: {uid}): (ユーザーが見つかりません)")
                        except Exception as e:
                            print(f"ERROR: Error during adminautorng display for user ID: {uid}: {e}")
                            active_sessions.append(f"・{uid}: データの読み込みエラー ({e})")

                if active_sessions:
                    embed = discord.Embed(
                        title="現在実行中のオートRNGセッション",
                        description="\n".join(active_sessions),
                        color=discord.Color.red()
                    )
                    print("DEBUG: Attempting to send !adminautorng embed.")
                    await message.channel.send(embed=embed)
                    print("DEBUG: !adminautorng embed sent.")
                else:
                    await message.channel.send("現在、実行中のオートRNGセッションはありません。")
            except Exception as e:
                print(f"ERROR: Failed to process !adminautorng command or send embed: {e}")
                import traceback
                traceback.print_exc()

        # --- 管理者向けラックブーストコマンド ---
        elif command_content.startswith("!boostluck"):
            print("DEBUG: Entering !boostluck command block.")
            try:
                if message.author.id not in ADMIN_IDS:
                    await message.channel.send("このコマンドは管理者のみが使用できます。")
                    return

                parts = command_content.split(" ")
                if len(parts) != 3:
                    await message.channel.send("使い方が間違っています。例: `!boostluck 1.5 60` (1.5倍、60秒)")
                    return

                try:
                    multiplier = float(parts[1])
                    duration_seconds = int(parts[2])
                    if multiplier <= 0 or duration_seconds <= 0:
                        await message.channel.send("倍率と秒数は正の数である必要があります。")
                        return
                except ValueError:
                    await message.channel.send("倍率と秒数は数値で指定してください。")
                    return

                end_time_timestamp = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=duration_seconds)).timestamp()

                async with user_data_lock: # 全ユーザーのuser_dataを変更するためロック
                    for uid in user_data:
                        # user_data[uid]["luck"] は、デイリーログインブーストとは別に、
                        # 管理者による一時的な基本ラック変更として使用される想定です。
                        # ここでは直接変更し、デイリーログインブーストは `perform_roll` や表示時に乗算されます。
                        user_data[uid]["luck"] = multiplier 
                        # 管理者ブースト情報も更新
                        user_data[uid]["admin_boost"] = {
                            "multiplier": multiplier,
                            "end_time": end_time_timestamp
                        }
                    save_user_data()

                print("DEBUG: Attempting to send !boostluck start message.")
                await message.channel.send(f"全員のラックを一時的に **{multiplier:.1f}倍** にしました！ ({duration_seconds}秒間有効)")
                print("DEBUG: !boostluck start message sent.")

                # 指定時間後に元のラックに戻すタスクをスケジュール
                await asyncio.sleep(duration_seconds)

                async with user_data_lock: # 全ユーザーのuser_dataを変更するためロック
                    for uid in user_data:
                        # デイリーログインブーストが残っている場合を考慮し、
                        # ここではluckを1.0に戻すだけで、デイリーログインブーストはそのまま維持される
                        user_data[uid]["luck"] = 1.0
                        user_data[uid]["admin_boost"] = { # 管理者ブーストをリセット
                            "multiplier": 1.0,
                            "end_time": None
                        }
                    save_user_data()
                await message.channel.send("全員のラックブーストが終了し、元のラックに戻りました。")
            except Exception as e:
                print(f"ERROR: Failed to process !boostluck command or send message: {e}")
                import traceback
                traceback.print_exc()

        # --- 管理者向け全データリセットコマンド ---
        elif command_content == "!resetall":
            print("DEBUG: Entering !resetall command block.")
            try:
                if message.author.id not in ADMIN_IDS:
                    await message.channel.send("このコマンドは管理者のみが使用できます。")
                    return

                # 念のため確認メッセージ
                await message.channel.send("**警告: 全ユーザーのデータがリセットされます。本当に実行しますか？ `yes` と入力して10秒以内に送信してください。**")

                def check(m):
                    return m.author == message.author and m.channel == message.channel and m.content.lower() == 'yes'

                try:
                    confirm_message = await bot.wait_for('message', check=check, timeout=10.0)
                    if confirm_message:
                        async with user_data_lock: # データをリセットする前にロック
                            user_data = {} # 全データをクリア
                            save_user_data()

                            for session_id, session_data in auto_rng_sessions.items():
                                if session_data["task"] and not session_data["task"].done():
                                    session_data["task"].cancel() # 実行中のオートRNGタスクを停止
                            auto_rng_sessions = {} # オートRNGセッションもクリア
                            save_auto_rng_sessions()

                        await message.channel.send("全ユーザーのデータとオートRNGセッションがリセットされました。")
                except asyncio.TimeoutError:
                    await message.channel.send("確認がタイムアウトしました。データのリセットはキャンセルされました。")
                except Exception as e:
                    print(f"ERROR: Error during !resetall confirmation or processing: {e}")
                    import traceback
                    traceback.print_exc()
            except Exception as e:
                print(f"ERROR: Failed to process !resetall command or send message: {e}")
                import traceback
                traceback.print_exc()

        # --- 新しい管理者向けユーザーデータ削除コマンド ---
        elif command_content.startswith("!delete"):
            print("DEBUG: Entering !delete command block (admin).")
            try:
                if message.author.id not in ADMIN_IDS:
                    await message.channel.send("このコマンドは管理者のみが使用できます。")
                    return
                
                parts = command_content.split(" ")
                if len(parts) < 2:
                    await message.channel.send("使い方が間違っています。例: `!delete @ユーザー名`, `!delete [ユーザーID]`, または `!delete all`")
                    return

                target = parts[1]
                target_user_ids_to_delete = []
                target_names_to_report = []

                if target == "all":
                    target_user_ids_to_delete = list(user_data.keys())
                    target_names_to_report = ["全ユーザー"]
                else:
                    user_obj = None
                    try:
                        # メンションからIDを抽出 (メンション形式は <@!ID> または <@ID>)
                        if message.mentions and str(message.mentions[0].id) == target.replace("<@", "").replace(">", "").replace("!", ""): 
                            user_obj = message.mentions[0]
                        else: # IDが直接指定された場合
                            user_obj = await bot.fetch_user(int(target))
                        target_user_ids_to_delete.append(str(user_obj.id))
                        target_names_to_report.append(user_obj.name)
                    except (ValueError, discord.NotFound):
                        await message.channel.send("指定されたユーザーが見つかりません。メンションまたは有効なユーザーIDを使用してください。")
                        return
                
                if not target_user_ids_to_delete:
                    await message.channel.send("削除対象のユーザーが指定されていません。")
                    return

                confirmation_message_text = f"**警告: {', '.join(target_names_to_report)} の全てのデータが削除されます。** オートRNGセッションも停止されます。本当に実行しますか？ `yes` と入力して10秒以内に送信してください。"
                await message.channel.send(confirmation_message_text)

                def check(m):
                    return m.author == message.author and m.channel == message.channel and m.content.lower() == 'yes'

                try:
                    confirm_message = await bot.wait_for('message', check=check, timeout=10.0)
                    if confirm_message:
                        async with user_data_lock:
                            for uid_to_delete in target_user_ids_to_delete:
                                if uid_to_delete in user_data:
                                    del user_data[uid_to_delete]
                                    print(f"DEBUG: Deleted user data for {uid_to_delete}.")
                                
                                # オートRNGセッションも停止・削除
                                if uid_to_delete in auto_rng_sessions:
                                    if auto_rng_sessions[uid_to_delete]["task"] and not auto_rng_sessions[uid_to_delete]["task"].done():
                                        auto_rng_sessions[uid_to_delete]["task"].cancel()
                                        print(f"DEBUG: Cancelled auto-RNG task for {uid_to_delete}.")
                                    del auto_rng_sessions[uid_to_delete]
                                    print(f"DEBUG: Deleted auto-RNG session for {uid_to_delete}.")
                                
                                # オートRNG保存カウンターも削除
                                if uid_to_delete in last_auto_rng_save_rolls:
                                    del last_auto_rng_save_rolls[uid_to_delete]
                                if uid_to_delete in last_auto_rng_save_time:
                                    del last_auto_rng_save_time[uid_to_delete]

                            save_user_data()
                            save_auto_rng_sessions()
                            await message.channel.send(f"{', '.join(target_names_to_report)} のデータとオートRNGセッションが削除されました。")
                    else:
                        await message.channel.send("確認が一致しませんでした。データ削除はキャンセルされました。")
                except asyncio.TimeoutError:
                    await message.channel.send("確認がタイムアウトしました。データ削除はキャンセルされました。")
                except Exception as e:
                    print(f"ERROR: Error during !delete command processing: {e}")
                    import traceback
                    traceback.print_exc()
                    await message.channel.send(f"データ削除中にエラーが発生しました: {e}")

            except Exception as e:
                print(f"ERROR: Failed to process !delete command or send message: {e}")
                import traceback
                traceback.print_exc()

        # --- 新しいデバッグ用コマンド ---
        elif command_content == "!test":
            print("DEBUG: Entering !test command block.")
            try:
                await message.channel.send("ボットは正常に動作しています！")
                print("DEBUG: !test response sent.")
            except Exception as e:
                print(f"ERROR: Failed to send !test response: {e}")
                import traceback
                traceback.print_exc()
        
        # --- コマンドが認識されなかった場合のログ ---
        else:
            print(f"DEBUG: Command '{command_content}' not recognized or handled.")


    except Exception as e:
        print(f"CRITICAL ERROR in on_message function! Please review the traceback below:")
        import traceback
        traceback.print_exc() # 詳細なエラー情報も出力
        # ユーザーにエラーが発生したことを通知する場合（開発中のみ推奨）
        # await message.channel.send(f"ボットの処理中に予期せぬエラーが発生しました: `{e}`")


# オートRNGセッションの保存頻度を調整するためのグローバル変数
# これを導入することで、ロールごとの保存ではなく、一定ロール数ごとや時間ごとなどに変更可能になる
AUTO_RNG_SAVE_INTERVAL_ROLLS = 100 # 例: 100ロールごとに保存
AUTO_RNG_SAVE_INTERVAL_SECONDS = 60 # 例: 60秒ごとに保存 (どちらか早い方)
last_auto_rng_save_time = {} # user_id -> last_save_timestamp
last_auto_rng_save_rolls = {} # user_id -> last_save_rolls_count


async def auto_roll_task(user: discord.User, is_resumed: bool = False):
    """
    指定されたユーザーの自動ロールを実行する非同期タスク。
    """
    user_id = str(user.id)
    session_data = auto_rng_sessions[user_id]
    found_items_log = session_data["found_items_log"]
    start_time = session_data["start_time"]
    max_duration_seconds = session_data["max_duration_seconds"]

    # user_dataへのアクセスはロックで保護
    async with user_data_lock:
        initial_rolls = user_data[user_id].get("rolls", 0) # 開始時のロール数を記録
        # オートRNG開始時の保存カウンターを初期化
        last_auto_rng_save_rolls[user_id] = initial_rolls
        last_auto_rng_save_time[user_id] = time.time()


    try:
        # 途中再開の場合、残り時間を計算してsleep
        if is_resumed:
            current_time_utc = datetime.datetime.now(datetime.timezone.utc)
            elapsed_time = (current_time_utc - start_time).total_seconds()
            remaining_time = max_duration_seconds - elapsed_time
            if remaining_time <= 0:
                # user_dataへのアクセスはロックで保護
                async with user_data_lock:
                    rolls_performed = user_data[user_id].get("rolls", 0) - initial_rolls
                try:
                    await send_auto_rng_results(user, found_items_log, rolls_performed, "再開前に時間切れ")
                except Exception as e:
                    print(f"WARNING: Could not send auto-RNG results (time out on resume) to {user.name}: {e}")
                
                # 終了時のクリーンアップ
                if user_id in auto_rng_sessions:
                    del auto_rng_sessions[user_id]
                    save_auto_rng_sessions()
                if user_id in last_auto_rng_save_rolls:
                    del last_auto_rng_save_rolls[user_id]
                if user_id in last_auto_rng_save_time:
                    del last_auto_rng_save_time[user_id]
                return

            try:
                await user.send(f"オートRNGセッションを再開します。残り約 {remaining_time / 3600:.1f}時間です。")
            except Exception as e:
                print(f"WARNING: Could not send auto-RNG resume message to {user.name}: {e}")
            # 最初のロールまで待機
            await asyncio.sleep(1) # 1秒待ってからロール開始 (誤差を考慮)


        while True:
            # 時間制限チェック
            current_time_utc = datetime.datetime.now(datetime.timezone.utc)
            elapsed_time = (current_time_utc - start_time).total_seconds()
            if elapsed_time >= max_duration_seconds:
                # user_dataへのアクセスはロックで保護
                async with user_data_lock:
                    rolls_performed = user_data[user_id].get("rolls", 0) - initial_rolls
                try:
                    await send_auto_rng_results(user, found_items_log, rolls_performed, "時間切れ")
                except Exception as e:
                    print(f"WARNING: Could not send auto-RNG results (time out) to {user.name}: {e}")
                break # ループを抜ける

            # ロール実行
            async with user_data_lock: # user_data変更時にロック
                # ユーザーの基本ラック (通常は1.0)
                current_base_luck = user_data[user_id]["luck"]

                # デイリーログインブーストの適用
                user_boost = user_data[user_id]["daily_login"]["active_boost"]
                if user_boost["end_time"] and datetime.datetime.now(datetime.timezone.utc) < datetime.datetime.fromtimestamp(user_boost["end_time"], tz=datetime.timezone.utc):
                    current_base_luck *= user_boost["multiplier"]
                
                # 管理者ブーストの適用
                admin_boost_info = user_data[user_id].get("admin_boost", {"multiplier": 1.0, "end_time": None})
                if admin_boost_info["end_time"] and current_time < datetime.datetime.fromtimestamp(admin_boost_info["end_time"], tz=datetime.timezone.utc):
                    current_base_luck *= admin_boost_info["multiplier"]

                # Luck Potionの適用ロジック (active_luck_potion_usesから消費)
                applied_potion_multiplier = 1.0
                applied_potion_display_name = None

                active_uses = user_data[user_id]["active_luck_potion_uses"]

                highest_multiplier = 1.0
                best_potion_internal_name = None
                sorted_potions_by_multiplier = sorted(LUCK_POTION_EFFECTS.items(), key=lambda item: item[1], reverse=True)

                for internal_name, multiplier_value in sorted_potions_by_multiplier:
                    if active_uses.get(internal_name, 0) > 0:
                        highest_multiplier = multiplier_value
                        best_potion_internal_name = internal_name
                        break

                if best_potion_internal_name:
                    applied_potion_multiplier = highest_multiplier
                    current_luck_for_roll = current_base_luck * applied_potion_multiplier

                    active_uses[best_potion_internal_name] -= 1
                    if active_uses[best_potion_internal_name] <= 0:
                        del active_uses[best_potion_internal_name]
                else:
                    current_luck_for_roll = current_base_luck

                user_data[user_id]["rolls"] = user_data[user_id].get("rolls", 0) + 1
                chosen_item, luck_applied_denominator, original_denominator = perform_roll(current_luck_for_roll) # perform_rollが3つの値を返す

                inventory = user_data[user_id]["inventory"]
                inventory[chosen_item] = inventory.get(chosen_item, 0) + 1

                # ★★★ データ保存頻度の調整 ★★★
                # ロールごとではなく、一定のロール数ごと、または時間ごとに保存
                current_rolls_count = user_data[user_id]["rolls"]
                current_time_for_save = time.time()

                should_save = False
                if current_rolls_count - last_auto_rng_save_rolls.get(user_id, 0) >= AUTO_RNG_SAVE_INTERVAL_ROLLS:
                    should_save = True
                    print(f"DEBUG: Auto-RNG save triggered by rolls for {user.name}")
                if current_time_for_save - last_auto_rng_save_time.get(user_id, current_time_for_save) >= AUTO_RNG_SAVE_INTERVAL_SECONDS:
                    should_save = True
                    print(f"DEBUG: Auto-RNG save triggered by time for {user.name}")

                if should_save:
                    save_user_data()
                    save_auto_rng_sessions()
                    last_auto_rng_save_rolls[user_id] = current_rolls_count
                    last_auto_rng_save_time[user_id] = current_time_for_save
                    print(f"DEBUG: Auto-RNG data saved for {user.name}.")


            # レアアイテム通知 (オートRNG中も通知)
            if original_denominator >= 100000: # ★★★ 通知判断は元の分母で ★★★
                notification_channel_id = bot_settings.get("notification_channel_id")
                if notification_channel_id:
                    notification_channel = bot.get_channel(notification_channel_id)
                    if notification_channel:
                        total_item_counts = {item: 0 for item in rare_item_chances_denominator.keys()}
                        async with user_data_lock: # 全ユーザーデータへのアクセスをロック
                            for uid_all in user_data:
                                for item, count in user_data[uid_all]["inventory"].items():
                                    if item in total_item_counts:
                                        total_item_counts[item] += count

                        notification_embed = discord.Embed(
                            title="レアアイテムドロップ通知！ (オートRNG)",
                            description=f"{user.mention} がオートRNGでレアアイテムを獲得しました！",
                            color=discord.Color.gold()
                        )
                        notification_embed.add_field(name="獲得者", value=user.mention, inline=False)
                        notification_embed.add_field(name="アイテム", value=chosen_item, inline=False)
                        notification_embed.add_field(name="確率", value=f"1 in {original_denominator:,}", inline=False) # 表示は元の確率
                        notification_embed.add_field(name="獲得日時", value=datetime.datetime.now(datetime.timezone.utc).strftime("%Y年%m月%d日 %H:%M:%S UTC"), inline=False)
                        notification_embed.add_field(name="サーバー総所持数", value=f"{total_owned_count}個", inline=False)
                        notification_embed.set_footer(text="おめでとうございます！")
                        try:
                            await notification_channel.send(embed=notification_embed)
                        except Exception as e:
                            print(f"WARNING: Could not send rare item notification to channel {notification_channel.id}: {e}")
                    else:
                        print(f"WARNING: Configured notification channel ID {notification_channel_id} not found.")

            await asyncio.sleep(1) # 1秒待機

    except asyncio.CancelledError:
        # タスクがキャンセルされた場合 (例: !autostop コマンド)
        async with user_data_lock: # user_dataへのアクセスはロックで保護
            rolls_performed = user_data[user_id].get("rolls", 0) - initial_rolls
        try:
            await send_auto_rng_results(user, found_items_log, rolls_performed, "手動停止")
        except Exception as e:
            print(f"WARNING: Could not send auto-RNG results (manual stop) to {user.name}: {e}")
    except Exception as e:
        print(f"ERROR: Auto-RNG error (user ID: {user_id}): {e}")
        import traceback
        traceback.print_exc()
        try:
            await user.send(f"オートRNG中にエラーが発生しました: {e}")
        except Exception as dm_e:
            print(f"WARNING: Could not send error message to user {user.name}: {dm_e}")
    finally:
        # セッション終了時のクリーンアップ
        if user_id in auto_rng_sessions:
            del auto_rng_sessions[user_id]
            save_auto_rng_sessions() # セッション終了を反映して保存
        if user_id in last_auto_rng_save_rolls: # 終了時にはカウンターも削除
            del last_auto_rng_save_rolls[user_id]
        if user_id in last_auto_rng_save_time:
            del last_auto_rng_save_time[user_id]
        print(f"DEBUG: Auto-RNG session for {user.name} finished/cleaned up.")

# ここにDiscord Botのトークンを記述
# 環境変数からトークンを取得するのが推奨される
bot.run(os.environ['DISCORD_BOT_TOKEN'])
