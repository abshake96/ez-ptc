"""
Benchmark: Traditional vs ez-ptc (basic) vs ez-ptc (chaining)

Compares three tool-calling methodologies using the raw OpenAI API:
1. Traditional — each tool registered individually; LLM calls tools one-at-a-time
2. ez-ptc (basic) — single execute_tools meta-tool; assist_tool_chaining=False
3. ez-ptc (chaining) — single execute_tools meta-tool; assist_tool_chaining=True

Usage:
    uv run python benchmark.py
    uv run python benchmark.py --model gpt-4.1-mini --runs 3 --save
"""

import argparse
import json
import statistics
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TypedDict

from dotenv import load_dotenv
from openai import OpenAI

from ez_ptc import Toolkit, ez_tool

load_dotenv()


# ── Type definitions & mock data ─────────────────────────────────────────


class CarSearchResult(TypedDict):
    car_id: str
    name: str
    price: int
    body_type: str


class CarSpecs(TypedDict):
    car_id: str
    kmpl: float
    fuel_type: str
    engine_cc: int
    transmission: str


class AvailabilityResult(TypedDict):
    car_id: str
    available: bool
    dealer_count: int


MOCK_CARS = [
    {"car_id": "suv_001", "name": "Hyundai Creta", "price": 1100000, "body_type": "SUV"},
    {"car_id": "suv_002", "name": "Kia Seltos", "price": 1200000, "body_type": "SUV"},
    {"car_id": "suv_003", "name": "MG Hector", "price": 1450000, "body_type": "SUV"},
    {"car_id": "suv_004", "name": "Tata Nexon", "price": 900000, "body_type": "SUV"},
    {"car_id": "suv_005", "name": "Maruti Brezza", "price": 850000, "body_type": "SUV"},
    {"car_id": "suv_006", "name": "Mahindra XUV300", "price": 950000, "body_type": "SUV"},
    {"car_id": "suv_007", "name": "Toyota Urban Cruiser", "price": 1000000, "body_type": "SUV"},
    {"car_id": "suv_008", "name": "Volkswagen Taigun", "price": 1150000, "body_type": "SUV"},
    {"car_id": "suv_009", "name": "Skoda Kushaq", "price": 1180000, "body_type": "SUV"},
    {"car_id": "suv_010", "name": "Honda WR-V", "price": 980000, "body_type": "SUV"},
    {"car_id": "suv_011", "name": "Renault Kiger", "price": 650000, "body_type": "SUV"},
    {"car_id": "suv_012", "name": "Nissan Magnite", "price": 620000, "body_type": "SUV"},
    {"car_id": "suv_013", "name": "Mahindra XUV700", "price": 1400000, "body_type": "SUV"},
    {"car_id": "suv_014", "name": "Tata Harrier", "price": 1500000, "body_type": "SUV"},
    {"car_id": "suv_015", "name": "Hyundai Venue", "price": 780000, "body_type": "SUV"},
]

