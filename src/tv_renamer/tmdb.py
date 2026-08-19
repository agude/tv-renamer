"""TMDB API client for searching shows and fetching episode metadata."""

from __future__ import annotations

import os
from dataclasses import dataclass

import requests

BASE_URL = "https://api.themoviedb.org/3"
MEDIA_EXTENSIONS = frozenset(
    {
        ".mkv",
        ".mp4",
        ".avi",
        ".ts",
        ".m4v",
        ".wmv",
        ".flv",
        ".mov",
        ".webm",
    }
)


def _api_key() -> str:
    key = os.environ.get("TMDB_API_KEY", "")
    if not key:
        raise RuntimeError("TMDB_API_KEY environment variable is not set")
    return key


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


def search_tv(query: str) -> list[SearchResult]:
    resp = requests.get(
        f"{BASE_URL}/search/tv",
        params={"api_key": _api_key(), "query": query},
        timeout=10,
    )
    resp.raise_for_status()
    results: list[SearchResult] = []
    for item in resp.json().get("results", []):
        results.append(
            SearchResult(
                tmdb_id=item["id"],
                name=item.get("name", ""),
                first_air_date=item.get("first_air_date", ""),
                overview=item.get("overview", ""),
                media_type="tv",
            )
        )
    return results


def search_movie(query: str) -> list[SearchResult]:
    resp = requests.get(
        f"{BASE_URL}/search/movie",
        params={"api_key": _api_key(), "query": query},
        timeout=10,
    )
    resp.raise_for_status()
    results: list[SearchResult] = []
    for item in resp.json().get("results", []):
        results.append(
            SearchResult(
                tmdb_id=item["id"],
                name=item.get("title", ""),
                first_air_date=item.get("release_date", ""),
                overview=item.get("overview", ""),
                media_type="movie",
            )
        )
    return results


def get_show(tmdb_id: int) -> ShowInfo:
    resp = requests.get(
        f"{BASE_URL}/tv/{tmdb_id}",
        params={"api_key": _api_key()},
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
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


def get_episodes(tmdb_id: int, season: int) -> list[Episode]:
    resp = requests.get(
        f"{BASE_URL}/tv/{tmdb_id}/season/{season}",
        params={"api_key": _api_key()},
        timeout=10,
    )
    resp.raise_for_status()
    episodes: list[Episode] = []
    for ep in resp.json().get("episodes", []):
        episodes.append(
            Episode(
                season=ep["season_number"],
                episode=ep["episode_number"],
                name=ep.get("name", ""),
            )
        )
    return episodes
