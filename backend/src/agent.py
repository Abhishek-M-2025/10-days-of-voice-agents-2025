# ======================================================
# 🏦 DAY 6: BANK FRAUD ALERT AGENT (SQLite DB Version)
# 🛡️ "Nova Bharat Bank" - Fraud Detection & Resolution
# ======================================================

import logging
import os
import sqlite3
from datetime import datetime
from typing import Annotated, Optional
from dataclasses import dataclass

print("\n" + "🛡️" * 50)
print("🚀 NOVA BHARAT BANK – FRAUD ALERT AGENT (SQLite) INITIALIZED")
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

from livekit.plugins import murf, silero, google, deepgram, noise_cancellation
from livekit.plugins.turn_detector.multilingual import MultilingualModel

logger = logging.getLogger("agent")
load_dotenv(".env.local")

# ======================================================
# 💾 1. SQLITE DATABASE SETUP
# ======================================================

DB_FILE = "fraud_db.sqlite"

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


def db_path():
    return os.path.join(os.path.dirname(__file__), DB_FILE)


def db_conn():
    conn = sqlite3.connect(db_path(), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def seed_database():
    """Create SQLite DB + Insert Abhishek & Priya"""
    conn = db_conn()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS fraud_cases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            userName TEXT NOT NULL,
            securityIdentifier TEXT,
            cardEnding TEXT,
            transactionName TEXT,
            transactionAmount TEXT,
            transactionTime TEXT,
            transactionSource TEXT,
            case_status TEXT DEFAULT 'pending_review',
            notes TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        )
    """)

    cur.execute("SELECT COUNT(1) FROM fraud_cases")
    if cur.fetchone()[0] == 0:
        sample_data = [
            (
                "Abhishek", "98756", "5501",
                "TechSquare Electronics", "₹50,000.00 INR",
                "11:45 PM IST", "flipkart.com",
                "pending_review", "High value late-night transaction flagged."
            ),
            (
                "Priya", "54321", "8844",
                "MetroStyle Apparel", "₹9,800.00 INR",
                "3:10 PM IST", "abc@shop.com",
                "pending_review", "Unusual merchant category for this user."
            )
        ]

        cur.executemany("""
            INSERT INTO fraud_cases (
                userName, securityIdentifier, cardEnding, transactionName,
                transactionAmount, transactionTime, transactionSource,
                case_status, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, sample_data)

        conn.commit()
        print("✅ SQLite DB seeded with Abhishek & Priya")

    conn.close()


seed_database()

# ======================================================
# 🧠 2. STATE MANAGEMENT
# ======================================================

@dataclass
class Userdata:
    active_case: Optional[FraudCase] = None

# ======================================================
# 🛠️ 3. SQLITE TOOL FUNCTIONS
# ======================================================

@function_tool
async def lookup_customer(
    ctx: RunContext[Userdata],
    name: Annotated[str, Field(description="Customer name provided by user")]
) -> str:

    print(f"🔎 LOOKUP: {name}")
    try:
        conn = db_conn()
        cur = conn.cursor()

        cur.execute(
            "SELECT * FROM fraud_cases WHERE LOWER(userName) = LOWER(?) LIMIT 1",
            (name,)
        )
        row = cur.fetchone()
        conn.close()

        if not row:
            return "I couldn't find your record. Please repeat your name."

        record = dict(row)

        ctx.userdata.active_case = FraudCase(
            userName=record["userName"],
            securityIdentifier=record["securityIdentifier"],
            cardEnding=record["cardEnding"],
            transactionName=record["transactionName"],
            transactionAmount=record["transactionAmount"],
            transactionTime=record["transactionTime"],
            transactionSource=record["transactionSource"],
            case_status=record["case_status"],
            notes=record["notes"],
        )

        return (
            f"Record Found: {record['userName']}\n"
            f"Security ID Expected: {record['securityIdentifier']}\n"
            f"Flagged Transaction: {record['transactionAmount']} at "
            f"{record['transactionName']} ({record['transactionSource']}).\n"
            f"Please ask the user for their Security Identifier now."
        )

    except Exception as e:
        return f"Database Error: {str(e)}"


@function_tool
async def resolve_fraud_case(
    ctx: RunContext[Userdata],
    status: Annotated[str, Field(description="'confirmed_safe' or 'confirmed_fraud'")],
    notes: Annotated[str, Field(description="Notes from the user's confirmation")]
) -> str:

    if not ctx.userdata.active_case:
        return "No active case found."

    case = ctx.userdata.active_case
    case.case_status = status
    case.notes = notes

    try:
        conn = db_conn()
        cur = conn.cursor()

        cur.execute("""
            UPDATE fraud_cases
            SET case_status = ?, notes = ?, updated_at = datetime('now')
            WHERE userName = ?
        """, (status, notes, case.userName))

        conn.commit()

        cur.execute("SELECT * FROM fraud_cases WHERE userName = ?", (case.userName,))
        updated = dict(cur.fetchone())
        conn.close()

        print(f"✅ CASE UPDATED: {case.userName} -> {status}")

        if status == "confirmed_fraud":
            return (
                f"Fraud confirmed. Card ending {case.cardEnding} has been BLOCKED.\n"
                f"DB Updated At: {updated['updated_at']}"
            )
        else:
            return (
                f"Transaction marked SAFE. Restrictions lifted.\n"
                f"DB Updated At: {updated['updated_at']}"
            )

    except Exception as e:
        return f"Database Save Error: {str(e)}"

# ======================================================
# 🤖 4. AGENT DEFINITION (Daniel)
# ======================================================

class FraudAgent(Agent):
    def __init__(self):
        super().__init__(
            instructions="""
            You are 'Daniel', Fraud Detection Specialist at Nova Bharat Bank.

            GREETING:
            - Say: "Hello, this is Daniel from Nova Bharat Bank’s Fraud Detection Department."
            - Ask: "May I know your first name?"

            LOOKUP:
            - Immediately call lookup_customer(name).

            VERIFICATION:
            - Ask for Security Identifier.
            - If incorrect → End politely.
            - If correct → Continue.

            FRAUD CHECK:
            - Explain the flagged transaction.
            - Ask: "Did you make this transaction?"

            RESOLUTION:
            - YES → resolve_fraud_case('confirmed_safe')
            - NO → resolve_fraud_case('confirmed_fraud')

            ENDING:
            - Confirm action taken.
            - End call professionally.
            """,
            tools=[lookup_customer, resolve_fraud_case],
        )

# ======================================================
# 🎬 ENTRYPOINT
# ======================================================

def prewarm(proc: JobProcess):
    proc.userdata["vad"] = silero.VAD.load()


async def entrypoint(ctx: JobContext):
    userdata = Userdata()
    session = AgentSession(
        stt=deepgram.STT(model="nova-3"),
        llm=google.LLM(model="gemini-2.5-flash"),
        tts=murf.TTS(voice="en-US-marcus", style="Conversational", text_pacing=True),
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
