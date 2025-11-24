# ======================================================
# 🌿 DAY 3 - HEALTH & WELLNESS VOICE COMPANION 
# ======================================================

import logging
import json
import os
import asyncio
from datetime import datetime
from typing import Annotated, Literal, List, Optional
from dataclasses import dataclass, field, asdict

print("\n" + "🌿" * 50)
print("🚀 WELLNESS COMPANION READY")
print("💡 agent.py LOADED SUCCESSFULLY!")
print("🌿" * 50 + "\n")

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
    metrics,
    MetricsCollectedEvent,
    RunContext,
    function_tool,
)

from livekit.plugins import murf, silero, google, deepgram, noise_cancellation
from livekit.plugins.turn_detector.multilingual import MultilingualModel

logger = logging.getLogger("agent")
load_dotenv(".env.local")

# ======================================================
# 🧠 STATE MANAGEMENT & DATA STRUCTURES
# ======================================================

@dataclass
class CheckInState:
    mood: str | None = None
    energy: str | None = None
    objectives: list[str] = field(default_factory=list)
    advice_given: str | None = None
    
    def is_complete(self) -> bool:
        return all([
            self.mood is not None,
            self.energy is not None,
            len(self.objectives) > 0
        ])
    
    def to_dict(self) -> dict:
        return asdict(self)

@dataclass
class Userdata:
    current_checkin: CheckInState
    history_summary: str
    session_start: datetime = field(default_factory=datetime.now)

# ======================================================
# 💾 PERSISTENCE LAYERS (JSON LOGGING)
# ======================================================

WELLNESS_LOG_FILE = "wellness_log.json"

def get_log_path():
    base_dir = os.path.dirname(__file__)
    backend_dir = os.path.abspath(os.path.join(base_dir, ".."))
    return os.path.join(backend_dir, WELLNESS_LOG_FILE)

def load_history() -> list:
    path = get_log_path()
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding='utf-8') as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except Exception:
        return []

def save_checkin_entry(entry: CheckInState) -> None:
    path = get_log_path()
    history = load_history()
    
    record = {
        "timestamp": datetime.now().isoformat(),
        "mood": entry.mood,
        "energy": entry.energy,
        "objectives": entry.objectives,
        "summary": entry.advice_given
    }
    
    history.append(record)
    
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding='utf-8') as f:
        json.dump(history, f, indent=4, ensure_ascii=False)

# ======================================================
# 🛠️ WELLNESS AGENT TOOLS
# ======================================================

@function_tool
async def record_mood_and_energy(
    ctx: RunContext[Userdata],
    mood: Annotated[str, Field(description="The user's emotional state")],
    energy: Annotated[str, Field(description="The user's energy level")],
) -> str:
    ctx.userdata.current_checkin.mood = mood
    ctx.userdata.current_checkin.energy = energy
    return f"I've noted that you are feeling {mood} with {energy} energy."

@function_tool
async def record_objectives(
    ctx: RunContext[Userdata],
    objectives: Annotated[list[str], Field(description="List of daily goals")],
) -> str:
    ctx.userdata.current_checkin.objectives = objectives
    return "I've written down your goals for the day."

@function_tool
async def complete_checkin(
    ctx: RunContext[Userdata],
    final_advice_summary: Annotated[str, Field(description="Summary of advice")],
) -> str:
    state = ctx.userdata.current_checkin
    state.advice_given = final_advice_summary
    
    if not state.is_complete():
        return "I still need your mood, energy, and at least one goal."

    save_checkin_entry(state)

    recap = f"""
    Here is your recap for today:
    You are feeling {state.mood} and your energy is {state.energy}.
    Your goals: {', '.join(state.objectives)}.
    
    Reminder: {final_advice_summary}
    
    Your wellness log has been updated.
    """
    return recap

# ======================================================
# 🧠 AGENT DEFINITION
# ======================================================

class WellnessAgent(Agent):
    def __init__(self, history_context: str):
        super().__init__(
            instructions=f"""
            You are a supportive Daily Wellness Companion.
            
            Context from previous sessions:
            {history_context}
            
            Goals:
            1. Ask for mood & energy.
            2. Ask for 1–3 daily goals.
            3. Provide simple, non-medical suggestions.
            4. Summarize the session & call complete_checkin.
            
            Safety:
            - Do NOT diagnose or treat medical conditions.
            - Recommend professional help for severe emotional distress.
            """,
            tools=[
                record_mood_and_energy,
                record_objectives,
                complete_checkin,
            ],
        )

# ======================================================
# 🎬 ENTRYPOINT & INITIALIZATION
# ======================================================

def prewarm(proc: JobProcess):
    proc.userdata["vad"] = silero.VAD.load()

async def entrypoint(ctx: JobContext):
    history = load_history()
    history_summary = "No previous history found."

    if history:
        last_entry = history[-1]
        history_summary = (
            f"Last check-in: {last_entry.get('timestamp', 'unknown date')}. "
            f"Mood: {last_entry.get('mood')} | Energy: {last_entry.get('energy')}. "
            f"Goals: {', '.join(last_entry.get('objectives', []))}."
        )

    userdata = Userdata(
        current_checkin=CheckInState(),
        history_summary=history_summary
    )

    session = AgentSession(
        stt=deepgram.STT(model="nova-3"),
        llm=google.LLM(model="gemini-2.5-flash"),
        tts=murf.TTS(
            voice="en-US-natalie",
            style="Promo",
            text_pacing=True,
        ),
        turn_detection=MultilingualModel(),
        vad=ctx.proc.userdata["vad"],
        userdata=userdata,
    )
    
    await session.start(
        agent=WellnessAgent(history_context=history_summary),
        room=ctx.room,
        room_input_options=RoomInputOptions(
            noise_cancellation=noise_cancellation.BVC()
        ),
    )

    await ctx.connect()

if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint, prewarm_fnc=prewarm))
