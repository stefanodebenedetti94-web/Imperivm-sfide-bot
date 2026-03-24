import os
import json
import random
from datetime import datetime, timedelta, time
from typing import Optional, Dict, Any, List
from zoneinfo import ZoneInfo

import discord
from discord.ext import commands, tasks
from discord import app_commands


# ============================================================
# IMPERIVM - Weekly Challenges Bot
# main.py
# ============================================================

TZ = ZoneInfo("Europe/Rome")

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "")
GUILD_ID = int(os.getenv("GUILD_ID", "0") or 0)
CHALLENGE_CHANNEL_ID = int(os.getenv("CHALLENGE_CHANNEL_ID", "0") or 0)
DATA_FILE = os.getenv("DATA_FILE", "sfide_data.json")
SYNC_ON_START = os.getenv("SYNC_ON_START", "true").lower() == "true"
TEST_GUILD_ONLY = os.getenv("TEST_GUILD_ONLY", "true").lower() == "true"

if not DISCORD_TOKEN:
    raise RuntimeError("Manca DISCORD_TOKEN nelle variabili ambiente.")

if not CHALLENGE_CHANNEL_ID:
    raise RuntimeError("Manca CHALLENGE_CHANNEL_ID nelle variabili ambiente.")

intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.message_content = False

bot = commands.Bot(command_prefix="!", intents=intents)

CHALLENGE_TYPES = ["dungeon", "kolosseo"]
CHALLENGE_TYPE_WEIGHTS = {
    "dungeon": 100,
    "kolosseo": 100,
}

KOLOSSEO_MAPS = [
    "Yop Arena",
    "Sadida Arena",
    "Eniripsa Arena",
    "Sram Arena",
    "Foggernaut Arena",
    "Rougue Arena",
    "Xelor Arena",
    "Ecaflio Arena",
]

DUNGEONS = [
    {"name": "Conte Harembourg", "difficulty": "Difficilissimo", "reward": 2500000, "weight": 10},
    {"name": "Missiz Freezz", "difficulty": "Alta", "reward": 1000000, "weight": 45},
    {"name": "Klime", "difficulty": "Alta", "reward": 1000000, "weight": 45},
    {"name": "Sylargh", "difficulty": "Alta", "reward": 1000000, "weight": 45},
    {"name": "Nileza", "difficulty": "Alta", "reward": 1500000, "weight": 45},
    {"name": "Wind Dojo", "difficulty": "Media", "reward": 1000000, "weight": 80},
    {"name": "Celestial Bearbarian", "difficulty": "Media", "reward": 800000, "weight": 80},
    {"name": "Katamashi", "difficulty": "Media", "reward": 800000, "weight": 80},
    {"name": "Damadrya", "difficulty": "Media", "reward": 800000, "weight": 80},
    {"name": "Fuji + Tengu", "difficulty": "Media", "reward": 800000, "weight": 80},
    {"name": "Korriander", "difficulty": "Easy", "reward": 600000, "weight": 120},
    {"name": "Sakai Miniera", "difficulty": "Easy", "reward": 600000, "weight": 120},
    {"name": "Kolosso", "difficulty": "Easy", "reward": 600000, "weight": 120},
    {"name": "Tanukoi San", "difficulty": "Easy", "reward": 600000, "weight": 120},
]


def now_rome() -> datetime:
    return datetime.now(TZ)


def fmt_dt(dt: datetime) -> str:
    return dt.astimezone(TZ).strftime("%d/%m/%Y %H:%M")


def fmt_kama(value: int) -> str:
    return f"{value:,}".replace(",", ".") + " kama"


def mention_user(user_id: Optional[int]) -> str:
    return f"<@{user_id}>" if user_id else "—"


def challenge_week_key(dt: Optional[datetime] = None) -> str:
    dt = dt or now_rome()
    iso_year, iso_week, _ = dt.isocalendar()
    return f"{iso_year}-W{iso_week:02d}"


def weighted_choice(items: List[Dict[str, Any]], weight_key: str = "weight") -> Dict[str, Any]:
    weights = [max(1, int(x.get(weight_key, 1))) for x in items]
    return random.choices(items, weights=weights, k=1)[0]


def parse_local_datetime(text: str) -> datetime:
    return datetime.strptime(text, "%Y-%m-%d %H:%M").replace(tzinfo=TZ)


def next_monday_8(dt: Optional[datetime] = None) -> datetime:
    dt = dt or now_rome()
    days_ahead = (0 - dt.weekday()) % 7
    candidate = datetime.combine((dt + timedelta(days=days_ahead)).date(), time(8, 0), tzinfo=TZ)
    if candidate <= dt:
        candidate += timedelta(days=7)
    return candidate


def next_tuesday_8_from(dt: Optional[datetime] = None) -> datetime:
    dt = dt or now_rome()
    days_ahead = (1 - dt.weekday()) % 7
    candidate = datetime.combine((dt + timedelta(days=days_ahead)).date(), time(8, 0), tzinfo=TZ)
    if candidate <= dt:
        candidate += timedelta(days=7)
    return candidate