MOCK_SPECS = {
    "suv_001": {"car_id": "suv_001", "kmpl": 16.8, "fuel_type": "Petrol", "engine_cc": 1497, "transmission": "Manual"},
    "suv_002": {"car_id": "suv_002", "kmpl": 16.5, "fuel_type": "Petrol", "engine_cc": 1497, "transmission": "Automatic"},
    "suv_003": {"car_id": "suv_003", "kmpl": 13.5, "fuel_type": "Petrol", "engine_cc": 1956, "transmission": "Automatic"},
    "suv_004": {"car_id": "suv_004", "kmpl": 17.4, "fuel_type": "Diesel", "engine_cc": 1497, "transmission": "Manual"},
    "suv_005": {"car_id": "suv_005", "kmpl": 17.0, "fuel_type": "Petrol", "engine_cc": 1462, "transmission": "Manual"},
    "suv_006": {"car_id": "suv_006", "kmpl": 17.0, "fuel_type": "Petrol", "engine_cc": 1197, "transmission": "Manual"},
    "suv_007": {"car_id": "suv_007", "kmpl": 17.0, "fuel_type": "Petrol", "engine_cc": 1462, "transmission": "Automatic"},
    "suv_008": {"car_id": "suv_008", "kmpl": 14.1, "fuel_type": "Petrol", "engine_cc": 999, "transmission": "Automatic"},
    "suv_009": {"car_id": "suv_009", "kmpl": 14.5, "fuel_type": "Petrol", "engine_cc": 999, "transmission": "Manual"},
    "suv_010": {"car_id": "suv_010", "kmpl": 16.5, "fuel_type": "Petrol", "engine_cc": 1199, "transmission": "Manual"},
    "suv_011": {"car_id": "suv_011", "kmpl": 20.5, "fuel_type": "Petrol", "engine_cc": 999, "transmission": "Manual"},
    "suv_012": {"car_id": "suv_012", "kmpl": 20.0, "fuel_type": "Petrol", "engine_cc": 999, "transmission": "Manual"},
    "suv_013": {"car_id": "suv_013", "kmpl": 13.0, "fuel_type": "Petrol", "engine_cc": 1997, "transmission": "Automatic"},
    "suv_014": {"car_id": "suv_014", "kmpl": 14.6, "fuel_type": "Diesel", "engine_cc": 1956, "transmission": "Automatic"},
    "suv_015": {"car_id": "suv_015", "kmpl": 17.5, "fuel_type": "Petrol", "engine_cc": 1197, "transmission": "Manual"},
}

MOCK_AVAILABILITY = {
    "suv_001": {"available": True, "dealer_count": 5},
    "suv_002": {"available": True, "dealer_count": 4},
    "suv_003": {"available": False, "dealer_count": 0},
    "suv_004": {"available": True, "dealer_count": 8},
    "suv_005": {"available": True, "dealer_count": 6},
    "suv_006": {"available": True, "dealer_count": 3},
    "suv_007": {"available": False, "dealer_count": 0},
    "suv_008": {"available": True, "dealer_count": 2},
    "suv_009": {"available": True, "dealer_count": 3},
    "suv_010": {"available": False, "dealer_count": 0},
    "suv_011": {"available": True, "dealer_count": 7},
    "suv_012": {"available": True, "dealer_count": 5},
    "suv_013": {"available": True, "dealer_count": 4},
    "suv_014": {"available": False, "dealer_count": 0},
    "suv_015": {"available": True, "dealer_count": 6},
}


# ── Tools ────────────────────────────────────────────────────────────────


@ez_tool
def search_cars(body_type: str) -> list[CarSearchResult]:
    """Search cars by body type."""
    return [car for car in MOCK_CARS if car["body_type"].lower() == body_type.lower()]


@ez_tool
def get_specs(car_id: str) -> CarSpecs:
    """Get detailed specifications for a specific car."""
    if car_id not in MOCK_SPECS:
        raise ValueError(f"Car ID {car_id} not found")
    return MOCK_SPECS[car_id]


@ez_tool
def check_availability(car_id: str, city: str) -> AvailabilityResult:
    """Check dealer availability for a car in a specific city."""
    if car_id not in MOCK_AVAILABILITY:
        return {"car_id": car_id, "available": False, "dealer_count": 0}
    result = MOCK_AVAILABILITY[car_id]
    return {"car_id": car_id, **result}


TOOLS = [search_cars, get_specs, check_availability]

QUERY = "SUVs with mileage >15 kmpl, available in Delhi with specs and dealer availability."


# ── Metrics ──────────────────────────────────────────────────────────────


@dataclass
class ScenarioMetrics:
    name: str
    llm_turns: int = 0
    tool_calls: int = 0
    api_time: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    final_answer: str = ""
    code_blocks: list[str] = field(default_factory=list)


# ── Helpers ──────────────────────────────────────────────────────────────


def tool_to_openai_schema(tool):
    """Convert an ez-ptc Tool to an OpenAI function tool schema."""
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.parameters,
        },
    }


