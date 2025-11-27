# ======================================================
# 🏦 DAY 6: BANK FRAUD ALERT AGENT
# 🛡️ "Nova Bharat Bank" - Fraud Detection & Resolution
# ======================================================

import logging
import json
import os
from datetime import datetime
from typing import Annotated, Optional
from dataclasses import dataclass, asdict

print("\n" + "🛡️" * 50)
print("🚀 NOVA BHARAT BANK – FRAUD ALERT AGENT INITIALIZED")
print("📚 TASKS: Verify Identity -> Check Transaction -> Update DB")
print("🛡️" * 50 + "\n")

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
# 💾 1. DATABASE SETUP (Mock Data)
# ======================================================

DB_FILE = "fraud_db.json"

@dataclass
class FraudCase:
    userName: str
    securityIdentifier: str
    cardEnding: str
    transactionName: str
    transactionAmount: str
    transactionTime: str
    transactionSource: str
    case_status: str = "pending_review"
    notes: str = ""

def seed_database():
    path = os.path.join(os.path.dirname(__file__), DB_FILE)
    if not os.path.exists(path):
        sample_data = [
            {
                "userName": "Abhishek",
                "securityIdentifier": "98756",
                "cardEnding": "5501",
                "transactionName": "TechSquare Electronics",
                "transactionAmount": "₹50,000.00 INR",
                "transactionTime": "11:45 PM IST",
                "transactionSource": "flipkart.com",
                "case_status": "pending_review",
                "notes": "High value late-night transaction flagged."
            },
            {
                "userName": "Priya",
                "securityIdentifier": "54321",
                "cardEnding": "8844",
                "transactionName": "MetroStyle Apparel",
                "transactionAmount": "₹9,800.00 INR",
                "transactionTime": "3:10 PM IST",
                "transactionSource": "abc@shop.com",
                "case_status": "pending_review",
                "notes": "Unusual merchant category for this user."
            }
        ]
        with open(path, "w", encoding='utf-8') as f:
            json.dump(sample_data, f, indent=4)
        print(f"✅ Database seeded at {DB_FILE}")

seed_database()

# ======================================================
# 🧠 2. STATE MANAGEMENT
# ======================================================

@dataclass
class Userdata:
    active_case: Optional[FraudCase] = None

# ======================================================
# 🛠️ 3. FRAUD AGENT TOOLS
# ======================================================

@function_tool
async def lookup_customer(
    ctx: RunContext[Userdata],
    name: Annotated[str, Field(description="The name the user provides")]
) -> str:
    """Looks up a customer in the fraud database by name."""
    name = name.strip().lower()
    path = os.path.join(os.path.dirname(__file__), DB_FILE)
    print(f"🔎 LOOKING UP: {name}")

    try:
        with open(path, "r", encoding='utf-8') as f:
            data = json.load(f)

        found_record = next((item for item in data if item["userName"].lower() == name), None)

        if found_record:
            ctx.userdata.active_case = FraudCase(**found_record)
            return (
                f"Record Found.\n"
                f"User: {found_record['userName']}\n"
                f"Security ID (Expected): {found_record['securityIdentifier']}\n"
                f"Transaction Details: {found_record['transactionAmount']} at "
                f"{found_record['transactionName']} ({found_record['transactionSource']})\n"
                f"Ask the user for their Security Identifier now."
            )
        else:
            return "User not found. Please repeat your name."

    except Exception as e:
        return f"Database error: {str(e)}"

@function_tool
async def resolve_fraud_case(
    ctx: RunContext[Userdata],
    status: Annotated[str, Field(description="The final status: 'confirmed_safe' or 'confirmed_fraud'")],
    notes: Annotated[str, Field(description="A brief summary of the user's response")]
) -> str:
    if not ctx.userdata.active_case:
        return "Error: No active case selected."

    case = ctx.userdata.active_case
    case.case_status = status
    case.notes = notes

    path = os.path.join(os.path.dirname(__file__), DB_FILE)
    try:
        with open(path, "r", encoding='utf-8') as f:
            data = json.load(f)

        for i, item in enumerate(data):
            if item["userName"] == case.userName:
                data[i] = asdict(case)
                break

        with open(path, "w", encoding='utf-8') as f:
            json.dump(data, f, indent=4)

        print(f"✅ CASE UPDATED: {case.userName} -> {status}")

        if status == "confirmed_fraud":
            return f"Case marked as FRAUD. Inform user: Card ending {case.cardEnding} is blocked."
        else:
            return "Case marked SAFE. Restrictions lifted."

    except Exception as e:
        return f"Error saving to DB: {e}"

# ======================================================
# 🤖 4. AGENT DEFINITION
# ======================================================

class FraudAgent(Agent):
    def __init__(self):
        super().__init__(
            instructions="""
            You are 'Daniel', a Fraud Detection Specialist at Nova Bharat Bank.

            GREETING:
            - Say: "Hello, I'm Daniel, Fraud Detection Specialist from Nova Bharat Bank."
            - Inform this call is about a security alert.
            - Ask: “Am I speaking with the account holder? May I have your first name?”

            LOOKUP:
            - Use lookup_customer tool immediately when user gives their name.

            VERIFICATION:
            - Ask for their Security Identifier.
            - If incorrect: End call politely.
            - If correct: Continue.

            TRANSACTION REVIEW:
            - Read flagged transaction details.
            - Ask: “Did you make this transaction?”

            RESOLUTION:
            - YES → resolve_fraud_case('confirmed_safe')
            - NO → resolve_fraud_case('confirmed_fraud')

            CLOSING:
            - Confirm card status.
            - End call professionally.

            Tone: Calm, confident, professional.
            """,
            tools=[lookup_customer, resolve_fraud_case],
        )

# ======================================================
# 🎬 ENTRYPOINT
# ======================================================

def prewarm(proc: JobProcess):
    proc.userdata["vad"] = silero.VAD.load()

async def entrypoint(ctx: JobContext):
    ctx.log_context_fields = {"room": ctx.room.name}
    userdata = Userdata()

    session = AgentSession(
        stt=deepgram.STT(model="nova-3"),
        llm=google.LLM(model="gemini-2.5-flash"),
        tts=murf.TTS(
            voice="en-US-marcus",
            style="Conversational",
            text_pacing=True,
        ),
        turn_detection=MultilingualModel(),
        vad=ctx.proc.userdata["vad"],
        userdata=userdata,
    )

    await session.start(
        agent=FraudAgent(),
        room=ctx.room,
        room_input_options=RoomInputOptions(noise_cancellation=noise_cancellation.BVC())
    )

    await ctx.connect()

if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint, prewarm_fnc=prewarm))
