"""
Day 8 — Voice Game Master (D&D-Style Adventure) Agent
Two universes included in one agent:
- "A Shadow over Brinmere"
- "Mystic Valley"

Tools:
 - select_game(game_name)
 - set_username(username)
 - start_adventure(player_name=None)
 - get_scene()
 - player_action(action)
 - show_journal()
 - restart_adventure()

Run: python day8_voice_game_master_both_games.py

Make sure .env.local contains required API keys for STT/LLM/TTS plugins.
"""

import os
import json
import uuid
import logging
import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Optional

# Third-party LiveKit agent imports (adapt if SDK path changes)
from dotenv import load_dotenv
from pydantic import Field

from livekit.agents import (
    Agent,
    AgentSession,
    JobContext,
    JobProcess,
    RoomInputOptions,
    WorkerOptions,
    cli,
    function_tool,
    RunContext,
)

from livekit.plugins import murf, silero, google, deepgram, noise_cancellation
from livekit.plugins.turn_detector.multilingual import MultilingualModel

# -------------------------
# Logging
# -------------------------
logger = logging.getLogger("voice_game_master_both")
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
logger.addHandler(handler)

load_dotenv(".env.local")

# -------------------------
# WORLD: Two universes with 7-8 scene nodes each
# -------------------------
WORLD = {
    # ----------------- Brinmere (7-8 turns) -----------------
    "brinmere_intro": {
        "title": "A Shadow over Brinmere",
        "desc": (
            "You awake on the damp shore of Brinmere, the moon a thin silver crescent. "
            "A ruined watchtower smolders a short distance inland, and a narrow path "
            "leads towards a cluster of cottages to the east. In the water beside you "
            "lies a small, carved wooden box, half-buried in sand."
        ),
        "choices": {
            "inspect_box": {"desc": "Inspect the carved wooden box at the water's edge.", "result_scene": "brinmere_box"},
            "approach_tower": {"desc": "Head inland towards the smoldering watchtower.", "result_scene": "brinmere_tower"},
            "walk_to_cottages": {"desc": "Follow the path east towards the cottages.", "result_scene": "brinmere_cottages"},
        },
    },
    "brinmere_box": {
        "title": "The Box",
        "desc": (
            "The box is warm despite the night air. Inside is a folded scrap of parchment "
            "with a hatch-marked map and the words: 'Beneath the tower, the latch sings.' "
            "As you read, a faint whisper seems to come from the tower."
        ),
        "choices": {
            "take_map": {"desc": "Take the map and keep it.", "result_scene": "brinmere_toward_tower", "effects": {"add_journal": "Found map fragment: 'Beneath the tower, the latch sings.'"}},
            "leave_box": {"desc": "Leave the box where it is.", "result_scene": "brinmere_intro"},
        },
    },
    "brinmere_tower": {
        "title": "The Watchtower",
        "desc": (
            "The watchtower's stonework is cracked and warm embers glow within. An iron "
            "latch covers a hatch at the base — it looks old but recently used."
        ),
        "choices": {
            "try_latch": {"desc": "Try the iron latch.", "result_scene": "brinmere_latch_test"},
            "search_rubble": {"desc": "Search the nearby rubble for another entrance.", "result_scene": "brinmere_secret_entrance"},
            "retreat_shore": {"desc": "Step back to the shoreline.", "result_scene": "brinmere_intro"},
        },
    },
    "brinmere_toward_tower": {
        "title": "Toward the Tower",
        "desc": (
            "Clutching the map, you approach the watchtower. The map's marks align with the hatch at the base."
        ),
        "choices": {
            "use_map_on_latch": {"desc": "Use the map clue and try the hatch carefully.", "result_scene": "brinmere_latch_open", "effects": {"add_journal": "Used map clue to open the hatch."}},
            "search_around": {"desc": "Search for another entrance.", "result_scene": "brinmere_secret_entrance"},
            "go_back": {"desc": "Return to the shore.", "result_scene": "brinmere_intro"},
        },
    },
    "brinmere_latch_test": {
        "title": "A Bad Twist",
        "desc": (
            "You twist the latch without heed — the mechanism sticks, and the effort sends a shiver through the ground. "
            "Something stirs within the tower."
        ),
        "choices": {
            "run_away": {"desc": "Run back to the shore.", "result_scene": "brinmere_intro"},
            "stand_and_prepare": {"desc": "Stand and prepare for whatever emerges.", "result_scene": "brinmere_combat"},
        },
    },
    "brinmere_secret_entrance": {
        "title": "A Narrow Gap",
        "desc": (
            "Behind a pile of rubble you find a narrow gap and old rope leading downward. It smells of cold iron and something briny."
        ),
        "choices": {
            "squeeze_in": {"desc": "Squeeze through the gap and follow the rope down.", "result_scene": "brinmere_cellar"},
            "mark_and_return": {"desc": "Mark the spot and return to the shore.", "result_scene": "brinmere_intro"},
        },
    },
    "brinmere_latch_open": {
        "title": "The Hatch Opens",
        "desc": (
            "With the map's guidance the latch yields and the hatch opens with a breath of cold air; steps lead down into an ancient cellar."
        ),
        "choices": {
            "descend": {"desc": "Descend into the cellar.", "result_scene": "brinmere_cellar"},
            "close_hatch": {"desc": "Close the hatch and reconsider.", "result_scene": "brinmere_toward_tower"},
        },
    },
    "brinmere_cellar": {
        "title": "Cellar of Echoes",
        "desc": (
            "The cellar opens into a circular chamber where runes glow faintly. At the center is a stone plinth and upon it a small brass key and a sealed scroll."
        ),
        "choices": {
            "take_key": {"desc": "Pick up the brass key.", "result_scene": "brinmere_cellar_key", "effects": {"add_inventory": "brass_key", "add_journal": "Found brass key on plinth."}},
            "open_scroll": {"desc": "Break the seal and read the scroll.", "result_scene": "brinmere_scroll_reveal", "effects": {"add_journal": "Scroll reads: 'The tide remembers what the villagers forget.'"}},
            "leave": {"desc": "Leave the cellar and close the hatch behind you.", "result_scene": "brinmere_intro"},
        },
    },
    "brinmere_cellar_key": {
        "title": "Key in Hand",
        "desc": (
            "With the key in your hand the runes dim and a hidden panel slides open, revealing a small statue that begins to hum."
        ),
        "choices": {
            "pledge_help": {"desc": "Pledge to return what was taken.", "result_scene": "brinmere_reward", "effects": {"add_journal": "You pledged to return what was taken."}},
            "refuse": {"desc": "Refuse and pocket the key.", "result_scene": "brinmere_cursed_key", "effects": {"add_journal": "You pocketed the key; a weight grows in your pocket."}},
        },
    },
    "brinmere_scroll_reveal": {
        "title": "The Scroll",
        "desc": (
            "The scroll tells of an heirloom taken by a water spirit beneath the tower. It hints the brass key 'speaks' when offered with truth."
        ),
        "choices": {
            "search_key": {"desc": "Search the plinth for a key.", "result_scene": "brinmere_cellar_key"},
            "leave_quiet": {"desc": "Leave quietly and keep the knowledge.", "result_scene": "brinmere_intro"},
        },
    },
    "brinmere_combat": {
        "title": "Something Emerges",
        "desc": (
            "A hunched, brine-soaked creature scrambles out from the tower. You must act quickly."
        ),
        "choices": {
            "fight": {"desc": "Fight the creature.", "result_scene": "brinmere_fight_win"},
            "flee": {"desc": "Flee back to the shore.", "result_scene": "brinmere_intro"},
        },
    },
    "brinmere_fight_win": {
        "title": "After the Scuffle",
        "desc": (
            "You fend off the creature. On the ground lies a small engraved locket — likely the heirloom."
        ),
        "choices": {
            "take_locket": {"desc": "Take the locket and examine it.", "result_scene": "brinmere_reward", "effects": {"add_inventory": "engraved_locket", "add_journal": "Recovered an engraved locket."}},
            "leave_locket": {"desc": "Leave the locket and tend to your wounds.", "result_scene": "brinmere_intro"},
        },
    },
    "brinmere_reward": {
        "title": "A Minor Resolution",
        "desc": (
            "A small peace settles over Brinmere. The arc closes for now."
        ),
        "choices": {
            "end_session": {"desc": "Conclude the mini-arc.", "result_scene": "brinmere_intro"},
            "continue": {"desc": "Keep exploring.", "result_scene": "brinmere_intro"},
        },
    },
    "brinmere_cursed_key": {
        "title": "A Weight in the Pocket",
        "desc": (
            "The brass key glows coldly. A weight tugs at your thoughts."
        ),
        "choices": {
            "seek_redemption": {"desc": "Seek a way to make amends.", "result_scene": "brinmere_reward"},
            "bury_key": {"desc": "Bury the key and hope the weight fades.", "result_scene": "brinmere_intro"},
        },
    },

    # ----------------- Mystic Valley (7-8 turns) -----------------
    "mystic_intro": {
        "title": "Mystic Valley",
        "desc": (
            "You awaken on a grassy hill at dawn, the valley stretched before you in mist. "
            "A silver pendant rests against your chest, warm with a strange energy. "
            "A winding path leads down toward a willow grove; to the east you hear the murmur of a village."
        ),
        "choices": {
            "follow_path": {"desc": "Follow the winding path toward the willow grove.", "result_scene": "mystic_willow"},
            "go_to_village": {"desc": "Head east toward the village sounds.", "result_scene": "mystic_village"},
            "inspect_pendant": {"desc": "Inspect the silver pendant.", "result_scene": "mystic_pendant"},
        },
    },
    "mystic_pendant": {
        "title": "The Pendant",
        "desc": (
            "The pendant vibrates softly; when you hold it up you glimpse a distant memory of a shattered tower and laughter lost at sea."
        ),
        "choices": {
            "keep_pendant": {"desc": "Keep the pendant and continue.", "result_scene": "mystic_willow", "effects": {"add_journal": "Pendant resonates with memory."}},
            "discard": {"desc": "Discard the pendant.", "result_scene": "mystic_intro"},
        },
    },
    "mystic_willow": {
        "title": "Willow Grove",
        "desc": (
            "Beneath the willow's hanging branches, a small fox with star-like fur limps toward you. "
            "It seems drawn to your pendant."
        ),
        "choices": {
            "help_fox": {"desc": "Help the fox.", "result_scene": "mystic_companion", "effects": {"add_journal": "Helped a star-fox; gained companion."}},
            "ignore_fox": {"desc": "Ignore it and explore the grove.", "result_scene": "mystic_glade"},
            "search_beneath": {"desc": "Search beneath the roots.", "result_scene": "mystic_hidden_altar"},
        },
    },
    "mystic_companion": {
        "title": "New Companion",
        "desc": (
            "The fox heals in the pendant's glow and bows to you. It seems loyal; it will accompany you."
        ),
        "choices": {
            "follow_deeper": {"desc": "Follow the deeper path with your companion.", "result_scene": "mystic_stone_circle"},
            "go_to_village": {"desc": "Head to the village with the fox.", "result_scene": "mystic_village"},
        },
    },
    "mystic_glade": {
        "title": "Secret Glade",
        "desc": (
            "A hidden glade opens up with a small stone circle. A faint song drifts through the air."
        ),
        "choices": {
            "listen_song": {"desc": "Sit and listen to the song.", "result_scene": "mystic_revelation", "effects": {"add_journal": "Heard the valley's old song."}},
            "leave_glade": {"desc": "Leave and return to the willow.", "result_scene": "mystic_willow"},
        },
    },
    "mystic_hidden_altar": {
        "title": "Hidden Altar",
        "desc": (
            "Under the roots you find a mossy altar with a small crystal shard embedded in it."
        ),
        "choices": {
            "take_shard": {"desc": "Take the crystal shard.", "result_scene": "mystic_shard_taken", "effects": {"add_inventory": "crystal_shard", "add_journal": "Recovered a crystal shard."}},
            "leave_shard": {"desc": "Leave it undisturbed.", "result_scene": "mystic_willow"},
        },
    },
    "mystic_stone_circle": {
        "title": "Stone Circle",
        "desc": (
            "A ring of standing stones hums with energy when you and your companion step inside."
        ),
        "choices": {
            "invoke_circle": {"desc": "Invoke the circle's power.", "result_scene": "mystic_invoked", "effects": {"add_journal": "Invoked stone circle; felt a surge."}},
            "step_out": {"desc": "Step out and continue your journey.", "result_scene": "mystic_village"},
        },
    },
    "mystic_village": {
        "title": "Valley Village",
        "desc": (
            "The village wakes slowly. An old woman eyes your pendant and mentions a legend of scattered shards."
        ),
        "choices": {
            "ask_about_shards": {"desc": "Ask the elder about the shards.", "result_scene": "mystic_elder", "effects": {"add_journal": "Learned of shards legend."}},
            "rest_in_inn": {"desc": "Rest at the inn.", "result_scene": "mystic_rest"},
            "leave_village": {"desc": "Leave the village and explore farther.", "result_scene": "mystic_stone_circle"},
        },
    },
    "mystic_shard_taken": {
        "title": "Shard in Hand",
        "desc": (
            "The shard pulses in your palm. The pendant resonates; you sense a second shard nearby."
        ),
        "choices": {
            "seek_second_shard": {"desc": "Search for the second shard.", "result_scene": "mystic_village"},
            "hide_shard": {"desc": "Hide the shard for later.", "result_scene": "mystic_willow"},
        },
    },
    "mystic_invoked": {
        "title": "Circle Awoken",
        "desc": (
            "Energy flows through you for a moment and the valley's path becomes clearer."
        ),
        "choices": {
            "follow_path": {"desc": "Follow the newly revealed path.", "result_scene": "mystic_hidden_altar"},
            "give_thanks": {"desc": "Give thanks to the stones and move on.", "result_scene": "mystic_village"},
        },
    },
    "mystic_revelation": {
        "title": "The Song's Truth",
        "desc": (
            "The song reveals a piece of history: a nameless spirit once shattered a crystal to hide its grief."
        ),
        "choices": {
            "seek_spirit": {"desc": "Seek the spirit who shattered the crystal.", "result_scene": "mystic_spirit"},
            "ponder_song": {"desc": "Stay and ponder the meaning.", "result_scene": "mystic_willow"},
        },
    },
    "mystic_elder": {
        "title": "The Elder",
        "desc": (
            "The elder remembers a fragment hidden within the willow grove; she warns that truth has a cost."
        ),
        "choices": {
            "accept_task": {"desc": "Accept the elder's task to restore the shards.", "result_scene": "mystic_stone_circle", "effects": {"add_journal": "Accepted elder's quest to restore shards."}},
            "refuse_task": {"desc": "Refuse and go your own way.", "result_scene": "mystic_intro"},
        },
    },
    "mystic_rest": {
        "title": "Rest",
        "desc": (
            "At the inn you rest and recover; the pendant feels heavier in your pocket."
        ),
        "choices": {
            "wake_and_leave": {"desc": "Wake and leave the village.", "result_scene": "mystic_willow"},
            "stay_longer": {"desc": "Stay and ask around the village more.", "result_scene": "mystic_village"},
        },
    },
    "mystic_spirit": {
        "title": "The Spirit",
        "desc": (
            "A gentle water-spirit appears near a pool; it speaks in riddles but its sorrow is clear."
        ),
        "choices": {
            "console_spirit": {"desc": "Console the spirit.", "result_scene": "mystic_reward", "effects": {"add_journal": "Consoled the water-spirit."}},
            "challenge_spirit": {"desc": "Challenge it for answers.", "result_scene": "mystic_challenge"},
        },
    },
    "mystic_challenge": {
        "title": "A Test of Wills",
        "desc": (
            "The spirit sends a trial of illusions. You must stand steady."
        ),
        "choices": {
            "endure": {"desc": "Endure the illusions.", "result_scene": "mystic_reward"},
            "flee": {"desc": "Flee the trial.", "result_scene": "mystic_intro"},
        },
    },
    "mystic_reward": {
        "title": "A Minor Resolution",
        "desc": (
            "The spirit calms and reveals the location of another shard; a small arc closes for now."
        ),
        "choices": {
            "end_session": {"desc": "Finish this session and return home.", "result_scene": "mystic_intro"},
            "keep_exploring": {"desc": "Continue to search for shards.", "result_scene": "mystic_village"},
        },
    },
}

