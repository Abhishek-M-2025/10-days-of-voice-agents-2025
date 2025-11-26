# ======================================================
# 💼 DAY 5: AI SALES DEVELOPMENT REP (SDR) + Lead Capture
# 🤖 "TechSkill Academy" - Auto-Lead Capture Agent
# 🚀 Features: FAQ Retrieval, Lead Qualification, JSON Database
# ======================================================

import logging
import json
import os
import asyncio
from datetime import datetime
from typing import Annotated, Optional
from dataclasses import dataclass, asdict

print("\n" + "💼" * 50)
print("🚀 AI SDR AGENT - DAY 5 ")
print("🏢 SELLING: TechSkill Academy – Cloud, AI & Data Programs")
print("💡 agent.py LOADED SUCCESSFULLY!")
print("💼" * 50 + "\n")

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
# 📂 1. KNOWLEDGE BASE (FAQ)
# ======================================================

FAQ_FILE = "academy_faq.json"
LEADS_FILE = "leads_db.json"

# Updated FAQ for "TechSkill Academy"
DEFAULT_FAQ = [
    {
        "question": "What courses do you offer?",
        "answer": "We offer AWS Cloud Practitioner Path, Microsoft Azure Fundamentals, Google Cloud Associate, Oracle Cloud Architect Associate, Data Science Foundations, Machine Learning Bootcamp, Cybersecurity Essentials, DevOps Engineer Track, and AI Voice Agent Development."
    },
    {
        "question": "How much do your courses cost?",
        "answer": "Most advanced programs such as AWS, Azure, Oracle, DevOps and Machine Learning Bootcamp cost around $250 USD."
    },
    {
        "question": "Do you offer free content?",
        "answer": "Yes! We publish weekly free tutorials on AI, cloud computing, and data fundamentals. Paid programs include certification prep, projects, labs, and mentor guidance."
    },
    {
        "question": "Do you offer corporate upskilling?",
        "answer": "Yes, TechSkill Academy provides enterprise cloud training and AI automation consulting. Pricing varies based on team size and course requirements."
    }
]

def load_knowledge_base():
    try:
        path = os.path.join(os.path.dirname(__file__), FAQ_FILE)
        if not os.path.exists(path):
            with open(path, "w", encoding='utf-8') as f:
                json.dump(DEFAULT_FAQ, f, indent=4)
        with open(path, "r", encoding='utf-8') as f:
            return json.dumps(json.load(f))
    except Exception as e:
        print(f"⚠️ Error loading FAQ: {e}")
        return ""

ACADEMY_FAQ_TEXT = load_knowledge_base()

# ======================================================
# 💾 2. LEAD DATA STRUCTURE 
# ======================================================

@dataclass
class LeadProfile:
    name: str | None = None
    company: str | None = None
    email: str | None = None
    role: str | None = None
    use_case: str | None = None
    team_size: str | None = None
    timeline: str | None = None

    def is_qualified(self):
        return all([self.name, self.email, self.use_case])

@dataclass
class Userdata:
    lead_profile: LeadProfile

# ======================================================
# 🛠️ 3. SDR TOOLS 
# ======================================================

@function_tool
async def update_lead_profile(
    ctx: RunContext[Userdata],
    name: Annotated[Optional[str], Field(description="Customer's name")] = None,
    company: Annotated[Optional[str], Field(description="Customer's company name")] = None,
    email: Annotated[Optional[str], Field(description="Customer's email address")] = None,
    role: Annotated[Optional[str], Field(description="Customer's job title")] = None,
    use_case: Annotated[Optional[str], Field(description="What course they are interested in")] = None,
    team_size: Annotated[Optional[str], Field(description="Team size")] = None,
    timeline: Annotated[Optional[str], Field(description="When they want to start")] = None,
) -> str:

    profile = ctx.userdata.lead_profile

    if name: profile.name = name
    if company: profile.company = company
    if email: profile.email = email
    if role: profile.role = role
    if use_case: profile.use_case = use_case
    if team_size: profile.team_size = team_size
    if timeline: profile.timeline = timeline

    print(f"📝 UPDATING LEAD: {profile}")
    return "Lead profile updated. Continue the conversation."

@function_tool
async def submit_lead_and_end(ctx: RunContext[Userdata]) -> str:
    profile = ctx.userdata.lead_profile

    db_path = os.path.join(os.path.dirname(__file__), LEADS_FILE)

    entry = asdict(profile)
    entry["timestamp"] = datetime.now().isoformat()

    # Load existing DB
    existing = []
    if os.path.exists(db_path):
        try:
            with open(db_path, "r") as f:
                existing = json.load(f)
        except:
            pass

    existing.append(entry)

    # Save DB
    with open(db_path, "w") as f:
        json.dump(existing, f, indent=4)

    print(f"✅ LEAD SAVED TO {LEADS_FILE}")

    return (
        f"Thanks {profile.name}, your details for the {profile.use_case} program have been saved. "
        f"Our team will reach out to you at {profile.email}. Goodbye!"
    )

# ======================================================
# 🧠 4. AGENT DEFINITION 
# ======================================================

class SDRAgent(Agent):
    def __init__(self):
        super().__init__(
            instructions=f"""
            You are **Sarah**, a warm and helpful SDR for **TechSkill Academy**.

            📘 **FAQ DATA YOU MUST USE:**
            {ACADEMY_FAQ_TEXT}

            🎯 **YOUR PRIMARY GOAL:**
            1. Help the user learn about our tech courses (AWS, Azure, ML, Data Science, DevOps, Oracle).
            2. Collect lead details:
                - Name
                - Email
                - Company
                - Role
                - Course they want (Use Case)
                - Timeline
                - Team size (optional)

            ⚙️ **RULES:**
            - Only answer using the FAQ. Do NOT make up anything else.
            - After every response, ask a follow-up question to gather details.
            - Whenever user provides personal information, call `update_lead_profile`.
            - When the user says they're done, call `submit_lead_and_end`.
            """,
            tools=[update_lead_profile, submit_lead_and_end],
        )

# ======================================================
# 🎬 ENTRYPOINT
# ======================================================

def prewarm(proc: JobProcess):
    proc.userdata["vad"] = silero.VAD.load()

async def entrypoint(ctx: JobContext):
    ctx.log_context_fields = {"room": ctx.room.name}

    print("\n" + "💼" * 25)
    print("🚀 STARTING SDR SESSION (TechSkill Academy)")

    userdata = Userdata(lead_profile=LeadProfile())

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
        agent=SDRAgent(),
        room=ctx.room,
        room_input_options=RoomInputOptions(
            noise_cancellation=noise_cancellation.BVC()
        ),
    )

    await ctx.connect()

if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint, prewarm_fnc=prewarm))