def get_reward_for_champion_level(level: int) -> int:
    if level >= 10:
        return 500000
    if level >= 5:
        return 300000
    if level >= 3:
        return 200000
    return 100000


def admin_only() -> app_commands.Check:
    return app_commands.checks.has_permissions(administrator=True)


def choose_weekly_challenge() -> str:
    history = state.get("challenge_history", [])
    if len(history) >= 2:
        last_two = history[-2:]
        if last_two[0] == last_two[1]:
            return "dungeon" if last_two[0] == "kolosseo" else "kolosseo"

    return weighted_choice(
        [{"name": k, "weight": v} for k, v in CHALLENGE_TYPE_WEIGHTS.items()],
        weight_key="weight",
    )["name"]


def default_state() -> Dict[str, Any]:
    return {
        "current_week": None,
        "active_challenge": None,
        "state": "idle",  # idle | open | signup_closed | completed
        "last_opened_at": None,
        "challenge_history": [],
        "auto": {
            "next_weekly_open": None,
            "next_kolosseo_close": None,
        },
        "tests": {
            "scheduled_open": None,
            "scheduled_close": None,
        },
        "messages": {
            "channel_id": CHALLENGE_CHANNEL_ID,
            "challenge_message_id": None,
            "signup_message_id": None,
            "result_message_id": None,
        },
        "dungeon": {
            "name": None,
            "difficulty": None,
            "reward": 0,
            "winners": [],
            "time": None,
            "opened_at": None,
            "closed_at": None,
        },
        "kolosseo": {
            "signup_open": False,
            "participants": [],
            "challengers": [],
            "selected_map": None,
            "current_champion_id": None,
            "current_champion_name": None,
            "champion_level": 0,
            "reward_per_win": 100000,
            "opened_at": None,
            "signup_closed_at": None,
            "closed_at": None,
        },
    }


state: Dict[str, Any] = {}


def save_state() -> None:
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def load_state() -> None:
    global state
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            state = json.load(f)
    else:
        state = default_state()
        save_state()

    state.setdefault("messages", {})
    state["messages"]["channel_id"] = CHALLENGE_CHANNEL_ID
    state.setdefault("challenge_history", [])
    state.setdefault("kolosseo", {})
    state["kolosseo"].setdefault("selected_map", None)


def ensure_auto_schedule() -> None:
    if not state["auto"].get("next_weekly_open"):
        state["auto"]["next_weekly_open"] = next_monday_8().isoformat()
        save_state()


async def get_target_channel() -> Optional[discord.TextChannel]:
    channel_id = int(state.get("messages", {}).get("channel_id") or 0)
    if not channel_id:
        return None

    channel = bot.get_channel(channel_id)
    if channel is None:
        try:
            fetched = await bot.fetch_channel(channel_id)
            if isinstance(fetched, discord.TextChannel):
                return fetched
            return None
        except Exception:
            return None

    return channel if isinstance(channel, discord.TextChannel) else None


async def fetch_message_if_possible(message_id: Optional[int]) -> Optional[discord.Message]:
    if not message_id:
        return None
    channel = await get_target_channel()
    if not channel:
        return None
    try:
        return await channel.fetch_message(int(message_id))
    except Exception:
        return None


def build_dungeon_open_embed() -> discord.Embed:
    dungeon = state["dungeon"]
    embed = discord.Embed(
        title="🏛️ Sfida Settimanale — Dungeon Rush",
        description=(
            "La sfida settimanale è iniziata.\n"
            "Questa settimana i membri di IMPERIVM dovranno completare il dungeon "
            "sorteggiato nel minor tempo possibile."
        ),
        color=discord.Color.red(),
        timestamp=now_rome(),
    )
    embed.add_field(name="Dungeon sorteggiato", value=dungeon["name"], inline=False)
    embed.add_field(name="Difficoltà", value=dungeon["difficulty"], inline=True)
    embed.add_field(name="Premio", value=fmt_kama(dungeon["reward"]), inline=True)
    embed.add_field(name="Durata", value="Da lunedì 08:00 a domenica 12:00", inline=False)
    embed.add_field(
        name="Regole",
        value=(
            "• Max 4 partecipanti per team\n"
            "• NO multi-account\n"
            "• NO Heroes Mode\n"
            "• Screen del tempo finale obbligatorio"
        ),
        inline=False,
    )
    embed.set_footer(text="La chiusura della sfida e l'annuncio vincitori saranno gestiti manualmente dallo staff.")
    return embed


def build_dungeon_final_embed() -> discord.Embed:
    dungeon = state["dungeon"]
    winners = dungeon.get("winners", [])
    winners_text = "\n".join(mention_user(uid) for uid in winners) if winners else "—"

    embed = discord.Embed(
        title="🏁 Dungeon Rush — Vincitori Ufficiali",
        description="La sfida settimanale si è conclusa. Ecco il team vincitore.",
        color=discord.Color.gold(),
        timestamp=now_rome(),
    )
    embed.add_field(name="Dungeon", value=dungeon.get("name") or "—", inline=False)
    embed.add_field(name="Vincitori", value=winners_text, inline=False)
    embed.add_field(name="Tempo registrato", value=dungeon.get("time") or "—", inline=True)
    embed.add_field(name="Premio", value=fmt_kama(int(dungeon.get("reward") or 0)), inline=True)
    return embed


