# Weather Dashboard - Docker, FastAPI & PostgreSQL

A small full-stack weather dashboard built to learn how a frontend, backend, database, external APIs, and Docker work together.

The user searches for a city. The backend finds its coordinates, fetches a 24-hour forecast, saves the forecast in PostgreSQL, calculates averages, and sends the result to the browser.

## Architecture

```text
Browser
  |
  | http://localhost:8080
  v
Frontend container (Nginx)
  |
  | JavaScript requests http://localhost:8000
  v
Backend container (FastAPI / Python)
  |-- asks OpenStreetMap Nominatim for city coordinates
  |-- asks OpenWeather for forecast data
  `-- reads and writes weather data
          |
          v
     PostgreSQL container
```

## Requirements

- Docker Desktop installed and running
- An OpenWeather account and API key

## Configure the API key

Create a file named `.env` in the project root, beside `docker-compose.yml`.

```env
API_KEY=replace_this_with_your_own_openweather_key
```

Do not put the real key in `docker-compose.yml`, source code, a screenshot, or GitHub.

The backend receives the key through this Compose expression:

```yaml
API_KEY: ${API_KEY:?Set API_KEY in a local .env file before starting Docker Compose.}
```

It means:

1. Read `API_KEY` from `.env`.
2. Pass it into the backend container as its `API_KEY` environment variable.
3. Stop immediately with the displayed message if the key is missing.

The `.gitignore` file excludes `.env`; `.env.example` is safe to share because it contains no real secret.

## Run the application

Open PowerShell in this project folder and run:

```powershell
docker compose up --build
```

`--build` creates the frontend and backend images before starting containers. On later runs, use the same command or run Docker Compose without `--build` when no Dockerfile/dependency changes were made.

Open the dashboard at:

```text
http://localhost:8080
```

To stop the running containers, press `Ctrl+C` in the terminal. To stop them in detached mode, run:

```powershell
docker compose down
```

## What happens when you search for a city

For example, when the user searches for `Berlin`:

1. The browser runs `searchCity()` in `frontend/index.html`.
2. JavaScript calls `GET http://localhost:8000/data?city=Berlin`.
3. FastAPI runs `get_data()` in `backend/main.py`.
4. `fetch_weather()` calls OpenStreetMap Nominatim to turn `Berlin` into latitude and longitude.
5. `fetch_weather()` calls OpenWeather's forecast endpoint with those coordinates and the private API key.
6. The first eight three-hour forecast records are selected: approximately the next 24 hours.
7. Python inserts new rows or updates changed rows in PostgreSQL.
8. `stats()` reads saved rows and calculates overall, morning, and evening averages.
9. FastAPI returns JSON to the browser.
10. JavaScript builds the forecast table and statistic cards on the page.

## Backend API routes

| Route | Example | Purpose |
|---|---|---|
| `GET /health` | `http://localhost:8000/health` | Checks whether OpenWeather can be reached |
| `GET /data` | `http://localhost:8000/data?city=Berlin` | Fetches fresh data, saves it, then returns statistics |
| `GET /stats` | `http://localhost:8000/stats?city=Berlin` | Returns only already-saved statistics from PostgreSQL |
| `GET /history` | `http://localhost:8000/history` | Returns every city stored in the database |

An example `/data` response has this shape:

```json
{
  "hourly": [
    {
      "time": "2026-10-06 12:00",
      "temp": 15.2,
      "pressure": 1015.0,
      "humidity": 62.0
    }
  ],
  "avg_temp": 15.2,
  "avg_pressure": 1015.0,
  "avg_humidity": 62.0,
  "avg_8_15_temp": 14.8,
  "avg_16_22_temp": 16.1,
  "updated": true,
  "apiStatus": "ok"
}
```

## Database

The backend creates this table on startup if it does not exist:

```sql
CREATE TABLE weather (
    id SERIAL PRIMARY KEY,
    city VARCHAR(100),
    forecast_time TIMESTAMP,
    temperature FLOAT,
    pressure FLOAT,
    humidity FLOAT
);
```

Each row represents one forecast value for one city and forecast time.

`init_db()` retries the initial connection up to ten times because Docker may start the backend before PostgreSQL is ready to accept connections.

## Important implementation details

- The frontend uses `localhost:8000` because this is a local-learning project. In a deployed website, this URL must be changed to the real backend domain or handled through a reverse proxy.
- `/data` both fetches external data and writes to the database. Each open browser refreshes it at page load and every ten minutes.
- The OpenWeather forecast endpoint returns data in three-hour steps. Eight records are about 24 hours.
- CORS is currently open to all origins (`allow_origins=["*"]`) to make local development easy. Restrict it before a public deployment.
- There is currently no named Docker volume for PostgreSQL. Removing the database container can remove the saved forecast data.

## Useful Docker commands

```powershell
# Show running containers for this project
docker compose ps

# Follow backend logs
docker compose logs -f backend

# Rebuild and restart after changing Dockerfiles or dependencies
docker compose up --build

# Stop and remove project containers
docker compose down
```

## Troubleshooting

### Docker is not running

Start Docker Desktop and wait until it reports that Docker is running. Then run `docker compose up --build` again.

### Docker says API_KEY is missing

Check that `.env` is in the same folder as `docker-compose.yml` and contains:

```env
API_KEY=your_real_key
```

### The frontend cannot get data

Check the backend logs:

```powershell
docker compose logs backend
```

Then visit `http://localhost:8000/health`. It should return `{"available": true}` when OpenWeather is reachable and the key works.

### Port is already in use

Another program is using port 8080, 8000, or 5432. Stop that program, or change the left-hand port in `docker-compose.yml`. For example, `"8081:80"` would make the frontend available at `http://localhost:8081`.

## Next improvements

1. Add a named PostgreSQL volume so data survives container removal.
2. Add a unique database constraint for `(city, forecast_time)` to prevent duplicate rows during simultaneous requests.
3. Store database credentials in `.env` too.
4. Use UTC-aware timestamps for predictable displayed times.
5. Restrict CORS to the frontend's actual domain.
6. Replace dynamic `innerHTML` city links with safe DOM element creation.
7. Add automated tests and pinned dependency versions.

