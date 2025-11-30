# -------------------------------------------------------------------------
# Day 9 – E-commerce Voice Agent Lex (ACP-Inspired)
# Fully working JSON-based backend + tool functions for LiveKit Agents
# -------------------------------------------------------------------------
import json
import logging
import os
import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Optional, Annotated

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
logger = logging.getLogger("voice_trendycart_agent")
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
logger.addHandler(handler)

load_dotenv(".env.local")

# -------------------------
# Simple Product Catalog (TrendyCart)
# -------------------------
CATALOG = [
    {
        "id": "mug-001",
        "name": "Stoneware Chai Mug",
        "description": "Hand-glazed ceramic mug perfect for masala chai.",
        "price": 200,
        "currency": "INR",
        "category": "mug",
        "color": "blue",
        "sizes": [],
    },
    {
        "id": "tshirt-501",
        "name": "White Cotton T-Shirt",
        "description": "Soft breathable T-Shirt",
        "price": 600,
        "currency": "INR",
        "category": "tshirt",
        "color": "white",
        "sizes": ["M", "L", "XL"],
    },
    {
        "id": "hoodie-001",
        "name": "Cozy Hoodie",
        "description": "Warm pullover hoodie, fleece-lined.",
        "price": 2000,
        "currency": "INR",
        "category": "hoodie",
        "color": "grey",
        "sizes": ["M", "L", "XL"],
    },
    {
        "id": "rain-001",
        "name": "Light Raincoat",
        "description": "Waterproof light raincoat, packable.",
        "price": 1299,
        "currency": "INR",
        "category": "raincoat",
        "color": "yellow",
        "sizes": ["M", "L", "XL"],
    },
    {
        "id": "rain-002",
        "name": "Heavy Duty Raincoat",
        "description": "Heavy-duty rainproof coat for monsoon.",
        "price": 2499,
        "currency": "INR",
        "category": "raincoat",
        "color": "navy",
        "sizes": ["L", "XL"],
    },
    {
        "id": "laptop-801",
        "name": "HP Victus Gaming Laptop",
        "description": "Ryzen 5 5600h variant, Rtx 3050 Graphics, 8GB RAM, gaming ready",
        "price": 65000,
        "currency": "INR",
        "category": "electronics",
        "color": "black",
        "sizes": [],
    },
    {
        "id": "laptop-802",
        "name": "Acer Aspire Lite",
        "description": "Everyday use laptop with lightweight design",
        "price": 40000,
        "currency": "INR",
        "category": "electronics",
        "color": "silver",
        "sizes": [],
    },
    {
        "id": "laptop-004",
        "name": "HP Pavilion",
        "description": "High-performance HP laptop for creators.",
        "price": 50000,
        "currency": "INR",
        "category": "laptop",
        "color": "silver",
        "sizes": [],
    },
    {
        "id": "laptop-803",
        "name": "Acer Nitro Gaming Laptop",
        "description": "Gaming laptop with RTX series GPU",
        "price": 60000,
        "currency": "INR",
        "category": "electronics",
        "color": "black",
        "sizes": [],
    },
    {
        "id": "shoe-301",
        "name": "Running Sports Shoes",
        "description": "Lightweight breathable running shoes",
        "price": 2199,
        "currency": "INR",
        "category": "shoe",
        "color": "black",
        "sizes": ["7", "8", "9", "10", "11"],
    },
    {
        "id": "shoe-302",
        "name": "White Casual Sneakers",
        "description": "Daily wear unisex sneakers",
        "price": 1899,
        "currency": "INR",
        "category": "shoe",
        "color": "white",
        "sizes": ["5", "6", "7", "8", "9"],
    },
]

ORDERS_FILE = "orders.json"

# ensure orders file exists
if not os.path.exists(ORDERS_FILE):
    with open(ORDERS_FILE, "w") as f:
        json.dump([], f)

# -------------------------
# Per-session Userdata
# -------------------------
@dataclass
class Userdata:
    player_name: Optional[str] = None
    session_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    started_at: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    cart: List[Dict] = field(default_factory=list)
    orders: List[Dict] = field(default_factory=list)
    history: List[Dict] = field(default_factory=list)

