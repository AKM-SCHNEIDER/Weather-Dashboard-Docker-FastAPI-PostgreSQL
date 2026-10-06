import time
import requests
from datetime import datetime
from fastapi import FastAPI, Query
import psycopg2
from fastapi.middleware.cors import CORSMiddleware
import os

app = FastAPI()

API_KEY = os.getenv("API_KEY")

# ---------------- CORS ----------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------- DB ----------------

def get_db_connection():
    return psycopg2.connect(
        host="db",
        database="weather",
        user="user",
        password="password",
    )


# ---------------- INIT DB ----------------

def init_db():
    """Create table. Retries because Postgres may not be ready immediately."""
    for attempt in range(10):
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS weather (
                    id SERIAL PRIMARY KEY,
                    city VARCHAR(100),
                    forecast_time TIMESTAMP,
                    temperature FLOAT,
                    pressure FLOAT,
                    humidity FLOAT
                );
                """
            )
            conn.commit()
            cur.close()
            conn.close()
            print("DB init success")
            return
        except Exception as e:
            print(f"DB init attempt {attempt+1} failed: {e}. Retrying in 3s...")
            time.sleep(3)

    print("DB init failed after 30s")


# ---------------- WEATHER FETCH ----------------
# OpenWeather free API 5-day forecast (3-hour steps)

def fetch_weather(city: str = "Aachen"):
    """Fetch forecast for a city and store into DB.

    Returns:
        (updated: bool, error: str|None)

    error can contain a message like:
    - "City 'X' not found"
    - "Geocoding API error: ..."
    - "OpenWeather API error: ..."
    """
    updated = False
    api_error = None


    # Geocode city
    geo_url = f"http://nominatim.openstreetmap.org/search?q={city}&format=json&limit=1"
    try:
        geo_res = requests.get(
            geo_url,
            headers={"User-Agent": "WeatherApp"},
            timeout=20,
        )
        geo_res.raise_for_status()
        geo_data = geo_res.json()
    except Exception as e:
        api_error = f"Geocoding API error: {e}"
        print(api_error)
        return updated, api_error

    if not geo_data:
        api_error = f"City '{city}' not found"
        print(api_error)
        return updated, api_error


    lat = float(geo_data[0]["lat"])
    lon = float(geo_data[0]["lon"])

    
    url = (
        "https://api.openweathermap.org/data/2.5/forecast"
        f"?lat={lat}&lon={lon}&appid={API_KEY}&units=metric"
    )

    try:
        res = requests.get(url, timeout=20)
        res.raise_for_status()
        data = res.json()
        print(f"Forecast API status: {res.status_code} for {city}")
    except Exception as e:
        api_error = f"OpenWeather API error: {e}"
        print(api_error)
        return updated, api_error


    # First 8 items => next 24 hours (8 * 3h)
    hourly_list = data["list"][0:8]

    conn = get_db_connection()
    cur = conn.cursor()

    for item in hourly_list:
        forecast_time = datetime.fromtimestamp(item["dt"])
        main = item["main"]
        temp = main["temp"]
        pressure = main["pressure"]
        humidity = main["humidity"]

        # Check if exists for this city+forecast_time
        cur.execute(
            """
            SELECT temperature, pressure, humidity
            FROM weather
            WHERE city = %s AND forecast_time = %s;
            """,
            (city, forecast_time),
        )
        existing = cur.fetchone()

        if existing is None:
            cur.execute(
                """
                INSERT INTO weather (city, forecast_time, temperature, pressure, humidity)
                VALUES (%s, %s, %s, %s, %s);
                """,
                (city, forecast_time, temp, pressure, humidity),
            )
            updated = True
            print(f"Inserted new forecast for {city} {forecast_time}")
        else:
            et, ep, eh = existing
            if abs(temp - et) > 0.2 or pressure != ep or humidity != eh:
                cur.execute(
                    """
                    UPDATE weather
                    SET temperature = %s, pressure = %s, humidity = %s
                    WHERE city = %s AND forecast_time = %s;
                    """,
                    (temp, pressure, humidity, city, forecast_time),
                )
                updated = True
                print(f"Updated forecast for {city} {forecast_time}")

    conn.commit()
    cur.close()
    conn.close()

    print(f"Successfully fetched and stored data for {city}. updated={updated}")
    return updated, api_error


# ---------------- API ENDPOINTS ----------------

@app.get("/health")
def health():
    """Check if OpenWeather API is currently reachable.
    For this beginner project we do a simple lightweight request to OpenWeather
    using the configured API_KEY and a fixed reference city.
    """
    try:

        test_url = (
            "https://api.openweathermap.org/data/2.5/weather"
            f"?q=Aachen&appid={API_KEY}&units=metric"
        )
        r = requests.get(test_url, timeout=10)
        r.raise_for_status()
        return {"available": True}
    except Exception as e:
        return {"available": False, "message": "Sorry, the API is not available at this moment"}


@app.get("/data")
def get_data(city: str = Query("Aachen")):
    updated, error = fetch_weather(city)

    # Return stats (from DB) even if the API failed.
    # If nothing is in DB yet, averages will become 0.
    data = stats(city)
    data["updated"] = updated

    if error is not None:
        data["apiStatus"] = "error"
        # If the city is wrong/typo, show a friendlier message in the frontend
        if error.startswith("City '") and " not found" in error:
            data["message"] = "Sorry, city not found. Please check the spelling and try again..."
        else:
            data["message"] = "⚠️ Sorry, the API is not available right now. Please try later."
        data["detail"] = error
    else:
        data["apiStatus"] = "ok"


    return data



@app.get("/stats")

def stats(city: str = Query("Aachen")):

    conn = get_db_connection()
    cur = conn.cursor()

    # Hourly data for city (last 48 entries, sort by time)
    cur.execute(
        """
        SELECT forecast_time, temperature, pressure, humidity
        FROM weather
        WHERE city = %s
        ORDER BY forecast_time ASC
        LIMIT 48;
        """,
        (city,),
    )
    rows = cur.fetchall()

    hourly = []
    temps = []
    pressures = []
    humidities = []

    for r in rows:
        hourly.append(
            {
                "time": r[0].strftime("%Y-%m-%d %H:%M"),
                "temp": r[1],
                "pressure": r[2],
                "humidity": r[3],
            }
        )
        temps.append(r[1])
        pressures.append(r[2])
        humidities.append(r[3])

    # Specific averages for city
    cur.execute(
        """
        SELECT AVG(temperature) FROM weather
        WHERE city = %s AND EXTRACT(HOUR FROM forecast_time) BETWEEN 8 AND 15;
        """,
        (city,),
    )
    avg_8_15 = cur.fetchone()[0] or 0

    cur.execute(
        """
        SELECT AVG(temperature) FROM weather
        WHERE city = %s AND EXTRACT(HOUR FROM forecast_time) BETWEEN 16 AND 22;
        """,
        (city,),
    )
    avg_16_22 = cur.fetchone()[0] or 0

    cur.close()
    conn.close()

    return {
        "hourly": hourly,
        "avg_temp": sum(temps) / len(temps) if temps else 0,
        "avg_pressure": sum(pressures) / len(pressures) if pressures else 0,
        "avg_humidity": sum(humidities) / len(humidities) if humidities else 0,
        "avg_8_15_temp": round(avg_8_15, 1),
        "avg_16_22_temp": round(avg_16_22, 1),
    }


# -- HISTORY -----

@app.get("/history")
def history():

    """Return list of cities that exist in DB."""
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT DISTINCT city
        FROM weather
        ORDER BY city ASC;
        """
    )
    cities = [r[0] for r in cur.fetchall()]

    cur.close()
    conn.close()
    return {"cities": cities}

init_db()

