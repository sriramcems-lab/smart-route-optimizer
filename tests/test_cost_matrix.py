"""
Unit tests for Cost Matrix and Route Geometry services.
Tests Haversine mathematics, simulated physics mode, mocked Google Routes API (v2),
and in-memory caching.
"""

from unittest.mock import MagicMock, patch
import pytest
import numpy as np
import requests

from optimizer.cost_matrix import (
    haversine_distance_meters,
    compute_simulated_cost_matrix,
    compute_live_google_route_matrix,
    get_cost_matrices,
    clear_matrix_cache,
    is_live_key_available,
    parse_duration_string,
    CostMatrixError,
)
from optimizer.route_service import (
    encode_polyline,
    compute_simulated_route_geometry,
    compute_live_google_route,
    get_route_geometry,
    clear_route_cache,
    RouteServiceError,
)


@pytest.fixture(autouse=True)
def reset_caches():
    """Clear memory caches before each test."""
    clear_matrix_cache()
    clear_route_cache()


class TestHaversineAndHelpers:
    """Tests for physical distance and duration helper functions."""

    def test_haversine_identical_point(self):
        # Distance to self should be 0.0
        dist = haversine_distance_meters(12.9716, 77.5946, 12.9716, 77.5946)
        assert dist == 0.0

    def test_haversine_known_distance(self):
        # Bangalore MG Road (12.9756, 77.6066) to Kempegowda Airport (13.1986, 77.7066)
        # Approximate straight-line distance is ~27.2 km (27,000 - 28,000 meters)
        dist = haversine_distance_meters(12.9756, 77.6066, 13.1986, 77.7066)
        assert 26000.0 < dist < 28500.0

    def test_parse_duration_string(self):
        assert parse_duration_string("120s") == 120.0
        assert parse_duration_string("3600.5s") == 3600.5
        assert parse_duration_string("0s") == 0.0
        assert parse_duration_string("") == 0.0
        assert parse_duration_string(None) == 0.0
        assert parse_duration_string("invalid") == 0.0

    def test_is_live_key_available(self):
        assert is_live_key_available(None) is False
        assert is_live_key_available("") is False
        assert is_live_key_available("   ") is False
        assert is_live_key_available("your_server_key_here") is False
        assert is_live_key_available("your_google_maps_server_api_key_here") is False
        assert is_live_key_available("AIzaSyB3Xxxxxxxxxxxxxxxx") is True


class TestSimulatedCostMatrix:
    """Tests for Demo Mode cost matrix calculations."""

    @pytest.fixture
    def sample_stops(self):
        return [
            {"lat": 12.9716, "lng": 77.5946, "label": "Start"},
            {"lat": 12.9352, "lng": 77.6245, "label": "Stop 1"},
            {"lat": 13.1986, "lng": 77.7066, "label": "Destination"},
        ]

    def test_simulated_matrix_structure(self, sample_stops):
        result = compute_simulated_cost_matrix(sample_stops)

        assert result["dataSource"] == "SIMULATED DATA"
        assert result["is_simulated"] is True

        dist_mat = result["distance_matrix"]
        dur_mat = result["duration_matrix"]

        assert isinstance(dist_mat, np.ndarray)
        assert isinstance(dur_mat, np.ndarray)
        assert dist_mat.shape == (3, 3)
        assert dur_mat.shape == (3, 3)

        # Diagonals must be 0
        for i in range(3):
            assert dist_mat[i, i] == 0.0
            assert dur_mat[i, i] == 0.0

        # Off-diagonals must be positive
        for i in range(3):
            for j in range(3):
                if i != j:
                    assert dist_mat[i, j] > 0.0
                    assert dur_mat[i, j] > 0.0

    def test_get_cost_matrices_demo_fallback(self, sample_stops):
        # When server_api_key is empty, automatically uses Demo Mode
        res = get_cost_matrices(sample_stops, server_api_key="")
        assert res["dataSource"] == "SIMULATED DATA"
        assert res["is_simulated"] is True

    def test_caching_behavior(self, sample_stops):
        # First call populates cache
        res1 = get_cost_matrices(sample_stops, server_api_key="")
        # Second call should return identical matrix from cache
        res2 = get_cost_matrices(sample_stops, server_api_key="")

        np.testing.assert_array_equal(res1["distance_matrix"], res2["distance_matrix"])
        np.testing.assert_array_equal(res1["duration_matrix"], res2["duration_matrix"])


