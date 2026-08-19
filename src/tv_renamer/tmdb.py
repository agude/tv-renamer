"""TMDB API client for searching shows and fetching episode metadata."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass

import requests

BASE_URL = "https://api.themoviedb.org/3"
USER_AGENT = "tv-renamer/0.1 (alex.public.account@gmail.com)"
RATE_LIMIT_SECS = 0.25


@dataclass(frozen=True)
class SearchResult:
    tmdb_id: int
    name: str
    first_air_date: str
    overview: str
    media_type: str  # "tv" or "movie"

    @property
    def year(self) -> str:
        return self.first_air_date[:4] if self.first_air_date else "????"


@dataclass(frozen=True)
class Episode:
    season: int
    episode: int
    name: str


@dataclass(frozen=True)
class ShowInfo:
    tmdb_id: int
    name: str
    first_air_date: str
    seasons: list[SeasonSummary]

    @property
    def year(self) -> str:
        return self.first_air_date[:4] if self.first_air_date else "????"


@dataclass(frozen=True)
class SeasonSummary:
    season_number: int
    episode_count: int
    name: str


class TMDBClient:
    """TMDB API client with rate limiting and session reuse."""

    def __init__(self, api_key: str | None = None) -> None:
        key = api_key or os.environ.get("TMDB_API_KEY", "")
        if not key:
            raise RuntimeError("TMDB_API_KEY environment variable is not set")
        self._api_key = key
        self._session = requests.Session()
        self._session.headers["User-Agent"] = USER_AGENT
        self._session.headers["Accept"] = "application/json"
        self._last_request: float = 0.0

    def _rate_limit(self) -> None:
        elapsed = time.monotonic() - self._last_request
        if elapsed < RATE_LIMIT_SECS:
            time.sleep(RATE_LIMIT_SECS - elapsed)
        self._last_request = time.monotonic()

    def _get(self, path: str, **params: str | int) -> dict:  # type: ignore[type-arg]
        self._rate_limit()
        resp = self._session.get(
            f"{BASE_URL}{path}",
            params={"api_key": self._api_key, **params},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()  # type: ignore[no-any-return]

    def search_tv(self, query: str) -> list[SearchResult]:
        data = self._get("/search/tv", query=query)
        return [
            SearchResult(
                tmdb_id=item["id"],
                name=item.get("name", ""),
                first_air_date=item.get("first_air_date", ""),
                overview=item.get("overview", ""),
                media_type="tv",
            )
            for item in data.get("results", [])
        ]

    def search_movie(self, query: str) -> list[SearchResult]:
        data = self._get("/search/movie", query=query)
        return [
            SearchResult(
                tmdb_id=item["id"],
                name=item.get("title", ""),
                first_air_date=item.get("release_date", ""),
                overview=item.get("overview", ""),
                media_type="movie",
            )
            for item in data.get("results", [])
        ]

    def get_show(self, tmdb_id: int) -> ShowInfo:
        data = self._get(f"/tv/{tmdb_id}")
        seasons = [
            SeasonSummary(
                season_number=s["season_number"],
                episode_count=s["episode_count"],
                name=s.get("name", ""),
            )
            for s in data.get("seasons", [])
        ]
        return ShowInfo(
            tmdb_id=data["id"],
            name=data["name"],
            first_air_date=data.get("first_air_date", ""),
            seasons=seasons,
        )

    def get_episodes(self, tmdb_id: int, season: int) -> list[Episode]:
        data = self._get(f"/tv/{tmdb_id}/season/{season}")
        return [
            Episode(
                season=ep["season_number"],
                episode=ep["episode_number"],
                name=ep.get("name", ""),
            )
            for ep in data.get("episodes", [])
        ]