def timed_completion(client, **kwargs):
    """Call client.chat.completions.create and return (response, elapsed_seconds)."""
    start = time.perf_counter()
    response = client.chat.completions.create(**kwargs)
    elapsed = time.perf_counter() - start
    return response, elapsed


def accumulate_usage(metrics, usage):
    """Add token counts from a response.usage object."""
    if usage:
        metrics.prompt_tokens += usage.prompt_tokens or 0
        metrics.completion_tokens += usage.completion_tokens or 0


# ── Scenario runners ─────────────────────────────────────────────────────


def run_traditional(client, model, max_turns, temperature):
    """Scenario 1: Traditional tool calling — each tool registered individually."""
    metrics = ScenarioMetrics(name="Traditional")

    openai_tools = [tool_to_openai_schema(t) for t in TOOLS]
    dispatch = {t.name: t for t in TOOLS}

    messages = [
        {"role": "system", "content": "You are a helpful car search assistant. Use the available tools to answer the user's query."},
        {"role": "user", "content": QUERY},
    ]

    for _ in range(max_turns):
        response, elapsed = timed_completion(
            client,
            model=model,
            messages=messages,
            tools=openai_tools,
            parallel_tool_calls=True,
            temperature=temperature,
        )
        metrics.api_time += elapsed
        metrics.llm_turns += 1
        accumulate_usage(metrics, response.usage)

        choice = response.choices[0]
        message = choice.message

        # Collect code blocks for display
        if message.tool_calls:
            lines = []
            for tc in message.tool_calls:
                args = json.loads(tc.function.arguments)
                params = ", ".join(f"{k}={json.dumps(v)}" for k, v in args.items())
                lines.append(f"{tc.function.name}({params})")
            metrics.code_blocks.append("\n".join(lines))

        if choice.finish_reason == "stop":
            metrics.final_answer = message.content or ""
            break

        if not message.tool_calls:
            metrics.final_answer = message.content or ""
            break

        # Append assistant message with tool calls
        messages.append(message.model_dump())

        # Dispatch each tool call
        for tc in message.tool_calls:
            fn = dispatch[tc.function.name]
            args = json.loads(tc.function.arguments)
            result = fn(**args)
            metrics.tool_calls += 1
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": json.dumps(result),
            })

    return metrics


def run_ezptc(client, model, max_turns, temperature, chaining, verbose=False):
    """Scenario 2/3: ez-ptc meta-tool approach."""
    label = "ez-ptc (chaining)" if chaining else "ez-ptc (basic)"
    metrics = ScenarioMetrics(name=label)

    toolkit = Toolkit(TOOLS, assist_tool_chaining=chaining)
    openai_tool_schema = toolkit.tool_schema(format="openai")
    system_prompt = (
        "You are a helpful car search assistant.\n\n"
        + toolkit.tool_prompt()
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": QUERY},
    ]

    for turn_idx in range(max_turns):
        response, elapsed = timed_completion(
            client,
            model=model,
            messages=messages,
            tools=[openai_tool_schema],
            temperature=temperature,
        )
        metrics.api_time += elapsed
        metrics.llm_turns += 1
        accumulate_usage(metrics, response.usage)

        choice = response.choices[0]
        message = choice.message

        if verbose:
            print(f"\n  [Turn {turn_idx + 1}] finish_reason={choice.finish_reason}")
            if message.content:
                print(f"  [Assistant text] {message.content[:200]}{'...' if len(message.content or '') > 200 else ''}")
            if message.tool_calls:
                print(f"  [Tool calls] {len(message.tool_calls)} call(s)")

        if choice.finish_reason == "stop":
            metrics.final_answer = message.content or ""
            break

        if not message.tool_calls:
            metrics.final_answer = message.content or ""
            break

        # Append assistant message
        messages.append(message.model_dump())

        # Process each tool call (should be a single execute_tools call)
        for tc in message.tool_calls:
            args = json.loads(tc.function.arguments)
            code = args.get("code", "")
            metrics.code_blocks.append(code)

            result = toolkit.execute_sync(code)
            metrics.tool_calls += len(result.tool_calls)

            # Apply same logic as as_tool_sync: error hint prefix + empty-output safety net
            if not result.success and toolkit._error_hint:
                tool_output = f"ERROR: {toolkit._error_hint}\n\n{result.to_string()}"
            elif (
                not result.output
                and result.tool_calls
                and not chaining
                and "print(" not in code
            ):
                tool_output = (
                    "[No output captured. You called tool(s) but did not print() the results. "
                    "Rewrite the code to print() each result immediately: print(tool_name(...))]"
                )
            else:
                tool_output = result.to_string()

            if verbose:
                print(f"  [Code]\n    {code.replace(chr(10), chr(10) + '    ')}")
                print(f"  [Tool return] success={result.success}, tool_calls={len(result.tool_calls)}")
                preview = tool_output[:300]
                print(f"  [Output] {preview}{'...' if len(tool_output) > 300 else ''}")

            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": tool_output,
            })

    return metrics


