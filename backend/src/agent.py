# ====================================================== ========== ========== ========== ==========
# 🧪 DAY 4: TEACH-THE-TUTOR (CHEMISTRY EDITION) : ACTIVE RECALL COACH
# 🚀 Features: Metals, Non-metals, Physical Properties, Acids & Bases, Chemical Properties
# ====================================================== ========== ========== ========== ==========

import logging
import json
import os
import asyncio
from typing import Annotated, Literal, Optional
from dataclasses import dataclass

print("\n" + "🧪" * 50)
print("🚀 CHEMISTRY TUTOR - DAY 4 TUTORIAL")
print("💡 agent.py LOADED SUCCESSFULLY!")
print("🧪" * 50 + "\n")

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

# 🔌 PLUGINS
from livekit.plugins import murf, silero, google, deepgram, noise_cancellation
from livekit.plugins.turn_detector.multilingual import MultilingualModel

logger = logging.getLogger("agent")
load_dotenv(".env.local")

# ======================================================
# 📚 KNOWLEDGE BASE (CHEMISTRY DATA)
# ======================================================

CONTENT_FILE = "chemistry_content.json"

DEFAULT_CONTENT = [
  {
    "id": "metals_nonmetals",
    "title": "Metals and Non-metals",
    "summary": "Metals are shiny, malleable, good conductors of heat and electricity. Non-metals are dull, brittle (if solid), and poor conductors. They differ in physical and chemical properties.",
    "sample_question": "State two physical properties of metals and two of non-metals."
  },
  {
    "id": "physical_properties",
    "title": "Physical Properties of Matter",
    "summary": "Physical properties include color, hardness, boiling point, melting point, conductivity, and density. These properties help identify substances without changing their composition.",
    "sample_question": "What is the difference between melting point and boiling point?"
  },
  {
    "id": "acids_bases",
    "title": "Acids and Bases",
    "summary": "Acids have pH < 7 and turn blue litmus red. Bases have pH > 7 and turn red litmus blue. Neutralization occurs when acids and bases react to form salt and water.",
    "sample_question": "What happens in a neutralization reaction? Give an example."
  },
  {
    "id": "chemical_reactions",
    "title": "Chemical Reactions",
    "summary": "A chemical reaction involves breaking and forming chemical bonds, producing new substances. Types include combination, decomposition, displacement, and double displacement.",
    "sample_question": "Define a decomposition reaction with an example."
  }
]


def load_content():
    try:
        path = os.path.join(os.path.dirname(__file__), CONTENT_FILE)
        if not os.path.exists(path):
            print(f"⚠️ {CONTENT_FILE} not found. Generating chemistry data...")
            with open(path, "w", encoding='utf-8') as f:
                json.dump(DEFAULT_CONTENT, f, indent=4)
            print("✅ Chemistry content file created successfully.")
        with open(path, "r", encoding='utf-8') as f:
            data = json.load(f)
            return data
    except Exception as e:
        print(f"⚠️ Error managing content file: {e}")
        return []

COURSE_CONTENT = load_content()

# ======================================================
# 🧠 STATE MANAGEMENT
# ======================================================

@dataclass
class TutorState:
    current_topic_id: str | None = None
    current_topic_data: dict | None = None
    mode: Literal["learn", "quiz", "teach_back"] = "learn"

    def set_topic(self, topic_id: str):
        topic = next((item for item in COURSE_CONTENT if item["id"] == topic_id), None)
        if topic:
            self.current_topic_id = topic_id
            self.current_topic_data = topic
            return True
        return False

@dataclass
class Userdata:
    tutor_state: TutorState
    agent_session: Optional[AgentSession] = None

# ======================================================
# 🛠️ TUTOR TOOLS
# ======================================================

@function_tool
async def select_topic(
    ctx: RunContext[Userdata],
    topic_id: Annotated[str, Field(description="The ID of the chemistry topic (e.g., 'metals_nonmetals', 'acids_bases')")]
) -> str:
    state = ctx.userdata.tutor_state
    success = state.set_topic(topic_id.lower())
    if success:
        return f"Topic set to {state.current_topic_data['title']}. Ask the user if they want to 'Learn', be 'Quizzed', or 'Teach it back'."
    else:
        available = ", ".join([t["id"] for t in COURSE_CONTENT])
        return f"Topic not found. Available topics are: {available}"

