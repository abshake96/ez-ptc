"""ez-ptc — Async tool definitions example.

Demonstrates defining async tools with @ez_tool and how the executor
transparently handles coroutines, event loops, and parallel execution.

No API keys required.

Usage:
    uv run python examples/advanced/example_async_tools.py
"""

import asyncio

from ez_ptc import Toolkit, ez_tool


# ── Async tool definitions ────────────────────────────────────────────


@ez_tool
async def fetch_user(user_id: int) -> dict:
    """Fetch a user by ID (simulated async I/O).

    Args:
        user_id: The user's ID
    """
    await asyncio.sleep(0.1)  # simulate network delay
    users = {
        1: {"id": 1, "name": "Alice", "role": "admin"},
        2: {"id": 2, "name": "Bob", "role": "user"},
        3: {"id": 3, "name": "Charlie", "role": "user"},
    }
    return users.get(user_id, {"id": user_id, "name": "Unknown", "role": "none"})


@ez_tool
async def fetch_orders(user_id: int) -> list:
    """Fetch orders for a user (simulated async I/O).

    Args:
        user_id: The user's ID
    """
    await asyncio.sleep(0.1)  # simulate network delay
    orders = {
        1: [{"order_id": 101, "item": "Laptop", "amount": 999.99}],
        2: [{"order_id": 201, "item": "Book", "amount": 14.99},
            {"order_id": 202, "item": "Headphones", "amount": 79.99}],
    }
    return orders.get(user_id, [])


# Also works to mix sync and async tools in the same toolkit
@ez_tool
def format_currency(amount: float) -> str:
    """Format a number as USD currency.

    Args:
        amount: The amount to format
    """
    return f"${amount:,.2f}"


toolkit = Toolkit([fetch_user, fetch_orders, format_currency])


def demo_basic_async():
    """Async tools work transparently — no special handling needed."""
    print("=" * 60)
    print("1. Basic Async Tool Call")
    print("=" * 60)

    result = toolkit.execute_sync("""
user = fetch_user(1)
print(f"User: {user['name']} ({user['role']})")
""")
    print(f"  Output: {result.output.strip()}")
    print(f"  Tool calls: {[tc['name'] for tc in result.tool_calls]}")
    print()


def demo_async_chaining():
    """Chain async tools together, mix with sync tools."""
    print("=" * 60)
    print("2. Async + Sync Tool Chaining")
    print("=" * 60)

    result = toolkit.execute_sync("""
user = fetch_user(2)
orders = fetch_orders(2)
total = sum(o["amount"] for o in orders)
formatted = format_currency(total)
print(f"{user['name']} has {len(orders)} orders totaling {formatted}")
""")
    print(f"  Output: {result.output.strip()}")
    print(f"  Tool calls: {[tc['name'] for tc in result.tool_calls]}")
    print()


def demo_parallel_async():
    """LLM code can use asyncio.gather for parallel async tool calls."""
    print("=" * 60)
    print("3. Parallel Async Execution (asyncio.gather)")
    print("=" * 60)

    # Inside the sandbox, tools are exposed as sync wrappers (the executor
    # handles async dispatch). Use asyncio.to_thread to run them in parallel.
    result = toolkit.execute_sync("""
import asyncio

async def main():
    # Fetch all users in parallel via asyncio.to_thread
    users = await asyncio.gather(
        asyncio.to_thread(fetch_user, 1),
        asyncio.to_thread(fetch_user, 2),
        asyncio.to_thread(fetch_user, 3),
    )
    for u in users:
        print(f"  {u['id']}: {u['name']} ({u['role']})")

asyncio.run(main())
""")
    print(f"  Output:\n{result.output}", end="")
    print(f"  Tool calls: {len(result.tool_calls)} parallel calls")
    print()


def demo_event_loop_fallback():
    """Executor detects running event loops and uses thread fallback."""
    print("=" * 60)
    print("4. Event Loop Fallback (simulates Pydantic AI / FastAPI)")
    print("=" * 60)

    from ez_ptc.executor import execute_code

    code = """
user = fetch_user(1)
print(f"Got user: {user['name']}")
"""
    tool_map = {t.name: t for t in toolkit.tools}

    # Simulate being called from within an async framework
    async def run_from_async_context():
        return execute_code(code, tool_map, timeout=10.0)

    result = asyncio.run(run_from_async_context())
    print(f"  Output: {result.output.strip()}")
    print(f"  Success: {result.success} (thread fallback worked)")
    print()


if __name__ == "__main__":
    demo_basic_async()
    demo_async_chaining()
    demo_parallel_async()
    demo_event_loop_fallback()