# -------------------------
# Merchant helpers
# -------------------------
def _load_all_orders() -> List[Dict]:
    try:
        with open(ORDERS_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return []

def _save_order(order: Dict):
    orders = _load_all_orders()
    orders.append(order)
    with open(ORDERS_FILE, "w") as f:
        json.dump(orders, f, indent=2)

def list_products(filters: Optional[Dict] = None) -> List[Dict]:
    filters = filters or {}
    results = []
    query = filters.get("q")
    category = filters.get("category")
    max_price = filters.get("max_price") or filters.get("to") or filters.get("max")
    min_price = filters.get("min_price") or filters.get("from") or filters.get("min")
    color = filters.get("color")
    size = filters.get("size")

    if category:
        cat = category.lower()
        if cat in ("phone", "phones", "mobile", "mobile phone", "mobiles"):
            category = "mobile"
        elif cat in ("tshirt", "t-shirts", "tees", "tee"):
            category = "tshirt"
        else:
            category = cat

    for p in CATALOG:
        ok = True
        pcat = p.get("category", "").lower()
        if category and pcat != category and category not in pcat and pcat not in category:
            ok = False
        if max_price:
            try:
                if p.get("price", 0) > int(max_price):
                    ok = False
            except Exception:
                pass
        if min_price:
            try:
                if p.get("price", 0) < int(min_price):
                    ok = False
            except Exception:
                pass
        if color and p.get("color") != color:
            ok = False
        if size and (not p.get("sizes") or size not in p.get("sizes")):
            ok = False
        if query:
            q = query.lower()
            if "phone" in q or "mobile" in q:
                if p.get("category") != "mobile":
                    ok = False
            else:
                if q not in p.get("name", "").lower() and q not in p.get("description", "").lower():
                    ok = False
        if ok:
            results.append(p)
    return results

def find_product_by_ref(ref_text: str, candidates: Optional[List[Dict]] = None) -> Optional[Dict]:
    ref = (ref_text or "").lower().strip()
    cand = candidates if candidates is not None else CATALOG
    ordinals = {"first": 0, "second": 1, "third": 2, "fourth": 3}

    for word, idx in ordinals.items():
        if word in ref and idx < len(cand):
            return cand[idx]

    for p in cand:
        if p["id"].lower() == ref:
            return p

    for p in cand:
        if p.get("color") and p["color"] in ref and p.get("category") and p["category"] in ref:
            return p

    for p in cand:
        if p["name"].lower() in ref or any(w in p["name"].lower() for w in ref.split()):
            return p

    for token in ref.split():
        if token.isdigit():
            idx = int(token) - 1
            if 0 <= idx < len(cand):
                return cand[idx]

    return None

def create_order_object(line_items: List[Dict], currency: str = "INR") -> Dict:
    items = []
    total = 0
    for li in line_items:
        pid = li.get("product_id")
        qty = int(li.get("quantity", 1))
        prod = next((p for p in CATALOG if p["id"] == pid), None)
        if not prod:
            raise ValueError(f"Product {pid} not found")
        line_total = prod["price"] * qty
        total += line_total
        items.append({
            "product_id": pid,
            "name": prod["name"],
            "unit_price": prod["price"],
            "quantity": qty,
            "line_total": line_total,
            "attrs": li.get("attrs", {}),
        })
    order = {
        "id": f"order-{str(uuid.uuid4())[:8]}",
        "items": items,
        "total": total,
        "currency": currency,
        "created_at": datetime.utcnow().isoformat() + "Z",
    }
    _save_order(order)
    return order

def get_most_recent_order() -> Optional[Dict]:
    all_orders = _load_all_orders()
    if not all_orders:
        return None
    return all_orders[-1]

# -------------------------
# Agent Tools
# -------------------------
@function_tool
async def show_catalog(
    ctx: RunContext[Userdata],
    q: Annotated[Optional[str], Field(description="Search query (optional)", default=None)] = None,
    category: Annotated[Optional[str], Field(description="Category (optional)", default=None)] = None,
    max_price: Annotated[Optional[int], Field(description="Maximum price (optional)", default=None)] = None,
    color: Annotated[Optional[str], Field(description="Color (optional)", default=None)] = None,
) -> str:
    filters = {"q": q, "category": category, "max_price": max_price, "color": color}
    prods = list_products({k: v for k, v in filters.items() if v is not None})
    if not prods:
        return "Sorry — I couldn't find any items that match. Want to try a different search?"
    lines = [f"Here are the top {min(4, len(prods))} items at TrendyCart:"]
    for idx, p in enumerate(prods[:4], start=1):
        size_info = f" (sizes: {', '.join(p['sizes'])})" if p.get('sizes') else ""
        lines.append(f"{idx}. {p['name']} — {p['price']} {p['currency']} (id: {p['id']}){size_info}")
    lines.append("You can say: 'I want the second item in size M' or 'add mug-001 to my cart, quantity 2'.")
    return "\n".join(lines)

@function_tool
async def add_to_cart(
    ctx: RunContext[Userdata],
    product_ref: Annotated[str, Field(description="Reference to product: id, name, or spoken ref")],
    quantity: Annotated[int, Field(description="Quantity", default=1)] = 1,
    size: Annotated[Optional[str], Field(description="Size (optional)", default=None)] = None,
) -> str:
    userdata = ctx.userdata
    prod = find_product_by_ref(product_ref)
    if not prod:
        return "I couldn't understand which product you meant. Try using the product id or say 'show catalog'."
    userdata.cart.append({
        "product_id": prod["id"],
        "quantity": int(quantity),
        "attrs": {"size": size} if size else {},
    })
    userdata.history.append({
        "time": datetime.utcnow().isoformat() + "Z",
        "action": "add_to_cart",
        "product_id": prod["id"],
        "quantity": int(quantity),
    })
    return f"Added {quantity} x {prod['name']} to your cart. What's next?"

@function_tool
async def show_cart(ctx: RunContext[Userdata]) -> str:
    userdata = ctx.userdata
    if not userdata.cart:
        return "Your cart is empty. Say 'show catalog' to browse items."
    lines = ["Items in your cart:"]
    total = 0
    for li in userdata.cart:
        p = next((x for x in CATALOG if x["id"] == li["product_id"]), None)
        if not p:
            continue
        line_total = p["price"] * li.get("quantity", 1)
        total += line_total
        sz = li.get("attrs", {}).get("size")
        sz_text = f", size {sz}" if sz else ""
        lines.append(f"- {p['name']} x {li['quantity']}{sz_text}: {line_total} INR")
    lines.append(f"Cart total: {total} INR")
    lines.append("Say 'place my order' to checkout or 'clear cart' to empty the cart.")
    return "\n".join(lines)

@function_tool
async def clear_cart(ctx: RunContext[Userdata]) -> str:
    userdata = ctx.userdata
    userdata.cart = []
    userdata.history.append({"time": datetime.utcnow().isoformat() + "Z", "action": "clear_cart"})
    return "Your cart has been cleared. What would you like to do next?"

@function_tool
async def place_order(
    ctx: RunContext[Userdata],
    confirm: Annotated[bool, Field(description="Confirm order placement", default=True)] = True,
) -> str:
    userdata = ctx.userdata
    if not userdata.cart:
        return "Your cart is empty — nothing to place. Want to browse items?"
    line_items = [{"product_id": li["product_id"], "quantity": li.get("quantity", 1), "attrs": li.get("attrs", {})} for li in userdata.cart]
    order = create_order_object(line_items)
    userdata.orders.append(order)
    userdata.history.append({"time": datetime.utcnow().isoformat() + "Z", "action": "place_order", "order_id": order["id"]})
    userdata.cart = []
    return f"Order placed. Order ID {order['id']}. Total {order['total']} {order['currency']}. What next?"

@function_tool
async def last_order(ctx: RunContext[Userdata]) -> str:
    ord = get_most_recent_order()
    if not ord:
        return "You have no past orders yet."
    lines = [f"Most recent order: {ord['id']} — {ord['created_at']}"]
    for it in ord['items']:
        lines.append(f"- {it['name']} x {it['quantity']}: {it['line_total']} {ord['currency']}")
    lines.append(f"Total: {ord['total']} {ord['currency']}")
    return "\n".join(lines)

# -------------------------
# The Agent (Lex)
# -------------------------
class GameMasterAgent(Agent):
    def __init__(self):
        instructions = """
        You are 'Lex', the friendly shopkeeper and voice assistant for TrendyCart.
        Universe: Modern Indian shop selling mugs, hoodies, tees, and trending gadgets.
        Tone: Warm, helpful, slightly witty; short sentences for TTS clarity.
        Role: Help browse catalog, add items to cart, place orders, review orders.

        Rules:
            - Use tools: show catalog, add to cart, show cart, place order, last order, clear cart.
            - Keep continuity using session userdata.
            - Include product id and price when presenting options.
        """
        super().__init__(
            instructions=instructions,
            tools=[show_catalog, add_to_cart, show_cart, clear_cart, place_order, last_order],
        )

# -------------------------
# Entrypoint & Prewarm
# -------------------------
def prewarm(proc: JobProcess):
    try:
        proc.userdata["vad"] = silero.VAD.load()
    except Exception:
        logger.warning("VAD prewarm failed; continuing without preloaded VAD.")

async def entrypoint(ctx: JobContext):
    ctx.log_context_fields = {"room": ctx.room.name}
    logger.info("\n" + "🛒" * 6)
    logger.info("🚀 STARTING VOICE COMMERCE AGENT - Lex at TrendyCart")
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