def build_kolosseo_open_embed() -> discord.Embed:
    kol = state["kolosseo"]
    champ_id = kol.get("current_champion_id")
    level = int(kol.get("champion_level") or 0)
    reward = int(kol.get("reward_per_win") or 100000)

    if champ_id:
        description = (
            "Il campione attuale è pronto a difendere il titolo.\n"
            "Le iscrizioni sono aperte solo per gli sfidanti."
        )
    else:
        description = (
            "Le iscrizioni al Kolosseo sono aperte.\n"
            "Non esiste ancora un campione: tra gli iscritti verranno sorteggiati "
            "1 Campione e 3 Sfidanti."
        )

    embed = discord.Embed(
        title="⚔️ Sfida Settimanale — Kolosseo",
        description=description,
        color=discord.Color.dark_red(),
        timestamp=now_rome(),
    )
    embed.add_field(name="Iscrizioni aperte fino a", value="Martedì ore 08:00", inline=True)
    embed.add_field(name="Come partecipare", value="Premi il pulsante qui sotto", inline=True)

    if champ_id:
        embed.add_field(name="Campione attuale", value=mention_user(champ_id), inline=False)
        embed.add_field(name="Livello campione", value=str(level), inline=True)
        embed.add_field(name="Premio attuale per ogni fight vinto", value=fmt_kama(reward), inline=True)
    else:
        embed.add_field(name="Premio attuale per ogni fight vinto", value=fmt_kama(100000), inline=False)

    embed.set_footer(text="Alla chiusura delle iscrizioni il bot sorteggerà automaticamente partecipanti e mappa.")
    return embed


def build_kolosseo_closed_embed() -> discord.Embed:
    return discord.Embed(
        title="🏛️ Iscrizioni Chiuse — Kolosseo",
        description="Le iscrizioni al Kolosseo sono terminate. Il sorteggio dei partecipanti è stato completato.",
        color=discord.Color.orange(),
        timestamp=now_rome(),
    )


def build_kolosseo_draw_embed() -> discord.Embed:
    kol = state["kolosseo"]
    champ_id = kol.get("current_champion_id")
    challengers = kol.get("challengers", [])
    reward = int(kol.get("reward_per_win") or 100000)
    level = int(kol.get("champion_level") or 0)
    selected_map = kol.get("selected_map") or "—"

    embed = discord.Embed(
        title="👑 Difesa del Trono — Kolosseo",
        description="Il sorteggio è completato. I fight potranno essere disputati da ora fino a domenica 12:00.",
        color=discord.Color.blurple(),
        timestamp=now_rome(),
    )
    embed.add_field(name="Campione", value=mention_user(champ_id), inline=False)
    embed.add_field(name="Livello campione", value=str(level), inline=True)
    embed.add_field(name="Premio attuale per ogni fight vinto", value=fmt_kama(reward), inline=True)
    embed.add_field(name="Mappa sorteggiata", value=selected_map, inline=False)

    for idx, user_id in enumerate(challengers, start=1):
        embed.add_field(name=f"Sfidante {idx}", value=mention_user(user_id), inline=False)

    if not challengers:
        embed.add_field(name="Sfidanti", value="Nessuno sorteggiato", inline=False)

    embed.add_field(name="Scadenza fight", value="Domenica ore 12:00", inline=False)
    return embed


def build_kolosseo_final_embed(final_champion_id: int) -> discord.Embed:
    kol = state["kolosseo"]
    embed = discord.Embed(
        title="🏁 Kolosseo — Campione Ufficiale",
        description="L'edizione settimanale del Kolosseo si è conclusa.",
        color=discord.Color.green(),
        timestamp=now_rome(),
    )
    embed.add_field(name="Campione ufficiale", value=mention_user(final_champion_id), inline=False)
    embed.add_field(name="Livello attuale", value=str(kol.get("champion_level") or 1), inline=True)
    embed.add_field(
        name="Premio attuale per ogni fight vinto",
        value=fmt_kama(int(kol.get("reward_per_win") or 100000)),
        inline=True,
    )
    return embed


class KolosseoSignupView(discord.ui.View):
    def __init__(self, disabled: bool = False):
        super().__init__(timeout=None)
        if disabled:
            for child in self.children:
                if isinstance(child, discord.ui.Button):
                    child.disabled = True

    @discord.ui.button(
        label="Partecipa al Kolosseo",
        style=discord.ButtonStyle.success,
        custom_id="kolosseo_join_button"
    )
    async def join_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if state.get("active_challenge") != "kolosseo" or not state["kolosseo"].get("signup_open"):
            await interaction.response.send_message("Le iscrizioni al Kolosseo non sono aperte.", ephemeral=True)
            return

        champion_id = state["kolosseo"].get("current_champion_id")
        if champion_id and interaction.user.id == champion_id:
            await interaction.response.send_message(
                "Sei già il Campione attuale, non devi iscriverti come sfidante.",
                ephemeral=True,
            )
            return

        participants: List[int] = state["kolosseo"].setdefault("participants", [])
        if interaction.user.id in participants:
            await interaction.response.send_message("Sei già iscritto al Kolosseo.", ephemeral=True)
            return

        participants.append(interaction.user.id)
        save_state()
        await interaction.response.send_message("Iscrizione registrata con successo.", ephemeral=True)