@function_tool
async def set_learning_mode(
    ctx: RunContext[Userdata],
    mode: Annotated[str, Field(description="Switch to: 'learn', 'quiz', or 'teach_back'")]
) -> str:
    state = ctx.userdata.tutor_state
    state.mode = mode.lower()
    agent_session = ctx.userdata.agent_session
    if agent_session:
        if state.mode == "learn":
            agent_session.tts.update_options(voice="en-US-matthew", style="Promo")
            instruction = f"Mode: LEARN. Explain: {state.current_topic_data['summary']}"
        elif state.mode == "quiz":
            agent_session.tts.update_options(voice="en-US-alicia", style="Conversational")
            instruction = f"Mode: QUIZ. Ask this question: {state.current_topic_data['sample_question']}"
        elif state.mode == "teach_back":
            agent_session.tts.update_options(voice="en-US-ken", style="Promo")
            instruction = "Mode: TEACH_BACK. Ask the user to explain the concept as if you are the beginner."
        else:
            return "Invalid mode."
    else:
        instruction = "Voice switch failed (Session not found)."

    print(f"🔄 SWITCHING MODE -> {state.mode.upper()}")
    return f"Switched to {state.mode} mode. {instruction}"

@function_tool
async def evaluate_teaching(
    ctx: RunContext[Userdata],
    user_explanation: Annotated[str, Field(description="The explanation given by the user during teach-back")]
) -> str:
    print(f"📝 EVALUATING EXPLANATION: {user_explanation}")
    # Simple evaluation: score based on presence of key words from topic summary
    summary = (ctx.userdata.tutor_state.current_topic_data or {}).get("summary", "")
    score = 0
    if not user_explanation:
        return "No explanation provided."
    # crude keyword match
    keywords = [w.lower().strip(".,") for w in summary.split() if len(w) > 4][:6]
    matches = sum(1 for kw in keywords if kw in user_explanation.lower())
    score = min(10, max(1, int((matches / max(1, len(keywords))) * 10)))
    feedback = "Good work!" if score >= 7 else "Needs improvement."
    corrections = ""
    # For brevity, give a short correction if obvious mismatch
    if "acid" in summary.lower() and "ph" not in user_explanation.lower():
        corrections = "Hint: Mention pH and litmus behaviour for acids/bases."
    return f"Score: {score}/10. {feedback} {corrections}"

# ======================================================
# 🧠 AGENT DEFINITION
# ======================================================

class TutorAgent(Agent):
    def __init__(self):
        topic_list = ", ".join([f"{t['id']} ({t['title']})" for t in COURSE_CONTENT])
        super().__init__(
            instructions=f"""
            You are a **Chemistry Tutor** designed to help users master concepts like Metals, Non-metals, Acids, Bases, and Chemical Reactions.

            📚 **AVAILABLE TOPICS:** {topic_list}

            🔄 **MODES:**
            1. **LEARN (Matthew):** Explain the concept.
            2. **QUIZ (Alicia):** Ask a question.
            3. **TEACH_BACK (Ken):** Listen as the user explains the topic.

            Start by asking what chemistry topic they want to study.
            Use the tools to switch modes.
            """,
            tools=[select_topic, set_learning_mode, evaluate_teaching],
        )

# ======================================================
# 🎬 ENTRYPOINT
# ======================================================

def prewarm(proc: JobProcess):
    proc.userdata["vad"] = silero.VAD.load()

async def entrypoint(ctx: JobContext):
    ctx.log_context_fields = {"room": ctx.room.name}

    print("\n" + "🧪" * 25)
    print("🚀 STARTING CHEMISTRY TUTOR SESSION")
    print(f"📚 Loaded {len(COURSE_CONTENT)} topics from Knowledge Base")

    userdata = Userdata(tutor_state=TutorState())

    session = AgentSession(
        stt=deepgram.STT(model="nova-3"),
        llm=google.LLM(model="gemini-2.5-flash"),
        tts=murf.TTS(
            voice="en-US-matthew",
            style="Promo",
            text_pacing=True,
        ),
        turn_detection=MultilingualModel(),
        vad=ctx.proc.userdata["vad"],
        userdata=userdata,
    )

    userdata.agent_session = session

    await session.start(
        agent=TutorAgent(),
        room=ctx.room,
        room_input_options=RoomInputOptions(
            noise_cancellation=noise_cancellation.BVC()
        ),
    )

    await ctx.connect()

if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint, prewarm_fnc=prewarm))