# -------------------------
# Per-session userdata dataclass
# -------------------------
@dataclass
class Userdata:
    player_name: Optional[str] = None
    selected_game: Optional[str] = None  # 'brinmere' or 'mystic' or full key names
    current_scene: str = "brinmere_intro"
    history: List[Dict] = field(default_factory=list)
    journal: List[str] = field(default_factory=list)
    inventory: List[str] = field(default_factory=list)
    named_npcs: Dict[str, str] = field(default_factory=dict)
    choices_made: List[str] = field(default_factory=list)
    session_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    started_at: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")

# -------------------------
# Helper functions
# -------------------------
def _scene_key_for_user(scene_key: str, userdata: Userdata) -> str:
    """
    Normalizes scene key per selected game.
    Internally we keep scene keys unique (prefix by brinmere_ or mystic_).
    """
    return scene_key

def scene_text(scene_key: str, userdata: Userdata) -> str:
    scene = WORLD.get(scene_key)
    if not scene:
        return "You are in a featureless void. What do you do?"
    desc = f"{scene['desc']}\n\nChoices:\n"
    for cid, cmeta in scene.get("choices", {}).items():
        desc += f"- {cmeta['desc']} (say: {cid})\n"
    desc += "\nWhat do you do?"
    return desc

def apply_effects(effects: dict, userdata: Userdata):
    if not effects:
        return
    if "add_journal" in effects:
        userdata.journal.append(effects["add_journal"])
    if "add_inventory" in effects:
        userdata.inventory.append(effects["add_inventory"])