# ── Output formatting ────────────────────────────────────────────────────


def print_scenario_result(metrics):
    """Print live output for a single scenario run."""
    print(f"\n{'=' * 80}")
    print(f"SCENARIO: {metrics.name}")
    print(f"{'=' * 80}")

    print("\n--- LLM-Generated Code (per turn) ---")
    if metrics.code_blocks:
        for i, block in enumerate(metrics.code_blocks, 1):
            print(f"  Turn {i}:")
            for line in block.split("\n"):
                print(f"    {line}")
    else:
        print("  (no code blocks)")

    total_tokens = metrics.prompt_tokens + metrics.completion_tokens
    print("\n--- Metrics ---")
    print(f"  LLM Turns:          {metrics.llm_turns}")
    print(f"  Tool Calls:         {metrics.tool_calls}")
    print(f"  API Time:           {metrics.api_time:.2f}s")
    print(f"  Prompt Tokens:      {metrics.prompt_tokens:,}")
    print(f"  Completion Tokens:  {metrics.completion_tokens:,}")
    print(f"  Total Tokens:       {total_tokens:,}")

    print("\n--- Final Answer ---")
    answer = metrics.final_answer.strip()
    if answer:
        for line in answer.split("\n"):
            print(f"  {line}")
    else:
        print("  (no final answer)")


def _fmt_val(values, fmt=",d"):
    """Format a single value or mean +/- stddev for multiple runs."""
    if len(values) == 1:
        return f"{values[0]:{fmt}}"
    mean = statistics.mean(values)
    if fmt == ".2f":
        return f"{mean:.2f} +/- {statistics.stdev(values):.2f}"
    return f"{mean:,.0f} +/- {statistics.stdev(values):,.0f}"