async def send_embed(embed: discord.Embed, view: Optional[discord.ui.View] = None) -> Optional[int]:
    channel = await get_target_channel()
    if not channel:
        return None
    msg = await channel.send(embed=embed, view=view)
    return msg.id


def reset_week_runtime_data(keep_champion: bool = True) -> None:
    current_champion_id = state["kolosseo"].get("current_champion_id") if keep_champion else None
    current_champion_name = state["kolosseo"].get("current_champion_name") if keep_champion else None
    champion_level = state["kolosseo"].get("champion_level") if keep_champion else 0
    reward_per_win = state["kolosseo"].get("reward_per_win") if keep_champion else 100000

    state["messages"]["challenge_message_id"] = None
    state["messages"]["signup_message_id"] = None
    state["messages"]["result_message_id"] = None

    state["dungeon"] = {
        "name": None,
        "difficulty": None,
        "reward": 0,
        "winners": [],
        "time": None,
        "opened_at": None,
        "closed_at": None,
    }

    state["kolosseo"] = {
        "signup_open": False,
        "participants": [],
        "challengers": [],
        "selected_map": None,
        "current_champion_id": current_champion_id,
        "current_champion_name": current_champion_name,
        "champion_level": champion_level,
        "reward_per_win": reward_per_win,
        "opened_at": None,
        "signup_closed_at": None,
        "closed_at": None,
    }


async def disable_kolosseo_button_message() -> None:
    message_id = state["messages"].get("signup_message_id")
    message = await fetch_message_if_possible(message_id)
    if not message:
        return
    try:
        await message.edit(view=KolosseoSignupView(disabled=True))
    except Exception:
        pass


async def open_weekly_challenge(challenge_type: Optional[str] = None, is_test: bool = False) -> None:
    if state.get("state") in {"open", "signup_closed"}:
        return

    reset_week_runtime_data(keep_champion=True)
    state["current_week"] = challenge_week_key()
    state["last_opened_at"] = now_rome().isoformat()

    if challenge_type not in CHALLENGE_TYPES:
        challenge_type = choose_weekly_challenge()

    state["active_challenge"] = challenge_type
    state["state"] = "open"
    state["challenge_history"].append(challenge_type)
    state["challenge_history"] = state["challenge_history"][-20:]

    if challenge_type == "dungeon":
        dungeon = weighted_choice(DUNGEONS, "weight")
        state["dungeon"] = {
            "name": dungeon["name"],
            "difficulty": dungeon["difficulty"],
            "reward": dungeon["reward"],
            "winners": [],
            "time": None,
            "opened_at": now_rome().isoformat(),
            "closed_at": None,
        }

        embed = build_dungeon_open_embed()
        msg_id = await send_embed(embed)
        state["messages"]["challenge_message_id"] = msg_id
        state["messages"]["result_message_id"] = msg_id
        state["auto"]["next_kolosseo_close"] = None

    elif challenge_type == "kolosseo":
        state["kolosseo"]["signup_open"] = True
        state["kolosseo"]["opened_at"] = now_rome().isoformat()

        embed = build_kolosseo_open_embed()
        view = KolosseoSignupView(disabled=False)
        msg_id = await send_embed(embed, view=view)

        state["messages"]["challenge_message_id"] = msg_id
        state["messages"]["signup_message_id"] = msg_id

        close_at = next_tuesday_8_from(now_rome())
        state["auto"]["next_kolosseo_close"] = close_at.isoformat()

    if not is_test:
        state["auto"]["next_weekly_open"] = next_monday_8(now_rome() + timedelta(minutes=1)).isoformat()

    save_state()


async def close_kolosseo_signups_and_draw() -> Dict[str, Any]:
    if state.get("active_challenge") != "kolosseo" or not state["kolosseo"].get("signup_open"):
        return {"ok": False, "reason": "Kolosseo non aperto o iscrizioni già chiuse."}

    participants: List[int] = list(dict.fromkeys(state["kolosseo"].get("participants", [])))
    champion_id = state["kolosseo"].get("current_champion_id")

    if champion_id:
        min_needed = 3
        participants = [p for p in participants if p != champion_id]
    else:
        min_needed = 4

    await disable_kolosseo_button_message()

    if len(participants) < min_needed:
        state["kolosseo"]["signup_open"] = False
        state["kolosseo"]["signup_closed_at"] = now_rome().isoformat()
        state["state"] = "signup_closed"
        save_state()

        channel = await get_target_channel()
        if channel:
            await channel.send(
                f"⚠️ Iscrizioni Kolosseo chiuse, ma partecipanti insufficienti. Minimo richiesto: **{min_needed}**."
            )
        return {"ok": False, "reason": "Partecipanti insufficienti."}

    random.shuffle(participants)

    if not champion_id:
        champion_id = participants.pop(0)
        state["kolosseo"]["current_champion_id"] = champion_id
        state["kolosseo"]["current_champion_name"] = str(champion_id)

        if int(state["kolosseo"].get("champion_level") or 0) <= 0:
            state["kolosseo"]["champion_level"] = 1

        state["kolosseo"]["reward_per_win"] = get_reward_for_champion_level(
            int(state["kolosseo"]["champion_level"])
        )

    challengers = participants[:3]
    selected_map = random.choice(KOLOSSEO_MAPS)

    state["kolosseo"]["challengers"] = challengers
    state["kolosseo"]["selected_map"] = selected_map
    state["kolosseo"]["signup_open"] = False
    state["kolosseo"]["signup_closed_at"] = now_rome().isoformat()
    state["state"] = "signup_closed"

    save_state()

    closed_embed = build_kolosseo_closed_embed()
    draw_embed = build_kolosseo_draw_embed()

    await send_embed(closed_embed)
    msg_id = await send_embed(draw_embed)
    state["messages"]["result_message_id"] = msg_id
    save_state()

    return {"ok": True}


