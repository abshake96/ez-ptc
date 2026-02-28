# Tool Mode

Tool mode integrates ez-ptc with any LLM framework that supports native tool calling. You register a single **meta-tool** that accepts Python code, and the framework handles the agentic loop.

## When to use Tool Mode

- You're using a framework (OpenAI, Anthropic, LangChain, etc.)
- You want the framework to manage the agentic loop
- You need reliable tool invocation (not dependent on code block extraction)
- You're building production agents

## How it works

### 1. Get the meta-tool and schema

```python
from ez_ptc import Toolkit, ez_tool

@ez_tool
def get_weather(location: str) -> dict:
    """Get weather for a location."""
    return {"temp": 22, "condition": "sunny"}

toolkit = Toolkit([get_weather])

# A callable function: execute_tools(code: str) -> str
execute_fn = toolkit.as_tool()

# JSON schema for framework registration
schema = toolkit.tool_schema(format="openai")   # or "anthropic"
```

### 2. (Optional) Add a system prompt with `tool_prompt()`

The tool schema description and `as_tool()` docstring already include instructions telling the LLM to combine all operations into a single code block. For many models and frameworks, this is enough.

However, some models — especially those with native **parallel tool calling** (e.g., OpenAI models via the raw API) — may still split work into multiple separate `execute_tools` calls instead of writing one code block that does everything. If you observe this behavior, add `tool_prompt()` to your system prompt as reinforcement:

```python
system_message = f"You are a helpful assistant.\n\n{toolkit.tool_prompt()}"
```

`tool_prompt()` generates a system prompt block that:
- Lists all available functions and their signatures
- Explicitly instructs the LLM to combine ALL operations into a single call
- Documents the execution environment (pre-imported modules, restrictions)

**When do you need it?** Run your agent and check how many `execute_tools` calls the LLM makes. If it's making multiple calls for a task that should be one code block, add `tool_prompt()`. If it already consolidates correctly, you can skip it.

### 3. Register with your framework

The schema tells the framework about the meta-tool. The LLM sees a single tool called `execute_tools` that accepts a `code` parameter.

The tool's description includes all available sub-tools, so the LLM knows what functions it can call inside the code.

### 4. Handle tool calls

When the LLM calls the meta-tool, pass the code to `execute_fn`:

```python
result = execute_fn(code_from_llm)
# Returns: stdout on success, stderr/traceback on failure
```

## Framework integrations

### OpenAI

OpenAI models support parallel tool calling, so they may split work into multiple separate calls. Adding `tool_prompt()` to the system prompt helps consolidate them into a single code block.

```python
from openai import OpenAI

client = OpenAI()
tool_schema = toolkit.tool_schema(format="openai")
execute_fn = toolkit.as_tool()

messages = [
    # tool_prompt() reinforces single-call behavior for models with parallel tool calling
    {"role": "system", "content": f"You are a helpful assistant.\n\n{toolkit.tool_prompt()}"},
    {"role": "user", "content": "What's the weather in NYC?"},
]

for turn in range(10):
    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=messages,
        tools=[tool_schema],
    )
    choice = response.choices[0]

    if choice.message.tool_calls:
        messages.append(choice.message)
        for tool_call in choice.message.tool_calls:
            import json
            args = json.loads(tool_call.function.arguments)
            result = execute_fn(**args)
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": result,
            })
    else:
        print(choice.message.content)
        break
```

### Anthropic

```python
import anthropic

client = anthropic.Anthropic()
tool_schema = toolkit.tool_schema(format="anthropic")
execute_fn = toolkit.as_tool()

messages = [{"role": "user", "content": "What's the weather in NYC?"}]

for turn in range(10):
    response = client.messages.create(
        model="claude-sonnet-4-5-20250514",
        max_tokens=4096,
        # tool_prompt() is optional here — add it if the model isn't consolidating calls
        system=f"You are a helpful assistant.\n\n{toolkit.tool_prompt()}",
        tools=[tool_schema],
        messages=messages,
    )

    if response.stop_reason == "tool_use":
        messages.append({"role": "assistant", "content": response.content})
        tool_results = []
        for block in response.content:
            if block.type == "tool_use":
                result = execute_fn(block.input.get("code", ""))
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result,
                })
        messages.append({"role": "user", "content": tool_results})
    else:
        for block in response.content:
            if hasattr(block, "text"):
                print(block.text)
        break
```

### LangChain

```python
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool as langchain_tool
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage

execute_fn = toolkit.as_tool()

@langchain_tool
def execute_tools(code: str) -> str:
    """Execute Python code with access to tools."""
    return execute_fn(code)

llm = ChatOpenAI(model="gpt-4.1-mini").bind_tools([execute_tools])
messages = [
    # tool_prompt() is optional — add it if the model isn't consolidating calls
    SystemMessage(content=f"You are a helpful assistant.\n\n{toolkit.tool_prompt()}"),
    HumanMessage(content="What's the weather?"),
]

for turn in range(10):
    response = llm.invoke(messages)
    messages.append(response)
    if response.tool_calls:
        for tc in response.tool_calls:
            result = execute_tools.invoke(tc["args"])
            messages.append(ToolMessage(content=result, tool_call_id=tc["id"]))
    else:
        print(response.content)
        break
```

### Pydantic AI

Pydantic AI manages tool calls sequentially, so models typically consolidate well without `tool_prompt()`. Add it if needed.

```python
from pydantic_ai import Agent, Tool as PydanticTool

execute_fn = toolkit.as_tool()

agent = Agent(
    "openai:gpt-4.1-mini",
    # system_prompt with tool_prompt() is optional for Pydantic AI — the as_tool()
    # docstring usually provides enough guidance on its own
    system_prompt=f"You are a helpful assistant.\n\n{toolkit.tool_prompt()}",
    tools=[PydanticTool(execute_fn, takes_ctx=False)],
)

result = agent.run_sync("What's the weather in NYC?")
print(result.output)
```

See [Framework Examples](examples.md) for complete, runnable examples for all supported frameworks.

## Schema formats

`toolkit.tool_schema()` supports two formats:

### OpenAI format (default)

```python
schema = toolkit.tool_schema(format="openai")
# {
#     "type": "function",
#     "function": {
#         "name": "execute_tools",
#         "description": "Execute Python code with access to these tools: ...",
#         "parameters": {
#             "type": "object",
#             "properties": {"code": {"type": "string", ...}},
#             "required": ["code"]
#         }
#     }
# }
```

Works with: OpenAI, LiteLLM, Google Gemini (with minor conversion), most OpenAI-compatible APIs.

### Anthropic format

```python
schema = toolkit.tool_schema(format="anthropic")
# {
#     "name": "execute_tools",
#     "description": "Execute Python code with access to these tools: ...",
#     "input_schema": {
#         "type": "object",
#         "properties": {"code": {"type": "string", ...}},
#         "required": ["code"]
#     }
# }
```

## The `as_tool()` callable

`toolkit.as_tool()` returns a function with proper metadata for framework introspection:

```python
fn = toolkit.as_tool()

fn.__name__        # "execute_tools"
fn.__doc__         # Docstring listing all sub-tools
fn.__annotations__ # {"code": str, "return": str}
fn("print('hi')")  # "hi\n"
```

The function accepts a `code` string, executes it with all toolkit tools available, and returns:
- **On success:** captured stdout, or repr of last expression if no output
- **On failure:** stderr/traceback for LLM self-correction
