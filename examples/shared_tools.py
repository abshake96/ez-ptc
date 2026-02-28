"""Shared tool definitions used by all examples."""

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
    """Get current weather for a location.

    Args:
        location: City and state, e.g. "San Francisco, CA"
        unit: Temperature unit - "celsius" or "fahrenheit"
    """
    # Simulated weather data
    data = {
        "San Francisco, CA": {"temp_c": 18, "condition": "foggy"},
        "New York, NY": {"temp_c": 25, "condition": "sunny"},
        "London, UK": {"temp_c": 14, "condition": "rainy"},
    }
    city_data = data.get(location, {"temp_c": 20, "condition": "partly cloudy"})
    temp = city_data["temp_c"] if unit == "celsius" else round(city_data["temp_c"] * 9 / 5 + 32)
    return {"location": location, "temp": temp, "unit": unit, "condition": city_data["condition"]}


@ez_tool
def search_products(query: str, limit: int = 5) -> list[ProductResult]:
    """Search the product catalog.

    Args:
        query: Search query string
        limit: Maximum number of results to return
    """
    # Simulated product catalog
    catalog = [
        {"id": 1, "name": "Umbrella", "price": 24.99, "tags": ["rain", "weather"]},
        {"id": 2, "name": "Sunglasses", "price": 49.99, "tags": ["sun", "weather"]},
        {"id": 3, "name": "Rain Jacket", "price": 89.99, "tags": ["rain", "weather"]},
        {"id": 4, "name": "Sun Hat", "price": 29.99, "tags": ["sun", "weather"]},
        {"id": 5, "name": "Snow Boots", "price": 119.99, "tags": ["snow", "weather"]},
        {"id": 6, "name": "Thermal Gloves", "price": 34.99, "tags": ["cold", "weather"]},
    ]
    q = query.lower()
    results = [p for p in catalog if q in p["name"].lower() or any(q in t for t in p["tags"])]
    if not results:
        results = catalog  # fallback: return everything
    return results[:limit]


USER_PROMPT = (
    "Check the weather in San Francisco, CA and New York, NY. "
    "Then search for products appropriate for each city's weather. "
    "Print a summary of your findings."
)

# Two toolkits for comparison — with and without tool chaining
toolkit = Toolkit([get_weather, search_products], assist_tool_chaining=True)
toolkit_basic = Toolkit([get_weather, search_products], assist_tool_chaining=False)