def summarize_scene_transition(old_scene: str, action_key: str, result_scene: str, userdata: Userdata) -> str:
    entry = {
        "from": old_scene,
        "action": action_key,
        "to": result_scene,
        "time": datetime.utcnow().isoformat() + "Z",
    }
    userdata.history.append(entry)
    userdata.choices_made.append(action_key)
    return f"You chose '{action_key}'."

# -------------------------
# Tools
# -------------------------
@function_tool
async def select_game(ctx: RunContext[Userdata], game_name: str = Field(..., description="Choose: 'A Shadow over Brinmere' or 'Mystic Valley'")) -> str:
    userdata = ctx.userdata
    name = (game_name or "").strip()
    # Accept short names too
    if name.lower() in ["brinmere", "a shadow over brinmere", "a shadow", "brinmere game"]:
        sel = "brinmere"
        userdata.selected_game = "brinmere"
        userdata.current_scene = "brinmere_intro"
    elif name.lower() in ["mystic valley", "mystic", "valley", "mystic valley game"]:
        sel = "mystic"
        userdata.selected_game = "mystic"
        userdata.current_scene = "mystic_intro"
    else:
        return "That game does not exist. Please choose either 'A Shadow over Brinmere' or 'Mystic Valley'."
    # persist minimal info into userdata (Agent runtime persists Userdata per session)
    return f"Great choice! You selected: {game_name}. What name should I call you in this adventure?"

