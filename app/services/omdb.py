import httpx

from app.config import get_settings


class OMDBError(Exception):
    pass


def _params(**extra) -> dict:
    settings = get_settings()
    if not settings.omdb_api_key:
        raise OMDBError("OMDB_API_KEY is not configured")
    return {"apikey": settings.omdb_api_key, **extra}


def search(query: str) -> list[dict]:
    """Returns a list of {imdb_id, title, year, poster_url}."""
    with httpx.Client(timeout=10) as client:
        resp = client.get("https://www.omdbapi.com/", params=_params(s=query, type="movie"))
        resp.raise_for_status()
        data = resp.json()

    if data.get("Response") == "False":
        return []

    return [
        {
            "imdb_id": item["imdbID"],
            "title": item.get("Title", ""),
            "year": item.get("Year", ""),
            "poster_url": None if item.get("Poster") == "N/A" else item.get("Poster"),
        }
        for item in data.get("Search", [])
    ]


def get_by_imdb_id(imdb_id: str) -> dict:
    """Returns {imdb_id, title, year, poster_url, plot} or raises OMDBError."""
    with httpx.Client(timeout=10) as client:
        resp = client.get("https://www.omdbapi.com/", params=_params(i=imdb_id))
        resp.raise_for_status()
        data = resp.json()

    if data.get("Response") == "False":
        raise OMDBError(data.get("Error", "Movie not found"))

    return {
        "imdb_id": data["imdbID"],
        "title": data.get("Title", ""),
        "year": data.get("Year", ""),
        "poster_url": None if data.get("Poster") == "N/A" else data.get("Poster"),
        "plot": None if data.get("Plot") == "N/A" else data.get("Plot"),
    }
