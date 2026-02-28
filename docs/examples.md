# Framework Examples

All examples live in the [`examples/`](../examples/) directory and use the same shared tools defined in [`shared_tools.py`](../examples/shared_tools.py).

## Shared tools

Every example uses these two tools:

```python
from typing import TypedDict
from ez_ptc import Toolkit, ez_tool

class WeatherResult(TypedDict):
    location: str
    temp: int
    unit: str
    condition: str

class ProductResult(TypedDict):
    id: int
    name: str
    price: float
    tags: list[str]

@ez_tool
def get_weather(location: str, unit: str = "celsius") -> WeatherResult:
    """Get current weather for a location."""
    ...

@ez_tool
def search_products(query: str, limit: int = 5) -> list[ProductResult]:
    """Search the product catalog."""
    ...

toolkit = Toolkit([get_weather, search_products], assist_tool_chaining=True)
```

And the same user prompt:

> "Check the weather in San Francisco, CA and New York, NY. Then search for products appropriate for each city's weather. Print a summary of your findings."

## Running examples

```bash
# Set your API key(s) in .env or environment
export OPENAI_API_KEY=sk-...
export ANTHROPIC_API_KEY=sk-ant-...

# Run any example
uv run python examples/example_openai.py
uv run python examples/example_anthropic.py
uv run python examples/example_prompt_mode.py
uv run python examples/example_litellm.py
uv run python examples/example_langchain.py
uv run python examples/example_pydantic_ai.py
uv run python examples/example_google_genai.py
```

## A note on `tool_prompt()`

All tool-mode examples include `toolkit.tool_prompt()` in the system prompt. This is **optional** — the tool schema and `as_tool()` docstring already instruct the LLM to consolidate operations into a single code block.

`tool_prompt()` adds reinforcement for models that support parallel tool calling (e.g., OpenAI models via the raw API), which may otherwise split work into multiple separate `execute_tools` calls. If your model already consolidates correctly, you can omit it.

## Example overview

| Example | Mode | Framework | Provider |
|---------|------|-----------|----------|
| [`example_prompt_mode.py`](../examples/example_prompt_mode.py) | Prompt | None (raw API) | OpenAI |
| [`example_openai.py`](../examples/example_openai.py) | Tool | OpenAI SDK | OpenAI |
| [`example_anthropic.py`](../examples/example_anthropic.py) | Tool | Anthropic SDK | Anthropic |
| [`example_litellm.py`](../examples/example_litellm.py) | Tool | LiteLLM | Any |
| [`example_langchain.py`](../examples/example_langchain.py) | Tool | LangChain | OpenAI |
| [`example_pydantic_ai.py`](../examples/example_pydantic_ai.py) | Tool | Pydantic AI | OpenAI |
| [`example_google_genai.py`](../examples/example_google_genai.py) | Tool | Google GenAI | Gemini |

## Prompt Mode (framework-free)

**File:** [`example_prompt_mode.py`](../examples/example_prompt_mode.py)

The simplest integration. No tool calling protocol — the LLM writes code in a markdown block.

```python
# Generate system prompt with tool descriptions
tool_instructions = toolkit.prompt()

# Call LLM (no tools parameter)
response = client.chat.completions.create(
    model="gpt-4.1-mini",
    messages=[
        {"role": "system", "content": tool_instructions},
        {"role": "user", "content": USER_PROMPT},
    ],
)

# Extract code from markdown and execute
code = toolkit.extract_code(response.choices[0].message.content)
result = toolkit.execute(code)
```

## OpenAI (tool mode)

**File:** [`example_openai.py`](../examples/example_openai.py)

Native tool calling with OpenAI's chat completions API.

```python
tool_schema = toolkit.tool_schema(format="openai")
execute_fn = toolkit.as_tool()

# Register tool and run agentic loop
response = client.chat.completions.create(
    model="gpt-4.1-mini",
    messages=messages,
    tools=[tool_schema],
)

# Handle tool calls
for tool_call in choice.message.tool_calls:
    args = json.loads(tool_call.function.arguments)
    result = execute_fn(**args)
    messages.append({"role": "tool", "tool_call_id": tool_call.id, "content": result})
```

## Anthropic (tool mode)

**File:** [`example_anthropic.py`](../examples/example_anthropic.py)

Uses Anthropic's native `tool_use` format.

```python
tool_schema = toolkit.tool_schema(format="anthropic")
execute_fn = toolkit.as_tool()

response = client.messages.create(
    model="claude-sonnet-4-5-20250514",
    tools=[tool_schema],
    messages=messages,
)

# Handle tool_use blocks
for block in response.content:
    if block.type == "tool_use":
        result = execute_fn(block.input.get("code", ""))
        tool_results.append({"type": "tool_result", "tool_use_id": block.id, "content": result})
```

## LiteLLM (any provider)

**File:** [`example_litellm.py`](../examples/example_litellm.py)

Same as OpenAI but uses LiteLLM for provider-agnostic calls. Swap the model string to use any provider:

```python
import litellm

# Works with any LiteLLM-supported model
response = litellm.completion(
    model="openai/gpt-4.1-mini",          # or
    # model="anthropic/claude-sonnet-4-5-20250514",  # or
    # model="gemini/gemini-2.0-flash",
    messages=messages,
    tools=[tool_schema],
)
```

## LangChain

**File:** [`example_langchain.py`](../examples/example_langchain.py)

Wraps the ez-ptc meta-tool as a LangChain tool.

```python
from langchain_core.tools import tool as langchain_tool

execute_fn = toolkit.as_tool()

@langchain_tool
def execute_tools(code: str) -> str:
    """Execute Python code with access to tools."""
    return execute_fn(code)

llm = ChatOpenAI(model="gpt-4.1-mini").bind_tools([execute_tools])
```

## Pydantic AI

**File:** [`example_pydantic_ai.py`](../examples/example_pydantic_ai.py)

The most concise integration — Pydantic AI handles the agentic loop automatically.

```python
from pydantic_ai import Agent, Tool as PydanticTool

execute_fn = toolkit.as_tool()

agent = Agent(
    "openai:gpt-4.1-mini",
    tools=[PydanticTool(execute_fn, takes_ctx=False)],
)
result = agent.run_sync(USER_PROMPT)
```

## Google Gemini

**File:** [`example_google_genai.py`](../examples/example_google_genai.py)

Uses the Google GenAI SDK. Requires converting the OpenAI schema format to Google's function declaration format.

```python
from google import genai
from google.genai.types import FunctionDeclaration, Tool as GenaiTool

schema = toolkit.tool_schema(format="openai")
func_decl = FunctionDeclaration(
    name=schema["function"]["name"],
    description=schema["function"]["description"],
    parameters=schema["function"]["parameters"],
)
tools = [GenaiTool(function_declarations=[func_decl])]
```