@function_tool
async def set_username(ctx: RunContext[Userdata], username: str = Field(..., description="Player in-game name")) -> str:
    userdata = ctx.userdata
    userdata.player_name = (username or "").strip() or "Traveler"
    # set the starting scene if not already set
    if not userdata.current_scene:
        userdata.current_scene = "brinmere_intro"
    opening = f"Welcome, {userdata.player_name}. Beginning your adventure now.\n\n"
    # attach the intro of the selected game
    if userdata.selected_game == "mystic":
        opening += scene_text("mystic_intro", userdata)
    else:
        opening += scene_text("brinmere_intro", userdata)
    if not opening.endswith("What do you do?"):
        opening += "\nWhat do you do?"
    return opening

@function_tool
async def start_adventure(ctx: RunContext[Userdata], player_name: Optional[str] = Field(default=None, description="Player name")) -> str:
    userdata = ctx.userdata
    if player_name:
        userdata.player_name = player_name
    # If game not selected yet, prompt user
    if not userdata.selected_game:
        return "Welcome to Game Master! My name is KIO. Which game do you want to play now? (A Shadow over Brinmere / Mystic Valley)"
    # Initialize session fields
    userdata.history = []
    userdata.journal = []
    userdata.inventory = []
    userdata.named_npcs = {}
    userdata.choices_made = []
    userdata.session_id = str(uuid.uuid4())[:8]
    userdata.started_at = datetime.utcnow().isoformat() + "Z"
    # Start appropriate intro
    if userdata.selected_game == "mystic":
        intro_scene = "mystic_intro"
    else:
        intro_scene = "brinmere_intro"
    userdata.current_scene = intro_scene
    opening = f"Greetings {userdata.player_name or 'traveler'}. Welcome to '{WORLD[intro_scene]['title']}'.\n\n" + scene_text(intro_scene, userdata)
    if not opening.endswith("What do you do?"):
        opening += "\nWhat do you do?"
    return opening

