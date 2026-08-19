"""Tests for TMDB API client with mocked HTTP responses."""

from unittest.mock import MagicMock, patch

import pytest

from tv_renamer.tmdb import TMDBClient


@pytest.fixture()
def client():
    with patch.dict("os.environ", {"TMDB_API_KEY": "fake-key"}):
        c = TMDBClient()
        yield c


def _mock_response(json_data: dict) -> MagicMock:
    resp = MagicMock()
    resp.json.return_value = json_data
    resp.raise_for_status.return_value = None
    return resp


class TestSearchTV:
    def test_parses_results(self, client: TMDBClient):
        client._session.get = MagicMock(
            return_value=_mock_response(
                {
                    "results": [
                        {
                            "id": 246,
                            "name": "Avatar: The Last Airbender",
                            "first_air_date": "2005-02-21",
                            "overview": "An animated series.",
                        }
                    ]
                }
            )
        )

        results = client.search_tv("avatar")

        assert len(results) == 1
        assert results[0].tmdb_id == 246
        assert results[0].name == "Avatar: The Last Airbender"
        assert results[0].year == "2005"
        assert results[0].media_type == "tv"

    def test_empty_results(self, client: TMDBClient):
        client._session.get = MagicMock(return_value=_mock_response({"results": []}))

        results = client.search_tv("nonexistent")
        assert results == []

    def test_missing_fields_use_defaults(self, client: TMDBClient):
        client._session.get = MagicMock(return_value=_mock_response({"results": [{"id": 1}]}))

        results = client.search_tv("test")
        assert results[0].name == ""
        assert results[0].first_air_date == ""
        assert results[0].overview == ""
        assert results[0].year == "????"


class TestSearchMovie:
    def test_parses_movie_fields(self, client: TMDBClient):
        client._session.get = MagicMock(
            return_value=_mock_response(
                {
                    "results": [
                        {
                            "id": 550,
                            "title": "Fight Club",
                            "release_date": "1999-10-15",
                            "overview": "A ticking-Loss bomb.",
                        }
                    ]
                }
            )
        )

        results = client.search_movie("fight club")

        assert results[0].tmdb_id == 550
        assert results[0].name == "Fight Club"
        assert results[0].year == "1999"
        assert results[0].media_type == "movie"


class TestGetShow:
    def test_parses_show_with_seasons(self, client: TMDBClient):
        client._session.get = MagicMock(
            return_value=_mock_response(
                {
                    "id": 246,
                    "name": "Avatar: The Last Airbender",
                    "first_air_date": "2005-02-21",
                    "seasons": [
                        {"season_number": 1, "episode_count": 20, "name": "Book One: Water"},
                        {"season_number": 2, "episode_count": 20, "name": "Book Two: Earth"},
                    ],
                }
            )
        )

        show = client.get_show(246)

        assert show.tmdb_id == 246
        assert show.name == "Avatar: The Last Airbender"
        assert show.year == "2005"
        assert len(show.seasons) == 2
        assert show.seasons[0].season_number == 1
        assert show.seasons[0].episode_count == 20
        assert show.seasons[0].name == "Book One: Water"

    def test_show_no_seasons(self, client: TMDBClient):
        client._session.get = MagicMock(
            return_value=_mock_response({"id": 1, "name": "Test", "first_air_date": "2020-01-01"})
        )

        show = client.get_show(1)
        assert show.seasons == []


class TestGetEpisodes:
    def test_parses_episode_list(self, client: TMDBClient):
        client._session.get = MagicMock(
            return_value=_mock_response(
                {
                    "episodes": [
                        {"season_number": 1, "episode_number": 1, "name": "The Boy in the Iceberg"},
                        {"season_number": 1, "episode_number": 2, "name": "The Avatar Returns"},
                    ]
                }
            )
        )

        episodes = client.get_episodes(246, 1)

        assert len(episodes) == 2
        assert episodes[0].season == 1
        assert episodes[0].episode == 1
        assert episodes[0].name == "The Boy in the Iceberg"

    def test_empty_season(self, client: TMDBClient):
        client._session.get = MagicMock(return_value=_mock_response({"episodes": []}))

        episodes = client.get_episodes(1, 1)
        assert episodes == []


class TestRateLimiting:
    def test_rate_limiter_sleeps(self, client: TMDBClient):
        client._last_request = 999999999.0
        client._session.get = MagicMock(return_value=_mock_response({"results": []}))

        with (
            patch("tv_renamer.tmdb.time.monotonic", side_effect=[999999999.1, 999999999.3]),
            patch("tv_renamer.tmdb.time.sleep") as mock_sleep,
        ):
            client.search_tv("test")
            mock_sleep.assert_called_once()


class TestApiKey:
    def test_missing_api_key_raises(self):
        with patch.dict("os.environ", {}, clear=True):
            client = TMDBClient()
            client._session.get = MagicMock()
            with pytest.raises(RuntimeError, match="TMDB_API_KEY"):
                client.search_tv("test")

    def test_api_key_passed_as_param(self, client: TMDBClient):
        client._session.get = MagicMock(return_value=_mock_response({"results": []}))

        client.search_tv("test")

        params = client._session.get.call_args[1]["params"]
        assert params["api_key"] == "fake-key"


class TestModuleFunctions:
    def test_module_functions_use_shared_client(self):
        import tv_renamer.tmdb as tmdb_mod

        with patch.dict("os.environ", {"TMDB_API_KEY": "fake-key"}):
            tmdb_mod._client = None
            c1 = tmdb_mod._get_client()
            c2 = tmdb_mod._get_client()
            assert c1 is c2
            tmdb_mod._client = None