def print_comparison(all_results):
    """Print comparison table for all scenarios across all runs."""
    # all_results: dict[scenario_name -> list[ScenarioMetrics]]
    names = list(all_results.keys())
    header = ["Metric"] + names
    col_widths = [max(20, len(h) + 2) for h in header]

    def row(label, extractor, fmt=",d"):
        values_per_scenario = {name: [extractor(m) for m in runs] for name, runs in all_results.items()}
        cells = [label]
        for name in names:
            cells.append(_fmt_val(values_per_scenario[name], fmt))
        return cells

    rows = [
        row("LLM Turns", lambda m: m.llm_turns),
        row("Tool Calls", lambda m: m.tool_calls),
        row("Prompt Tokens", lambda m: m.prompt_tokens),
        row("Completion Tokens", lambda m: m.completion_tokens),
        row("Total Tokens", lambda m: m.prompt_tokens + m.completion_tokens),
        row("API Time (s)", lambda m: m.api_time, fmt=".2f"),
    ]

    # Recalculate widths based on actual content
    all_rows = [header] + rows
    for r in all_rows:
        for i, cell in enumerate(r):
            col_widths[i] = max(col_widths[i], len(str(cell)) + 2)

    def fmt_row(cells):
        parts = []
        for i, cell in enumerate(cells):
            if i == 0:
                parts.append(f" {cell:<{col_widths[i] - 1}}")
            else:
                parts.append(f" {cell:>{col_widths[i] - 1}}")
        return "|" + "|".join(parts) + "|"

    sep = "|" + "|".join("-" * w for w in col_widths) + "|"

    print(f"\n{'=' * 40} RESULTS {'=' * 40}")
    print(fmt_row(header))
    print(sep)
    for r in rows:
        print(fmt_row(r))
    print("=" * (sum(col_widths) + len(col_widths) + 1))

    # Savings: ez-ptc (chaining) vs Traditional
    if len(names) >= 3:
        trad = all_results[names[0]]
        chain = all_results[names[2]]
        trad_tokens = statistics.mean([m.prompt_tokens + m.completion_tokens for m in trad])
        chain_tokens = statistics.mean([m.prompt_tokens + m.completion_tokens for m in chain])
        trad_time = statistics.mean([m.api_time for m in trad])
        chain_time = statistics.mean([m.api_time for m in chain])
        trad_turns = statistics.mean([m.llm_turns for m in trad])
        chain_turns = statistics.mean([m.llm_turns for m in chain])

        token_pct = ((trad_tokens - chain_tokens) / trad_tokens * 100) if trad_tokens else 0
        time_pct = ((trad_time - chain_time) / trad_time * 100) if trad_time else 0
        turn_pct = ((trad_turns - chain_turns) / trad_turns * 100) if trad_turns else 0

        print(f"\n--- Savings: {names[2]} vs {names[0]} ---")
        print(f"  Tokens:    {token_pct:+.1f}%  ({trad_tokens:,.0f} -> {chain_tokens:,.0f})")
        print(f"  API Time:  {time_pct:+.1f}%  ({trad_time:.2f}s -> {chain_time:.2f}s)")
        print(f"  LLM Turns: {turn_pct:+.1f}%  ({trad_turns:.0f} -> {chain_turns:.0f})")


# ── Markdown report ──────────────────────────────────────────────────────


def _format_code_for_report(code_blocks):
    """Format code blocks for the markdown report."""
    if not code_blocks:
        return "_No code generated._"
    parts = []
    for i, block in enumerate(code_blocks, 1):
        if len(code_blocks) > 1:
            parts.append(f"**Turn {i}:**")
        parts.append(f"```python\n{block}\n```")
    return "\n\n".join(parts)


def _mean(metrics_list, extractor):
    return statistics.mean([extractor(m) for m in metrics_list])


def _pct_change(old, new):
    if old == 0:
        return 0.0
    return (old - new) / old * 100