@function_tool
async def get_scene(ctx: RunContext[Userdata]) -> str:
    userdata = ctx.userdata
    scene_k = userdata.current_scene or ("mystic_intro" if userdata.selected_game == "mystic" else "brinmere_intro")
    return scene_text(scene_k, userdata)

@function_tool
async def player_action(ctx: RunContext[Userdata], action: str = Field(..., description="Player spoken action or short action code")) -> str:
    userdata = ctx.userdata
    current = userdata.current_scene or ("mystic_intro" if userdata.selected_game == "mystic" else "brinmere_intro")
    scene = WORLD.get(current)
    action_text = (action or "").strip()

    # Attempt direct choice-key match
    chosen_key = None
    if scene and action_text.lower() in (scene.get("choices") or {}):
        chosen_key = action_text.lower()

    # Fuzzy match: check if action_text contains a choice id or early words from description
    if not chosen_key and scene:
        for cid, cmeta in (scene.get("choices") or {}).items():
            desc = cmeta.get("desc", "").lower()
            if cid in action_text.lower() or any(w in action_text.lower() for w in desc.split()[:4]):
                chosen_key = cid
                break

    # Keyword scan fallback
    if not chosen_key and scene:
        for cid, cmeta in (scene.get("choices") or {}).items():
            for keyword in cmeta.get("desc", "").lower().split():
                if keyword and keyword in action_text.lower():
                    chosen_key = cid
                    break
            if chosen_key:
                break

    # If no choice resolved
    if not chosen_key:
        resp = (
            "I didn't quite catch that action for this situation. Try one of the listed choices or use a simple phrase like 'inspect the box' or 'go to the tower'.\n\n"
            + scene_text(current, userdata)
        )
        return resp

    # Apply chosen
    choice_meta = scene["choices"].get(chosen_key)
    result_scene = choice_meta.get("result_scene", current)
    effects = choice_meta.get("effects", None)

    apply_effects(effects or {}, userdata)
    _note = summarize_scene_transition(current, chosen_key, result_scene, userdata)

    userdata.current_scene = result_scene
    next_desc = scene_text(result_scene, userdata)

    persona_pre = "KIO, the Game Master, replies:\n\n"
    reply = f"{persona_pre}{_note}\n\n{next_desc}"
    if not reply.endswith("What do you do?"):
        reply += "\nWhat do you do?"
    return reply

