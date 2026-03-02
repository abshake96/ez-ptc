"""ez-ptc — Pydantic BaseModel return types for tool chaining.

Demonstrates how Pydantic models as return type annotations enable
rich tool chaining: the LLM sees the exact schema of each tool's
output and can confidently access result fields.

No API keys required.

Usage:
    uv run python examples/advanced/example_pydantic_models.py

Requires:
    pip install pydantic  (already a dependency of ez-ptc's dev tools)
"""

from pydantic import BaseModel

from ez_ptc import Toolkit, ez_tool


# ── Pydantic models as return types ──────────────────────────────────


class Location(BaseModel):
    city: str
    country: str
    latitude: float
    longitude: float


class WeatherReport(BaseModel):
    location: str
    temp_celsius: float
    humidity: int
    condition: str
    wind_kph: float


class Restaurant(BaseModel):
    name: str
    cuisine: str
    rating: float
    price_range: str


@ez_tool
def geocode(city: str) -> Location:
    """Geocode a city name to coordinates.

    Args:
        city: City name, e.g. "Paris"
    """
    cities = {
        "Paris": Location(city="Paris", country="France", latitude=48.86, longitude=2.35),
        "Tokyo": Location(city="Tokyo", country="Japan", latitude=35.68, longitude=139.69),
        "New York": Location(city="New York", country="USA", latitude=40.71, longitude=-74.01),
    }
    return cities.get(city, Location(city=city, country="Unknown", latitude=0.0, longitude=0.0))


@ez_tool
def get_weather(lat: float, lon: float) -> WeatherReport:
    """Get weather at coordinates.

    Args:
        lat: Latitude
        lon: Longitude
    """
    return WeatherReport(
        location=f"{lat:.1f},{lon:.1f}",
        temp_celsius=22.5,
        humidity=65,
        condition="partly cloudy",
        wind_kph=12.0,
    )


@ez_tool
def find_restaurants(city: str, cuisine: str = "any") -> list[Restaurant]:
    """Find restaurants in a city.

    Args:
        city: City to search
        cuisine: Cuisine filter
    """
    return [
        Restaurant(name=f"Le {city} Bistro", cuisine="French", rating=4.5, price_range="$$$"),
        Restaurant(name=f"{city} Sushi Bar", cuisine="Japanese", rating=4.2, price_range="$$"),
    ]


def demo_chaining_enabled():
    """With assist_tool_chaining=True, the LLM sees exact return schemas."""
    print("=" * 60)
    print("1. Prompt with Pydantic Return Schemas")
    print("=" * 60)

    toolkit = Toolkit(
        [geocode, get_weather, find_restaurants],
        assist_tool_chaining=True,
    )

    prompt = toolkit.prompt()
    # Show just the tool signatures + return schemas
    for line in prompt.split("\n"):
        if "# Returns:" in line or line.startswith("def "):
            print(f"  {line}")
    print()


def demo_chaining_disabled():
    """Without chaining, the LLM gets no return type info."""
    print("=" * 60)
    print("2. Prompt without Return Schemas (default)")
    print("=" * 60)

    toolkit = Toolkit(
        [geocode, get_weather, find_restaurants],
        assist_tool_chaining=False,
    )

    prompt = toolkit.prompt()
    for line in prompt.split("\n"):
        if line.startswith("def "):
            print(f"  {line}")
    print()
    print("  Notice: no '# Returns:' comments — LLM must guess key names.")
    print()


def demo_execution():
    """Execute code that chains Pydantic-typed tools."""
    print("=" * 60)
    print("3. Execution — Chaining Pydantic Tools")
    print("=" * 60)

    toolkit = Toolkit(
        [geocode, get_weather, find_restaurants],
        assist_tool_chaining=True,
    )

    code = """
# Chain: geocode -> get_weather, and find_restaurants
loc = geocode("Paris")
weather = get_weather(loc.latitude, loc.longitude)
restaurants = find_restaurants(loc.city, cuisine="French")

print(f"City: {loc.city}, {loc.country}")
print(f"Weather: {weather.temp_celsius}C, {weather.condition}")
print(f"Top restaurant: {restaurants[0].name} ({restaurants[0].rating} stars)")
"""
    result = toolkit.execute_sync(code)
    print(f"  Output:\n{result.output}", end="")
    print(f"  Tool calls: {[tc['name'] for tc in result.tool_calls]}")
    print()


def demo_tool_schema():
    """Show how Pydantic schemas appear in the OpenAI tool schema."""
    print("=" * 60)
    print("4. Tool Schema — Pydantic in tool_schema()")
    print("=" * 60)

    toolkit = Toolkit(
        [geocode, get_weather, find_restaurants],
        assist_tool_chaining=True,
    )

    schema = toolkit.tool_schema()
    desc = schema["function"]["description"]
    # Show the Returns: hints in the description
    for line in desc.split("\n"):
        if "Returns:" in line or "geocode" in line or "get_weather" in line or "find_restaurants" in line:
            print(f"  {line.strip()}")
    print()


if __name__ == "__main__":
    demo_chaining_enabled()
    demo_chaining_disabled()
    demo_execution()
    demo_tool_schema()