def generate_report(all_results, model, runs):
    """Generate a markdown benchmark report."""
    names = list(all_results.keys())
    s1, s2, s3 = [all_results[n] for n in names]

    def avg(metrics_list, ext):
        return _mean(metrics_list, ext)

    def fmt(val, fmt_str=","):
        if fmt_str == ",":
            return f"{val:,.0f}"
        return f"{val:{fmt_str}}"

    s1_turns = avg(s1, lambda m: m.llm_turns)
    s2_turns = avg(s2, lambda m: m.llm_turns)
    s3_turns = avg(s3, lambda m: m.llm_turns)
    s1_tools = avg(s1, lambda m: m.tool_calls)
    s2_tools = avg(s2, lambda m: m.tool_calls)
    s3_tools = avg(s3, lambda m: m.tool_calls)
    s1_tokens = avg(s1, lambda m: m.prompt_tokens + m.completion_tokens)
    s2_tokens = avg(s2, lambda m: m.prompt_tokens + m.completion_tokens)
    s3_tokens = avg(s3, lambda m: m.prompt_tokens + m.completion_tokens)
    s1_input = avg(s1, lambda m: m.prompt_tokens)
    s2_input = avg(s2, lambda m: m.prompt_tokens)
    s3_input = avg(s3, lambda m: m.prompt_tokens)
    s1_output = avg(s1, lambda m: m.completion_tokens)
    s2_output = avg(s2, lambda m: m.completion_tokens)
    s3_output = avg(s3, lambda m: m.completion_tokens)
    s1_time = avg(s1, lambda m: m.api_time)
    s2_time = avg(s2, lambda m: m.api_time)
    s3_time = avg(s3, lambda m: m.api_time)

    # Use code blocks from the last run of each scenario
    s1_code = _format_code_for_report(s1[-1].code_blocks)
    s2_code = _format_code_for_report(s2[-1].code_blocks)
    s3_code = _format_code_for_report(s3[-1].code_blocks)

    def best_label(v1, v2, v3):
        vals = [(v1, names[0]), (v2, names[1]), (v3, names[2])]
        return min(vals, key=lambda x: x[0])[1]

    turns_imp = _pct_change(s1_turns, s3_turns)
    tokens_imp = _pct_change(s1_tokens, s3_tokens)
    time_imp = _pct_change(s1_time, s3_time)

    chain_turn_diff = abs(_pct_change(s2_turns, s3_turns))
    chain_turn_dir = "fewer" if s3_turns < s2_turns else "more" if s3_turns > s2_turns else "same"
    chain_token_diff = abs(_pct_change(s2_tokens, s3_tokens))
    chain_token_dir = "fewer" if s3_tokens < s2_tokens else "more" if s3_tokens > s2_tokens else "same"
    chain_time_diff = abs(_pct_change(s2_time, s3_time))
    chain_time_dir = "faster" if s3_time < s2_time else "slower" if s3_time > s2_time else "same"

    if s3_tokens < min(s1_tokens, s2_tokens):
        winner = f"{names[2]}"
    elif s2_tokens < s1_tokens:
        winner = f"{names[1]}"
    else:
        winner = f"{names[0]}"

    stat_note = ""
    if runs > 1:
        stat_note = f"\n*Values are means across {runs} runs.*\n"

    report = f"""# Benchmark: Tool Calling Approaches

**Model:** {model}
**Query:** "{QUERY}"
**Date:** {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}
**Temperature:** 0.0
**Runs:** {runs}
{stat_note}
## Summary Table

| Metric | {names[0]} | {names[1]} | {names[2]} | Best |
|--------|----------:|----------:|----------:|------|
| **LLM Turns** | {s1_turns:.0f} | {s2_turns:.0f} | {s3_turns:.0f} | {best_label(s1_turns, s2_turns, s3_turns)} |
| **Tool Calls** | {s1_tools:.0f} | {s2_tools:.0f} | {s3_tools:.0f} | {best_label(s1_tools, s2_tools, s3_tools)} |
| **Total Tokens** | {s1_tokens:,.0f} | {s2_tokens:,.0f} | {s3_tokens:,.0f} | {best_label(s1_tokens, s2_tokens, s3_tokens)} |
| **Input Tokens** | {s1_input:,.0f} | {s2_input:,.0f} | {s3_input:,.0f} | - |
| **Output Tokens** | {s1_output:,.0f} | {s2_output:,.0f} | {s3_output:,.0f} | - |
| **API Time** | {s1_time:.2f}s | {s2_time:.2f}s | {s3_time:.2f}s | {best_label(s1_time, s2_time, s3_time)} |

## Scenario 1: {names[0]}

**Approach:** Each tool registered individually with OpenAI; LLM calls tools one-at-a-time (`parallel_tool_calls=True`).

**Results:** {s1_turns:.0f} turns, {s1_tools:.0f} tool calls, {s1_tokens:,.0f} tokens, {s1_time:.2f}s API time

**LLM-Generated Code:**

{s1_code}

## Scenario 2: {names[1]}

**Approach:** Single `execute_tools` meta-tool; LLM writes Python code (`assist_tool_chaining=False`).

**Results:** {s2_turns:.0f} turns, {s2_tools:.0f} tool calls, {s2_tokens:,.0f} tokens, {s2_time:.2f}s API time

**LLM-Generated Code:**

{s2_code}

## Scenario 3: {names[2]}

**Approach:** Single `execute_tools` meta-tool; LLM gets `# Returns: {{...}}` hints (`assist_tool_chaining=True`).

**Results:** {s3_turns:.0f} turns, {s3_tools:.0f} tool calls, {s3_tokens:,.0f} tokens, {s3_time:.2f}s API time

**LLM-Generated Code:**

{s3_code}

## Key Improvements

### {names[2]} vs {names[0]}:
- **{turns_imp:.1f}%** fewer LLM turns
- **{tokens_imp:.1f}%** fewer tokens
- **{time_imp:.1f}%** faster API time

### {names[2]} vs {names[1]}:
- **{chain_turn_diff:.1f}%** {chain_turn_dir} LLM turns
- **{chain_token_diff:.1f}%** {chain_token_dir} tokens
- **{chain_time_diff:.1f}%** {chain_time_dir} API time

## Conclusion

**Winner:** {winner}

The key advantage of ez-ptc with tool chaining is that it:
1. Reduces LLM round-trips significantly
2. Enables programmatic filtering between tool calls
3. Returns only relevant data (selective output)
4. Saves tokens and reduces latency

Tool chaining documentation helps the LLM understand exact return types, enabling better code generation and data manipulation.
"""
    return report