async def finalize_dungeon(winners: List[int], tempo: str) -> None:
    state["dungeon"]["winners"] = winners
    state["dungeon"]["time"] = tempo
    state["dungeon"]["closed_at"] = now_rome().isoformat()
    state["state"] = "completed"

    embed = build_dungeon_final_embed()
    msg_id = await send_embed(embed)
    state["messages"]["result_message_id"] = msg_id
    save_state()


async def finalize_kolosseo(final_champion_id: int) -> None:
    old_champion_id = state["kolosseo"].get("current_champion_id")
    old_level = int(state["kolosseo"].get("champion_level") or 0)

    if old_champion_id and final_champion_id == old_champion_id:
        new_level = old_level + 1
        if new_level > 10:
            new_level = 1
    else:
        new_level = 1

    state["kolosseo"]["current_champion_id"] = final_champion_id
    state["kolosseo"]["current_champion_name"] = str(final_champion_id)
    state["kolosseo"]["champion_level"] = new_level
    state["kolosseo"]["reward_per_win"] = get_reward_for_champion_level(new_level)
    state["kolosseo"]["challengers"] = []
    state["kolosseo"]["participants"] = []
    state["kolosseo"]["selected_map"] = None
    state["kolosseo"]["closed_at"] = now_rome().isoformat()
    state["state"] = "completed"

    embed = build_kolosseo_final_embed(final_champion_id)
    msg_id = await send_embed(embed)
    state["messages"]["result_message_id"] = msg_id
    save_state()


@tasks.loop(seconds=20)
async def scheduler_loop() -> None:
    current = now_rome()

    test_open = state.get("tests", {}).get("scheduled_open")
    if test_open:
        dt = datetime.fromisoformat(test_open["run_at"])
        if current >= dt:
            await open_weekly_challenge(test_open["type"], is_test=True)
            state["tests"]["scheduled_open"] = None
            save_state()

    test_close = state.get("tests", {}).get("scheduled_close")
    if test_close:
        dt = datetime.fromisoformat(test_close["run_at"])
        if current >= dt:
            await close_kolosseo_signups_and_draw()
            state["tests"]["scheduled_close"] = None
            save_state()

    weekly_open = state.get("auto", {}).get("next_weekly_open")
    if weekly_open:
        dt = datetime.fromisoformat(weekly_open)
        if current >= dt:
            await open_weekly_challenge(None, is_test=False)
            save_state()

    kol_close = state.get("auto", {}).get("next_kolosseo_close")
    if (
        kol_close
        and state.get("active_challenge") == "kolosseo"
        and state["kolosseo"].get("signup_open")
    ):
        dt = datetime.fromisoformat(kol_close)
        if current >= dt:
            await close_kolosseo_signups_and_draw()
            state["auto"]["next_kolosseo_close"] = None
            save_state()


@scheduler_loop.before_loop
async def before_scheduler_loop() -> None:
    await bot.wait_until_ready()


@bot.event
async def on_ready() -> None:
    load_state()
    ensure_auto_schedule()

    bot.add_view(KolosseoSignupView())

    if SYNC_ON_START:
        try:
            if TEST_GUILD_ONLY and GUILD_ID:
                guild_obj = discord.Object(id=GUILD_ID)
                synced = await bot.tree.sync(guild=guild_obj)
                print(f"[SYNC] Guild commands synced: {len(synced)}")
            else:
                synced = await bot.tree.sync()
                print(f"[SYNC] Global commands synced: {len(synced)}")
        except Exception as e:
            print(f"[SYNC ERROR] {e}")

    if not scheduler_loop.is_running():
        scheduler_loop.start()

    print(f"Logged in as {bot.user} ({bot.user.id})")


@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.errors.MissingPermissions):
        text = "Non hai i permessi per usare questo comando."
    else:
        text = f"Errore: {error}"

    if interaction.response.is_done():
        await interaction.followup.send(text, ephemeral=True)
    else:
        await interaction.response.send_message(text, ephemeral=True)


