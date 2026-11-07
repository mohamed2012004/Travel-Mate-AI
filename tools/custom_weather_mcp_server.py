from mcp.server.fastmcp import FastMCP
import requests
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

mcp = FastMCP("Weather MCP Server")


WEATHERAPI_API_KEY = os.getenv("WEATHERAPI_API_KEY") or os.getenv("OPENWEATHER_API_KEY")
WEATHERAPI_BASE_URL = "https://api.weatherapi.com/v1"


@mcp.tool()
def get_current_weather(city: str):
    """Current weather for a city: temperature (celsius), humidity, wind (km/h)."""

    response = requests.get(
        f"{WEATHERAPI_BASE_URL}/current.json",
        params={
            "key": WEATHERAPI_API_KEY,
            "q": city
        },
        timeout=10
    )

    data = response.json()

    if response.status_code != 200:
        return data

    current = data["current"]

    return {
        "city": data["location"]["name"],
        "temperature_c": current["temp_c"],
        "feels_like_c": current["feelslike_c"],
        "humidity": current["humidity"],
        "condition": current["condition"]["text"],
        "wind_kph": current["wind_kph"]
    }



@mcp.tool()
def get_forecast(city: str, days: int = 5):
    """Daily forecast for a city for the next 1-10 days."""

    response = requests.get(
        f"{WEATHERAPI_BASE_URL}/forecast.json",
        params={
            "key": WEATHERAPI_API_KEY,
            "q": city,
            "days": min(max(days, 1), 10)
        },
        timeout=10
    )

    data = response.json()

    if response.status_code != 200:
        return data

    forecast = []

    for day in data["forecast"]["forecastday"]:
        day_data = day["day"]

        forecast.append(
            {
                "date": day["date"],
                "temperature_c": day_data["avgtemp_c"],
                "high_c": day_data["maxtemp_c"],
                "low_c": day_data["mintemp_c"],
                "weather": day_data["condition"]["text"],
                "chance_of_rain": day_data["daily_chance_of_rain"]
            }
        )

    return {
        "city": data["location"]["name"],
        "forecast": forecast
    }




if __name__ == "__main__":
    mcp.run()