# ── Main ─────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="Benchmark: Traditional vs ez-ptc tool calling"
    )
    parser.add_argument("--model", default="gpt-4.1-mini", help="OpenAI model name (default: gpt-4.1-mini)")
    parser.add_argument("--runs", type=int, default=1, help="Number of runs per scenario (default: 1)")
    parser.add_argument("--save", action="store_true", help="Save markdown report to BENCHMARK_REPORT.md")
    parser.add_argument("--temperature", type=float, default=0.0, help="LLM temperature (default: 0.0)")
    parser.add_argument("--max-turns", type=int, default=15, help="Max agentic loop iterations (default: 15)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Print intermediate turns and tool returns for debugging")
    args = parser.parse_args()

    client = OpenAI()

    print(f"\nBenchmark: Traditional vs ez-ptc Tool Calling")
    print(f"Model: {args.model}  |  Runs: {args.runs}  |  Temperature: {args.temperature}")
    print(f"{'=' * 80}")

    scenario_names = ["Traditional", "ez-ptc (basic)", "ez-ptc (chaining)"]
    all_results = {name: [] for name in scenario_names}

    for run_idx in range(args.runs):
        if args.runs > 1:
            print(f"\n{'#' * 80}")
            print(f"# RUN {run_idx + 1} / {args.runs}")
            print(f"{'#' * 80}")

        # Scenario 1: Traditional
        m1 = run_traditional(client, args.model, args.max_turns, args.temperature)
        print_scenario_result(m1)
        all_results["Traditional"].append(m1)

        # Scenario 2: ez-ptc (basic)
        m2 = run_ezptc(client, args.model, args.max_turns, args.temperature, chaining=False, verbose=args.verbose)
        print_scenario_result(m2)
        all_results["ez-ptc (basic)"].append(m2)

        # Scenario 3: ez-ptc (chaining)
        m3 = run_ezptc(client, args.model, args.max_turns, args.temperature, chaining=True, verbose=args.verbose)
        print_scenario_result(m3)
        all_results["ez-ptc (chaining)"].append(m3)

    print_comparison(all_results)

    if args.save:
        report = generate_report(all_results, args.model, args.runs)
        with open("BENCHMARK_REPORT.md", "w") as f:
            f.write(report)
        print(f"\nReport saved to BENCHMARK_REPORT.md")


if __name__ == "__main__":
    main()