@bot.tree.command(
    name="sfida_status",
    description="Mostra lo stato attuale della sfida.",
    guild=discord.Object(id=GUILD_ID) if GUILD_ID else None,
)
async def sfida_status(interaction: discord.Interaction):
    active = state.get("active_challenge") or "nessuna"
    st = state.get("state") or "idle"
    week = state.get("current_week") or "—"
    next_open = state.get("auto", {}).get("next_weekly_open")
    next_close = state.get("auto", {}).get("next_kolosseo_close")
    test_open = state.get("tests", {}).get("scheduled_open")
    test_close = state.get("tests", {}).get("scheduled_close")
    kol = state.get("kolosseo", {})
    history = state.get("challenge_history", [])

    text = (
        f"**Settimana:** {week}\n"
        f"**Sfida attiva:** {active}\n"
        f"**Stato:** {st}\n"
        f"**Storico ultime sfide:** {', '.join(history[-5:]) if history else '—'}\n"
        f"**Prossima apertura automatica:** {fmt_dt(datetime.fromisoformat(next_open)) if next_open else '—'}\n"
        f"**Prossima chiusura automatica Kolosseo:** {fmt_dt(datetime.fromisoformat(next_close)) if next_close else '—'}\n"
        f"**Campione attuale:** {mention_user(kol.get('current_champion_id')) if kol.get('current_champion_id') else '—'}\n"
        f"**Livello campione:** {kol.get('champion_level', 0)}\n"
        f"**Premio attuale per fight:** {fmt_kama(int(kol.get('reward_per_win') or 100000))}\n"
        f"**Mappa corrente Kolosseo:** {kol.get('selected_map') or '—'}\n"
        f"**Test apertura schedulata:** {fmt_dt(datetime.fromisoformat(test_open['run_at'])) if test_open else '—'}\n"
        f"**Test chiusura schedulata:** {fmt_dt(datetime.fromisoformat(test_close['run_at'])) if test_close else '—'}"
    )
    await interaction.response.send_message(text, ephemeral=True)


@bot.tree.command(
    name="sfida_force_start",
    description="Forza l'apertura manuale di una sfida.",
    guild=discord.Object(id=GUILD_ID) if GUILD_ID else None,
)
@admin_only()
@app_commands.describe(tipo="dungeon oppure kolosseo")
async def sfida_force_start(interaction: discord.Interaction, tipo: str):
    tipo = tipo.lower().strip()
    if tipo not in CHALLENGE_TYPES:
        await interaction.response.send_message("Tipo non valido. Usa: dungeon o kolosseo.", ephemeral=True)
        return

    await open_weekly_challenge(tipo, is_test=True)
    await interaction.response.send_message(f"Sfida aperta manualmente: **{tipo}**.", ephemeral=True)


@bot.tree.command(
    name="sfida_force_close",
    description="Marca la sfida corrente come completata.",
    guild=discord.Object(id=GUILD_ID) if GUILD_ID else None,
)
@admin_only()
async def sfida_force_close(interaction: discord.Interaction):
    state["state"] = "completed"
    state["kolosseo"]["signup_open"] = False
    state["auto"]["next_kolosseo_close"] = None
    save_state()
    await interaction.response.send_message("Sfida corrente marcata come completata.", ephemeral=True)


@bot.tree.command(
    name="sfida_schedule_in",
    description="Schedula un'apertura automatica di test tra X minuti.",
    guild=discord.Object(id=GUILD_ID) if GUILD_ID else None,
)
@admin_only()
@app_commands.describe(tipo="dungeon o kolosseo", minuti="Tra quanti minuti far partire la sfida")
async def sfida_schedule_in(interaction: discord.Interaction, tipo: str, minuti: app_commands.Range[int, 1, 10080]):
    tipo = tipo.lower().strip()
    if tipo not in CHALLENGE_TYPES:
        await interaction.response.send_message("Tipo non valido. Usa: dungeon o kolosseo.", ephemeral=True)
        return

    run_at = now_rome() + timedelta(minutes=minuti)
    state["tests"]["scheduled_open"] = {"type": tipo, "run_at": run_at.isoformat()}
    save_state()

    await interaction.response.send_message(
        f"Test schedulato: apertura **{tipo}** il **{fmt_dt(run_at)}**.",
        ephemeral=True,
    )


@bot.tree.command(
    name="sfida_schedule_test",
    description="Schedula un'apertura automatica di test a data e ora precise.",
    guild=discord.Object(id=GUILD_ID) if GUILD_ID else None,
)
@admin_only()
@app_commands.describe(tipo="dungeon o kolosseo", data_ora="Formato: YYYY-MM-DD HH:MM")
async def sfida_schedule_test(interaction: discord.Interaction, tipo: str, data_ora: str):
    tipo = tipo.lower().strip()
    if tipo not in CHALLENGE_TYPES:
        await interaction.response.send_message("Tipo non valido. Usa: dungeon o kolosseo.", ephemeral=True)
        return

    try:
        run_at = parse_local_datetime(data_ora)
    except Exception:
        await interaction.response.send_message("Formato non valido. Usa YYYY-MM-DD HH:MM", ephemeral=True)
        return

    state["tests"]["scheduled_open"] = {"type": tipo, "run_at": run_at.isoformat()}
    save_state()

    await interaction.response.send_message(
        f"Test schedulato: apertura **{tipo}** il **{fmt_dt(run_at)}**.",
        ephemeral=True,
    )


