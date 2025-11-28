# ======================================================
# 🛒 DAY 7: AI GROCERY VOICE AGENT — JSON DATABASE VERSION
# 🤖 "NovaGrocery" – Smart Shopping Assistant (Lyra)
# 🚀 Features:
#   - Grocery Search
#   - Shopping Cart
#   - Auto Order Status Simulation
#   - Recipe Ingredients Lookup
#   - JSON Storage (NO SQLite)
# ======================================================

import logging
import json
import os
import asyncio
from datetime import datetime
from dataclasses import dataclass, asdict
from typing import Annotated, Optional

print("\n" + "🛒" * 50)
print("🚀 AI GROCERY AGENT - NOVAGROCERY")
print("🤖 AGENT: Lyra")
print("💡 agent.py LOADED SUCCESSFULLY!")
print("🛒" * 50 + "\n")

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
# 📁 1. JSON STORAGE CONFIG
# ======================================================

DATA_DIR = "data"
CATALOG_FILE = os.path.join(DATA_DIR, "catalog.json")
ORDERS_FILE = os.path.join(DATA_DIR, "orders.json")
ORDER_ITEMS_FILE = os.path.join(DATA_DIR, "order_items.json")
RECIPES_FILE = os.path.join(DATA_DIR, "recipes.json")

os.makedirs(DATA_DIR, exist_ok=True)

# ======================================================
# 📦 2. DEFAULT DATA FOR FRESH INSTALLS
# ======================================================

DEFAULT_CATALOG = [
    {"id": 1, "name": "Milk", "price": 2.5},
    {"id": 2, "name": "Bread", "price": 1.5},
    {"id": 3, "name": "Eggs", "price": 3.0},
    {"id": 4, "name": "Bananas", "price": 1.2},
    {"id": 5, "name": "Apples", "price": 1.8},
    {"id": 6, "name": "Rice", "price": 4.0},
    {"id": 7, "name": "Chicken Breast", "price": 6.5},
    {"id": 8, "name": "Butter", "price": 2.8},
]

DEFAULT_RECIPES = [
    {"name": "Pancakes", "ingredients": ["Milk", "Eggs", "Bread"]},
    {"name": "Fruit Salad", "ingredients": ["Apples", "Bananas"]},
]

DEFAULT_ORDERS = []
DEFAULT_ITEMS = []

# ======================================================
# 📌 Load/Save JSON Helpers
# ======================================================

def load_json(path, default):
    if not os.path.exists(path):
        with open(path, "w") as f:
            json.dump(default, f, indent=4)
    with open(path, "r") as f:
        return json.load(f)

def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=4)

# ======================================================
# 🧠 Load All JSON Data Into Memory
# ======================================================

catalog = load_json(CATALOG_FILE, DEFAULT_CATALOG)
orders = load_json(ORDERS_FILE, DEFAULT_ORDERS)
order_items = load_json(ORDER_ITEMS_FILE, DEFAULT_ITEMS)
recipes = load_json(RECIPES_FILE, DEFAULT_RECIPES)

# ======================================================
# 🔍 Utility Functions
# ======================================================

def get_item_by_name(name):
    for item in catalog:
        if item["name"].lower() == name.lower():
            return item
    return None

def get_order(order_id):
    for o in orders:
        if o["id"] == order_id:
            return o
    return None

# ======================================================
# 🛒 3. CART / ORDER INGREDIENTS
# ======================================================

@dataclass
class CartItem:
    item_id: int
    name: str
    price: float
    quantity: int

@dataclass
class Cart:
    items: list

    def add_item(self, product, qty):
        for i in self.items:
            if i.item_id == product["id"]:
                i.quantity += qty
                return
        self.items.append(CartItem(product["id"], product["name"], product["price"], qty))

    def remove_item(self, product_name):
        self.items = [i for i in self.items if i.name.lower() != product_name.lower()]

    def update_qty(self, product_name, qty):
        for i in self.items:
            if i.name.lower() == product_name.lower():
                i.quantity = qty

    def total(self):
        return sum(i.price * i.quantity for i in self.items)

    def is_empty(self):
        return len(self.items) == 0

    def to_json(self):
        return [asdict(i) for i in self.items]

# ======================================================
# 🧠 4. USER DATA
# ======================================================

@dataclass
class Userdata:
    cart: Cart
    active_order_id: Optional[int] = None

# ======================================================
# 🔧 5. FUNCTIONS (ALL LLM CALLS)
# ======================================================

@function_tool
async def find_item(
    ctx: RunContext[Userdata],
    name: Annotated[str, Field(description="Item to search")]
):
    item = get_item_by_name(name)
    if item:
        return f"{item['name']} is available for ${item['price']}."
    return f"Sorry, {name} is not available."

@function_tool
async def add_to_cart(
    ctx: RunContext[Userdata],
    name: Annotated[str, Field()],
    quantity: Annotated[int, Field()],
):
    product = get_item_by_name(name)
    if not product:
        return f"{name} is not available."

    ctx.userdata.cart.add_item(product, quantity)
    return f"Added {quantity} × {product['name']} to your cart."

@function_tool
async def remove_from_cart(
    ctx: RunContext[Userdata],
    name: Annotated[str, Field()],
):
    ctx.userdata.cart.remove_item(name)
    return f"Removed {name} from your cart."

@function_tool
async def update_cart_quantity(
    ctx: RunContext[Userdata],
    name: Annotated[str, Field()],
    quantity: Annotated[int, Field()],
):
    ctx.userdata.cart.update_qty(name, quantity)
    return f"Updated {name} quantity to {quantity}."