class TestMockedLiveGoogleRouteMatrix:
    """Tests for live Google Routes API v2 handling using mocks (no live billing)."""

    @pytest.fixture
    def sample_stops(self):
        return [
            {"lat": 12.9716, "lng": 77.5946},
            {"lat": 12.9352, "lng": 77.6245},
        ]

    @patch("optimizer.cost_matrix.requests.post")
    def test_successful_live_matrix_call(self, mock_post, sample_stops):
        # Mock Google computeRouteMatrix streaming response payload
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"originIndex": 0, "destinationIndex": 0, "distanceMeters": 0, "duration": "0s", "condition": "ROUTE_EXISTS"},
            {"originIndex": 0, "destinationIndex": 1, "distanceMeters": 5400, "duration": "720s", "condition": "ROUTE_EXISTS"},
            {"originIndex": 1, "destinationIndex": 0, "distanceMeters": 5600, "duration": "750s", "condition": "ROUTE_EXISTS"},
            {"originIndex": 1, "destinationIndex": 1, "distanceMeters": 0, "duration": "0s", "condition": "ROUTE_EXISTS"},
        ]
        mock_post.return_value = mock_response

        result = compute_live_google_route_matrix(sample_stops, server_api_key="valid-mock-key")

        assert result["dataSource"] == "LIVE GOOGLE DATA"
        assert result["is_simulated"] is False

        dist_matrix = result["distance_matrix"]
        time_matrix = result["duration_matrix"]

        assert dist_matrix[0, 1] == 5400.0
        assert dist_matrix[1, 0] == 5600.0
        assert time_matrix[0, 1] == 720.0
        assert time_matrix[1, 0] == 750.0

        # Verify Google Routes API headers were set
        call_args = mock_post.call_args
        assert call_args[1]["headers"]["X-Goog-Api-Key"] == "valid-mock-key"
        assert "originIndex,destinationIndex" in call_args[1]["headers"]["X-Goog-FieldMask"]

    @patch("optimizer.cost_matrix.requests.post")
    def test_live_matrix_error_response(self, mock_post, sample_stops):
        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.json.return_value = {
            "error": {"code": 403, "message": "The provided API key is invalid."}
        }
        mock_post.return_value = mock_response

        with pytest.raises(CostMatrixError) as exc_info:
            compute_live_google_route_matrix(sample_stops, server_api_key="bad-key")

        assert "HTTP 403" in str(exc_info.value)
        assert "API key is invalid" in str(exc_info.value)

    @patch("optimizer.cost_matrix.requests.post")
    def test_live_matrix_route_not_found(self, mock_post, sample_stops):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"originIndex": 0, "destinationIndex": 1, "condition": "ROUTE_NOT_FOUND"}
        ]
        mock_post.return_value = mock_response

        with pytest.raises(CostMatrixError) as exc_info:
            compute_live_google_route_matrix(sample_stops, server_api_key="valid-mock-key")

        assert "No driving route could be found" in str(exc_info.value)


class TestRouteGeometryService:
    """Tests for polyline encoding and route service (Demo and Live modes)."""

    def test_encode_polyline_standard_algorithm(self):
        # Known test vector from Google Maps polyline documentation:
        # [(38.5, -120.2), (40.7, -120.95), (43.252, -126.453)]
        coords = [(38.5, -120.2), (40.7, -120.95), (43.252, -126.453)]
        encoded = encode_polyline(coords)
        assert encoded == "_p~iF~ps|U_ulLnnqC_mqNvxq`@"

        # Also verify empty list
        assert encode_polyline([]) == ""

    def test_simulated_route_geometry(self):
        stops = [
            {"lat": 12.9716, "lng": 77.5946},
            {"lat": 12.9352, "lng": 77.6245},
            {"lat": 13.1986, "lng": 77.7066},
        ]
        res = compute_simulated_route_geometry(stops)
        assert res["dataSource"] == "SIMULATED DATA"
        assert res["is_simulated"] is True
        assert isinstance(res["polyline"], str)
        assert len(res["polyline"]) > 0
        assert len(res["legs"]) == 2
        assert res["total_distance_meters"] > 0.0

    @patch("optimizer.route_service.requests.post")
    def test_mocked_live_google_route(self, mock_post):
        stops = [
            {"lat": 12.9716, "lng": 77.5946},
            {"lat": 12.9352, "lng": 77.6245},
            {"lat": 13.1986, "lng": 77.7066},
        ]
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "routes": [
                {
                    "distanceMeters": 42000,
                    "duration": "3600s",
                    "polyline": {"encodedPolyline": "mocked_encoded_polyline_abc123"},
                    "legs": [
                        {"distanceMeters": 6000, "duration": "600s"},
                        {"distanceMeters": 36000, "duration": "3000s"},
                    ],
                }
            ]
        }
        mock_post.return_value = mock_response

        res = compute_live_google_route(stops, server_api_key="valid-mock-key")
        assert res["dataSource"] == "LIVE GOOGLE DATA"
        assert res["is_simulated"] is False
        assert res["polyline"] == "mocked_encoded_polyline_abc123"
        assert res["total_distance_meters"] == 42000.0
        assert res["total_duration_seconds"] == 3600.0
        assert len(res["legs"]) == 2