@function_tool
async def show_journal(ctx: RunContext[Userdata]) -> str:
    userdata = ctx.userdata
    lines = []
    lines.append(f"Session: {userdata.session_id} | Started at: {userdata.started_at}")
    if userdata.selected_game:
        lines.append(f"Selected Game: {userdata.selected_game}")
    if userdata.player_name:
        lines.append(f"Player: {userdata.player_name}")
    if userdata.journal:
        lines.append("\nJournal entries:")
        for j in userdata.journal:
            lines.append(f"- {j}")
    else:
        lines.append("\nJournal is empty.")
    if userdata.inventory:
        lines.append("\nInventory:")
        for it in userdata.inventory:
            lines.append(f"- {it}")
    else:
        lines.append("\nNo items in inventory.")
    lines.append("\nRecent choices:")
    for h in userdata.history[-8:]:
        lines.append(f"- {h['time']} | from {h['from']} -> {h['to']} via {h['action']}")
    lines.append("\nWhat do you do?")
    return "\n".join(lines)

@function_tool
async def restart_adventure(ctx: RunContext[Userdata]) -> str:
    userdata = ctx.userdata
    userdata.current_scene = "brinmere_intro"
    userdata.history = []
    userdata.journal = []
    userdata.inventory = []
    userdata.named_npcs = {}
    userdata.choices_made = []
    userdata.session_id = str(uuid.uuid4())[:8]
    userdata.started_at = datetime.utcnow().isoformat() + "Z"
    userdata.selected_game = None
    userdata.player_name = None
    greeting = "The world resets. You may choose a new adventure. Which game do you want to play? (A Shadow over Brinmere / Mystic Valley)"
    return greeting