@function_tool
async def view_cart(ctx: RunContext[Userdata]):
    cart = ctx.userdata.cart
    if cart.is_empty():
        return "Your cart is empty."
    msg = "🛒 Your cart contains:\n"
    for i in cart.items:
        msg += f"- {i.name}: {i.quantity} × ${i.price}\n"
    msg += f"\nTotal: ${cart.total():.2f}"
    return msg

@function_tool
async def get_recipe(
    ctx: RunContext[Userdata],
    name: Annotated[str, Field()]
):
    for r in recipes:
        if r["name"].lower() == name.lower():
            ing = ", ".join(r["ingredients"])
            return f"{name} requires: {ing}"
    return f"No recipe found for {name}"

@function_tool
async def infer_ingredients(
    ctx: RunContext[Userdata],
    name: Annotated[str, Field()]
):
    for r in recipes:
        if r["name"].lower() == name.lower():
            for ing in r["ingredients"]:
                product = get_item_by_name(ing)
                if product:
                    ctx.userdata.cart.add_item(product, 1)
            return f"Added all ingredients for {name} to your cart."
    return f"No recipe found."

# ======================================================
# 📦 PLACE ORDER
# ======================================================

@function_tool
async def place_order(ctx: RunContext[Userdata]):
    cart = ctx.userdata.cart

    if cart.is_empty():
        return "Your cart is empty. Add items before placing an order."

    order_id = len(orders) + 1

    order = {
        "id": order_id,
        "created_at": datetime.now().isoformat(),
        "status": "received",
        "total_price": cart.total(),
    }
    orders.append(order)

    for item in cart.items:
        order_items.append({
            "order_id": order_id,
            "item_id": item.item_id,
            "name": item.name,
            "price": item.price,
            "quantity": item.quantity,
        })

    save_json(ORDERS_FILE, orders)
    save_json(ORDER_ITEMS_FILE, order_items)

    ctx.userdata.active_order_id = order_id
    ctx.userdata.cart = Cart(items=[])

    return f"Your order #{order_id} has been placed! Total: ${order['total_price']}."

# ======================================================
# ❌ CANCEL ORDER
# ======================================================

@function_tool
async def cancel_order(
    ctx: RunContext[Userdata],
    order_id: Annotated[int, Field()]
):
    order = get_order(order_id)
    if not order:
        return f"No order found."

    if order["status"] == "delivered":
        return "Order already delivered."

    order["status"] = "cancelled"
    save_json(ORDERS_FILE, orders)

    return f"Order #{order_id} cancelled successfully."

# ======================================================
# 📊 ORDER STATUS
# ======================================================

@function_tool
async def get_order_status(
    ctx: RunContext[Userdata],
    order_id: Annotated[int, Field()]
):
    order = get_order(order_id)
    if not order:
        return "Order not found."

    return f"Order #{order_id} is currently {order['status']}."

# ======================================================
# 📋 ORDER HISTORY
# ======================================================

@function_tool
async def order_history(ctx: RunContext[Userdata]):
    if not orders:
        return "No past orders."

    msg = "🧾 Your order history:\n"
    for o in orders:
        msg += f"- Order #{o['id']} — {o['status']} — ${o['total_price']}\n"
    return msg

# ======================================================
# 🚚 AUTO ORDER STATUS SIMULATION LOOP
# ======================================================

async def order_status_simulator():
    while True:
        await asyncio.sleep(5)

        changed = False

        for order in orders:
            if order["status"] in ["cancelled", "delivered"]:
                continue

            next_status = {
                "received": "confirmed",
                "confirmed": "shipped",
                "shipped": "out_for_delivery",
                "out_for_delivery": "delivered",
            }.get(order["status"])

            if next_status:
                order["status"] = next_status
                changed = True

        if changed:
            save_json(ORDERS_FILE, orders)

# ======================================================
# 🧠 6. AGENT DEFINITION (Lyra)
# ======================================================

class GroceryAgent(Agent):
    def __init__(self):
        super().__init__(
            instructions=f"""
You are **Lyra**, an intelligent, friendly grocery assistant for **NovaGrocery**.

Your abilities:
- Help customers find items.
- Add/remove/update cart items.
- Suggest recipes.
- Auto-infer ingredients.
- Create and manage orders.
- Respond using simple, human-friendly language.

Always:
- Keep responses short and helpful.
- Confirm actions clearly.
- Offer next-step guidance.
            """,
            tools=[
                find_item,
                add_to_cart,
                remove_from_cart,
                update_cart_quantity,
                view_cart,
                get_recipe,
                infer_ingredients,
                place_order,
                cancel_order,
                get_order_status,
                order_history,
            ],
        )

# ======================================================
# 🎬 ENTRYPOINT
# ======================================================

def prewarm(proc: JobProcess):
    proc.userdata["vad"] = silero.VAD.load()

async def entrypoint(ctx: JobContext):

    asyncio.create_task(order_status_simulator())

    userdata = Userdata(cart=Cart(items=[]))

    session = AgentSession(
        stt=deepgram.STT(model="nova-3"),
        llm=google.LLM(model="gemini-2.5-flash"),
        tts=murf.TTS(
            voice="en-US-natalie",  # Female voice
            style="Promo",
            text_pacing=True,
        ),
        turn_detection=MultilingualModel(),
        vad=ctx.proc.userdata["vad"],
        userdata=userdata,
    )

    await session.start(
        agent=GroceryAgent(),
        room=ctx.room,
        room_input_options=RoomInputOptions(
            noise_cancellation=noise_cancellation.BVC(),
        ),
    )

    await ctx.connect()


if __name__ == "__main__":
    cli.run_app(
        WorkerOptions(entrypoint_fnc=entrypoint, prewarm_fnc=prewarm)
    )  
