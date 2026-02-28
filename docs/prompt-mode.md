# Prompt Mode

Prompt mode is the framework-free way to use ez-ptc. You inject tool descriptions into the system prompt, the LLM writes Python code in a markdown block, and you extract and execute it.

## When to use Prompt Mode

- You're making raw API calls (no framework)
- You want full control over the LLM interaction
- You're prototyping or experimenting
- Your LLM doesn't support native tool calling

## How it works

### 1. Generate the system prompt

```python
from ez_ptc import Toolkit, ez_tool

@ez_tool
def get_weather(location: str, unit: str = "celsius") -> dict:
    """Get current weather for a location.

    Args:
        location: City and state, e.g. "San Francisco, CA"
        unit: Temperature unit - "celsius" or "fahrenheit"
    """
    return {"location": location, "temp": 22, "unit": unit, "condition": "sunny"}

toolkit = Toolkit([get_weather])
prompt = toolkit.prompt()
```

This generates:

```
You have access to the following tools via Python function calls.

Available tools:

def get_weather(location: str, unit: str = 'celsius') -> dict:
    """Get current weather for a location.

    Args:
        location: City and state, e.g. "San Francisco, CA"
        unit: Temperature unit - "celsius" or "fahrenheit"
    """

IMPORTANT: Combine ALL operations into a single code block.

Write Python code in a ```python code block.

Chain results: store tool outputs in variables, pass them to subsequent calls or conditions.
For parallel execution, use asyncio:
    import asyncio
    async def main():
        a, b = await asyncio.gather(asyncio.to_thread(tool1, ...), asyncio.to_thread(tool2, ...))
        print(a, b)
    asyncio.run(main())

Environment: json, math, re, asyncio are pre-imported. You can also import other standard library modules (collections, datetime, itertools, etc.).
Restrictions: No file I/O, networking, or shell access (os, subprocess, socket, etc. are blocked).

ALWAYS print() the final result you want to return.
```

### 2. Send to your LLM

Use the generated prompt as your system message (or append it to one):

```python
from openai import OpenAI

client = OpenAI()
response = client.chat.completions.create(
    model="gpt-4.1-mini",
    messages=[
        {"role": "system", "content": prompt},
        {"role": "user", "content": "What's the weather in San Francisco?"},
    ],
)

llm_text = response.choices[0].message.content
```

The LLM responds with something like:

````
I'll check the weather for you.

```python
weather = get_weather("San Francisco, CA")
print(f"Weather in SF: {weather['condition']}, {weather['temp']}°C")
```
````

### 3. Extract and execute

```python
code = toolkit.extract_code(llm_text)
if code:
    result = toolkit.execute(code)
    print(result.output)       # "Weather in SF: sunny, 22°C"
    print(result.tool_calls)   # [{"name": "get_weather", "args": (...), ...}]
```

## Customizing the prompt

### Custom preamble and postamble

```python
toolkit = Toolkit(
    tools=[get_weather],
    preamble="You are a weather assistant with these tools:",
    postamble="Always print results as JSON.",
)
```

### Combining with your own system prompt

```python
system_prompt = f"""You are a helpful assistant.

{toolkit.prompt()}

Additional rules:
- Always respond in English
- Be concise
"""
```

## Full example

```python
from ez_ptc import Toolkit, ez_tool
from openai import OpenAI

@ez_tool
def get_weather(location: str) -> dict:
    """Get weather for a location."""
    return {"temp": 22, "condition": "sunny"}

toolkit = Toolkit([get_weather])
client = OpenAI()

# 1. Generate prompt
prompt = toolkit.prompt()

# 2. Call LLM
response = client.chat.completions.create(
    model="gpt-4.1-mini",
    messages=[
        {"role": "system", "content": prompt},
        {"role": "user", "content": "Weather in NYC?"},
    ],
)

# 3. Extract and execute
code = toolkit.extract_code(response.choices[0].message.content)
if code:
    result = toolkit.execute(code)
    if result.success:
        print(result.output)
    else:
        print(f"Error: {result.error}")
```

## Code extraction details

`toolkit.extract_code()` searches for fenced code blocks in this order:

1. `` ```python ... ``` `` — Python-specific blocks (preferred)
2. `` ``` ... ``` `` — Generic code blocks (fallback)

Returns the first match, or `None` if no code block is found. Only the code inside the fence is returned (no backticks or language tag).