# -------------------------
# GameMaster Agent class
# -------------------------
class GameMasterAgent(Agent):
    def __init__(self):
        instructions = """
        You are 'KIO', the Game Master (GM) for a voice-first adventure service.
        Behavior:
         - Greet the player with: "Welcome to Game Master! My name is KIO. Which game do you want to play now?"
         - Wait for the player to call the select_game tool (or to say one of the two game names).
         - After game selection, ask for the player's in-game name (use set_username).
         - After username set, use start_adventure to begin the intro.
         - Use the tools provided to advance the story and maintain continuity.
         - Each GM reply must end with 'What do you do?'
         - Be concise enough for TTS, but evocative.
        """
        super().__init__(instructions=instructions, tools=[select_game, set_username, start_adventure, get_scene, player_action, show_journal, restart_adventure])

# -------------------------
# Prewarm and Entrypoint
# -------------------------
def prewarm(proc: JobProcess):
    # Try to preload VAD
    try:
        proc.userdata["vad"] = silero.VAD.load()
        logger.info("Preloaded Silero VAD")
    except Exception:
        logger.warning("VAD prewarm failed; continuing without preloaded VAD.")

async def entrypoint(ctx: JobContext):
    ctx.log_context_fields = {"room": ctx.room.name}
    logger.info("\n" + "🎲" * 6)
    logger.info("🚀 STARTING VOICE GAME MASTER (Dual-Game agent)")

    userdata = Userdata()

    session = AgentSession(
        stt=deepgram.STT(model=os.getenv("DEEPGRAM_MODEL", "nova-3")),
        llm=google.LLM(model=os.getenv("GOOGLE_LLM_MODEL", "gemini-2.5-flash")),
        tts=murf.TTS(
            voice=os.getenv("MURF_VOICE", "en-US-marcus"),
            style=os.getenv("MURF_STYLE", "Conversational"),
            text_pacing=True,
        ),
        turn_detection=MultilingualModel(),
        vad=ctx.proc.userdata.get("vad"),
        userdata=userdata,
    )

    await session.start(
        agent=GameMasterAgent(),
        room=ctx.room,
        room_input_options=RoomInputOptions(noise_cancellation=noise_cancellation.BVC()),
    )

    await ctx.connect()

if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint, prewarm_fnc=prewarm))