@bot.tree.command(
    name="kolosseo_schedule_close_in",
    description="Schedula la chiusura automatica di test del Kolosseo tra X minuti.",
    guild=discord.Object(id=GUILD_ID) if GUILD_ID else None,
)
@admin_only()
@app_commands.describe(minuti="Tra quanti minuti chiudere il Kolosseo")
async def kolosseo_schedule_close_in(interaction: discord.Interaction, minuti: app_commands.Range[int, 1, 10080]):
    run_at = now_rome() + timedelta(minutes=minuti)
    state["tests"]["scheduled_close"] = {"run_at": run_at.isoformat()}
    save_state()

    await interaction.response.send_message(
        f"Test schedulato: chiusura Kolosseo il **{fmt_dt(run_at)}**.",
        ephemeral=True,
    )


@bot.tree.command(
    name="kolosseo_schedule_close",
    description="Schedula la chiusura automatica di test del Kolosseo a data e ora precise.",
    guild=discord.Object(id=GUILD_ID) if GUILD_ID else None,
)
@admin_only()
@app_commands.describe(data_ora="Formato: YYYY-MM-DD HH:MM")
async def kolosseo_schedule_close(interaction: discord.Interaction, data_ora: str):
    try:
        run_at = parse_local_datetime(data_ora)
    except Exception:
        await interaction.response.send_message("Formato non valido. Usa YYYY-MM-DD HH:MM", ephemeral=True)
        return

    state["tests"]["scheduled_close"] = {"run_at": run_at.isoformat()}
    save_state()

    await interaction.response.send_message(
        f"Test schedulato: chiusura Kolosseo il **{fmt_dt(run_at)}**.",
        ephemeral=True,
    )


@bot.tree.command(
    name="scheduler_status",
    description="Mostra i job schedulati reali e di test.",
    guild=discord.Object(id=GUILD_ID) if GUILD_ID else None,
)
@admin_only()
async def scheduler_status(interaction: discord.Interaction):
    next_open = state.get("auto", {}).get("next_weekly_open")
    next_close = state.get("auto", {}).get("next_kolosseo_close")
    test_open = state.get("tests", {}).get("scheduled_open")
    test_close = state.get("tests", {}).get("scheduled_close")

    text = (
        f"**Apertura settimanale reale:** {fmt_dt(datetime.fromisoformat(next_open)) if next_open else '—'}\n"
        f"**Chiusura reale Kolosseo:** {fmt_dt(datetime.fromisoformat(next_close)) if next_close else '—'}\n"
        f"**Test apertura:** {fmt_dt(datetime.fromisoformat(test_open['run_at'])) if test_open else '—'}\n"
        f"**Test chiusura:** {fmt_dt(datetime.fromisoformat(test_close['run_at'])) if test_close else '—'}"
    )
    await interaction.response.send_message(text, ephemeral=True)


@bot.tree.command(
    name="scheduler_clear",
    description="Cancella tutti i job di test schedulati.",
    guild=discord.Object(id=GUILD_ID) if GUILD_ID else None,
)
@admin_only()
async def scheduler_clear(interaction: discord.Interaction):
    state["tests"]["scheduled_open"] = None
    state["tests"]["scheduled_close"] = None
    save_state()
    await interaction.response.send_message("Job di test cancellati.", ephemeral=True)


@bot.tree.command(
    name="dungeon_start",
    description="Apre manualmente un Dungeon Rush.",
    guild=discord.Object(id=GUILD_ID) if GUILD_ID else None,
)
@admin_only()
async def dungeon_start(interaction: discord.Interaction):
    await open_weekly_challenge("dungeon", is_test=True)
    await interaction.response.send_message("Dungeon Rush aperto manualmente.", ephemeral=True)


@bot.tree.command(
    name="dungeon_reroll",
    description="Riestrae il dungeon corrente.",
    guild=discord.Object(id=GUILD_ID) if GUILD_ID else None,
)
@admin_only()
async def dungeon_reroll(interaction: discord.Interaction):
    if state.get("active_challenge") != "dungeon":
        await interaction.response.send_message("Non c'è un Dungeon Rush attivo.", ephemeral=True)
        return

    dungeon = weighted_choice(DUNGEONS, "weight")
    state["dungeon"]["name"] = dungeon["name"]
    state["dungeon"]["difficulty"] = dungeon["difficulty"]
    state["dungeon"]["reward"] = dungeon["reward"]
    save_state()

    embed = build_dungeon_open_embed()
    await send_embed(embed)
    await interaction.response.send_message(
        f"Dungeon riestratto: **{dungeon['name']}** — premio **{fmt_kama(dungeon['reward'])}**.",
        ephemeral=True,
    )


