# Contributing to ez-ptc

Thanks for your interest in contributing!

## Development setup

```bash
# Clone the repo
git clone https://github.com/abhisheksatish/ez-ptc.git
cd ez-ptc

# Install with dev dependencies (requires uv)
uv sync

# Run tests
uv run pytest tests/
```

## Running examples

Examples require API keys set in your environment:

```bash
export OPENAI_API_KEY=sk-...
export ANTHROPIC_API_KEY=sk-ant-...

uv run python examples/example_openai.py
```

## Code style

- Type annotations on all public functions
- Google-style docstrings
- Keep the package zero-dependency — no runtime deps

## Pull requests

1. Fork the repo and create a branch
2. Make your changes
3. Ensure all tests pass: `uv run pytest tests/`
4. Submit a PR with a clear description of what changed and why