@bot.tree.command(
    name="dungeon_finalize",
    description="Chiude il Dungeon Rush impostando vincitori e tempo.",
    guild=discord.Object(id=GUILD_ID) if GUILD_ID else None,
)
@admin_only()
@app_commands.describe(
    vincitore1="Primo vincitore",
    vincitore2="Secondo vincitore (opzionale)",
    vincitore3="Terzo vincitore (opzionale)",
    vincitore4="Quarto vincitore (opzionale)",
    tempo="Tempo registrato, es: 04:32",
)
async def dungeon_finalize(
    interaction: discord.Interaction,
    tempo: str,
    vincitore1: discord.Member,
    vincitore2: Optional[discord.Member] = None,
    vincitore3: Optional[discord.Member] = None,
    vincitore4: Optional[discord.Member] = None,
):
    if state.get("active_challenge") != "dungeon":
        await interaction.response.send_message("Non c'è un Dungeon Rush attivo.", ephemeral=True)
        return

    winners = [vincitore1.id]
    for member in [vincitore2, vincitore3, vincitore4]:
        if member and member.id not in winners:
            winners.append(member.id)

    await finalize_dungeon(winners, tempo)
    await interaction.response.send_message("Dungeon Rush finalizzato correttamente.", ephemeral=True)


@bot.tree.command(
    name="kolosseo_open",
    description="Apre manualmente il Kolosseo.",
    guild=discord.Object(id=GUILD_ID) if GUILD_ID else None,
)
@admin_only()
async def kolosseo_open(interaction: discord.Interaction):
    await open_weekly_challenge("kolosseo", is_test=True)
    await interaction.response.send_message("Kolosseo aperto manualmente.", ephemeral=True)


@bot.tree.command(
    name="kolosseo_close",
    description="Chiude manualmente le iscrizioni del Kolosseo e fa il sorteggio.",
    guild=discord.Object(id=GUILD_ID) if GUILD_ID else None,
)
@admin_only()
async def kolosseo_close(interaction: discord.Interaction):
    result = await close_kolosseo_signups_and_draw()
    if result["ok"]:
        await interaction.response.send_message("Iscrizioni Kolosseo chiuse e sorteggio completato.", ephemeral=True)
    else:
        await interaction.response.send_message(f"Operazione non completata: {result['reason']}", ephemeral=True)


@bot.tree.command(
    name="kolosseo_draw",
    description="Alias manuale per chiusura iscrizioni + sorteggio Kolosseo.",
    guild=discord.Object(id=GUILD_ID) if GUILD_ID else None,
)
@admin_only()
async def kolosseo_draw(interaction: discord.Interaction):
    result = await close_kolosseo_signups_and_draw()
    if result["ok"]:
        await interaction.response.send_message("Sorteggio Kolosseo completato.", ephemeral=True)
    else:
        await interaction.response.send_message(f"Operazione non completata: {result['reason']}", ephemeral=True)


@bot.tree.command(
    name="kolosseo_status",
    description="Mostra stato dettagliato del Kolosseo.",
    guild=discord.Object(id=GUILD_ID) if GUILD_ID else None,
)
async def kolosseo_status(interaction: discord.Interaction):
    kol = state["kolosseo"]
    participants = kol.get("participants", [])
    challengers = kol.get("challengers", [])

    text = (
        f"**Campione:** {mention_user(kol.get('current_champion_id')) if kol.get('current_champion_id') else '—'}\n"
        f"**Livello campione:** {kol.get('champion_level', 0)}\n"
        f"**Premio attuale per fight:** {fmt_kama(int(kol.get('reward_per_win') or 100000))}\n"
        f"**Mappa estratta:** {kol.get('selected_map') or '—'}\n"
        f"**Iscrizioni aperte:** {'Sì' if kol.get('signup_open') else 'No'}\n"
        f"**Partecipanti iscritti:** {len(participants)}\n"
        f"**Sfidanti estratti:** {', '.join(mention_user(x) for x in challengers) if challengers else '—'}"
    )
    await interaction.response.send_message(text, ephemeral=True)


@bot.tree.command(
    name="kolosseo_finalize",
    description="Chiude il Kolosseo impostando il campione finale.",
    guild=discord.Object(id=GUILD_ID) if GUILD_ID else None,
)
@admin_only()
@app_commands.describe(campione="Campione finale di questa edizione")
async def kolosseo_finalize(interaction: discord.Interaction, campione: discord.Member):
    if state.get("active_challenge") != "kolosseo":
        await interaction.response.send_message("Non c'è un Kolosseo attivo.", ephemeral=True)
        return

    await finalize_kolosseo(campione.id)
    await interaction.response.send_message("Kolosseo finalizzato correttamente.", ephemeral=True)


@bot.tree.command(
    name="kolosseo_reset",
    description="Resetta completamente il campione del Kolosseo.",
    guild=discord.Object(id=GUILD_ID) if GUILD_ID else None,
)
@admin_only()
async def kolosseo_reset(interaction: discord.Interaction):
    state["kolosseo"]["current_champion_id"] = None
    state["kolosseo"]["current_champion_name"] = None
    state["kolosseo"]["champion_level"] = 0
    state["kolosseo"]["reward_per_win"] = 100000
    state["kolosseo"]["participants"] = []
    state["kolosseo"]["challengers"] = []
    state["kolosseo"]["selected_map"] = None
    save_state()

    await interaction.response.send_message("Campione Kolosseo resettato.", ephemeral=True)


if __name__ == "__main__":
    load_state()
    bot.run(DISCORD_TOKEN)
