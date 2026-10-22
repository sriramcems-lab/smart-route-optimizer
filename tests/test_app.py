"""
Integration tests for Flask Web Application (app.py).
Tests REST endpoints, server-side validation, error responses,
and Demo Mode vs Live Mode safety.
"""

import json
import pytest
from app import create_app
from optimizer.cost_matrix import clear_matrix_cache
from optimizer.route_service import clear_route_cache


@pytest.fixture
def client():
    """Create a clean Flask test client with Demo Mode defaults."""
    clear_matrix_cache()
    clear_route_cache()
    test_app = create_app({
        "TESTING": True,
        "GOOGLE_MAPS_SERVER_API_KEY": "",
        "GOOGLE_MAPS_BROWSER_API_KEY": "dummy_browser_key",
    })
    with test_app.test_client() as test_client:
        yield test_client


class TestIndexEndpoint:
    """Tests for GET / dashboard serving."""

    def test_get_index_success(self, client):
        response = client.get("/")
        assert response.status_code == 200
        html = response.data.decode("utf-8")
        assert "Smart Route Optimizer" in html
        assert 'id="map"' in html
        assert 'id="place-search-input"' in html
        assert 'id="preset-select"' in html
        assert 'id="stops-container"' in html
        assert 'id="btn-optimize"' in html
        assert 'id="data-source-badge"' in html
        assert 'id="aco-details"' in html
        assert 'id="analytics-canvas"' in html
        assert 'class="comparison-table"' in html
        assert "window.APP_CONFIG" in html
        # Ensure server key is NEVER leaked in HTML
        assert "GOOGLE_MAPS_SERVER_API_KEY" not in html

    def test_404_handler(self, client):
        response = client.get("/api/nonexistent-endpoint")
        assert response.status_code == 404
        data = response.get_json()
        assert data["status"] == "error"
        assert data["error_type"] == "NOT_FOUND"

    def test_405_handler(self, client):
        # /api/optimize requires POST
        response = client.get("/api/optimize")
        assert response.status_code == 405
        data = response.get_json()
        assert data["status"] == "error"
        assert data["error_type"] == "METHOD_NOT_ALLOWED"


class TestOptimizeEndpointValidation:
    """Tests for server-side validation on POST /api/optimize."""

    def test_missing_json_header(self, client):
        response = client.post("/api/optimize", data="not json", content_type="text/plain")
        assert response.status_code == 400
        data = response.get_json()
        assert data["error_type"] == "INVALID_CONTENT_TYPE"

    def test_empty_json_body(self, client):
        response = client.post("/api/optimize", data="", content_type="application/json")
        assert response.status_code == 400
        data = response.get_json()
        assert data["error_type"] == "MALFORMED_JSON"

    def test_fewer_than_two_stops(self, client):
        payload = {
            "stops": [{"lat": 12.9716, "lng": 77.5946, "label": "Start"}]
        }
        response = client.post("/api/optimize", json=payload)
        assert response.status_code == 400
        data = response.get_json()
        assert data["error_type"] == "VALIDATION_ERROR"
        assert "At least 2 stops" in data["message"]

    def test_more_than_fifteen_stops(self, client):
        payload = {
            "stops": [{"lat": 12.0 + (i * 0.01), "lng": 77.0 + (i * 0.01)} for i in range(16)]
        }
        response = client.post("/api/optimize", json=payload)
        assert response.status_code == 400
        data = response.get_json()
        assert "Maximum 15 stops" in data["message"]

    def test_invalid_coordinates(self, client):
        payload = {
            "stops": [
                {"lat": 100.0, "lng": 77.0},  # Latitude out of bounds
                {"lat": 12.0, "lng": 77.0},
            ]
        }
        response = client.post("/api/optimize", json=payload)
        assert response.status_code == 400
        data = response.get_json()
        assert "Latitude at stop 0 must be between -90.0 and 90.0" in data["message"]

    def test_invalid_objective(self, client):
        payload = {
            "stops": [
                {"lat": 12.97, "lng": 77.59},
                {"lat": 13.00, "lng": 77.60},
            ],
            "objective": "fastest_or_cheapest",
        }
        response = client.post("/api/optimize", json=payload)
        assert response.status_code == 400
        data = response.get_json()
        assert "Objective must be either 'distance' or 'time'" in data["message"]

    def test_invalid_aco_hyperparameters(self, client):
        payload = {
            "stops": [
                {"lat": 12.97, "lng": 77.59},
                {"lat": 13.00, "lng": 77.60},
            ],
            "aco_params": {
                "num_ants": -10,  # Invalid
            },
        }
        response = client.post("/api/optimize", json=payload)
        assert response.status_code == 400
        data = response.get_json()
        assert "num_ants must be between 1 and 100" in data["message"]


class TestOptimizeEndpointExecution:
    """Tests for successful route optimization in Demo Mode."""

    @pytest.fixture
    def five_stops_payload(self):
        # 5 stops in Bangalore
        return {
            "stops": [
                {"label": "Start: Majestic", "lat": 12.9784, "lng": 77.5726},
                {"label": "Stop 1: Indiranagar", "lat": 12.9719, "lng": 77.6412},
                {"label": "Stop 2: Koramangala", "lat": 12.9352, "lng": 77.6245},
                {"label": "Stop 3: Whitefield", "lat": 12.9698, "lng": 77.7499},
                {"label": "Destination: Airport", "lat": 13.1986, "lng": 77.7066},
            ],
            "objective": "distance",
            "aco_params": {
                "num_ants": 15,
                "iterations": 25,
                "alpha": 1.0,
                "beta": 2.5,
                "evaporation_rate": 0.2,
                "q": 100.0,
                "random_seed": 42,
            },
        }

    def test_successful_distance_optimization(self, client, five_stops_payload):
        response = client.post("/api/optimize", json=five_stops_payload)
        assert response.status_code == 200
        data = response.get_json()

        assert data["status"] == "success"
        assert data["dataSource"] == "SIMULATED DATA"
        assert data["isSimulated"] is True
        assert data["objective"] == "distance"

        # Check baseline structure
        assert "baseline" in data
        assert data["baseline"]["tour"] == [0, 1, 2, 3, 4]
        assert data["baseline"]["total_distance_km"] > 0.0

        # Check optimized structure
        assert "optimized" in data
        assert data["optimized"]["tour"][0] == 0
        assert data["optimized"]["tour"][-1] == 4
        assert len(data["optimized"]["tour"]) == 5

        # Check metrics
        assert "metrics" in data
        assert data["metrics"]["cost_unit"] == "meters"
        assert isinstance(data["metrics"]["percentage_improvement"], float)

        # Check route geometry
        assert "route_geometry" in data
        assert isinstance(data["route_geometry"]["polyline"], str)
        assert len(data["route_geometry"]["legs"]) == 4

        # Check convergence history
        assert "convergence" in data
        assert len(data["convergence"]["best_costs"]) == 25

        # Check disclaimer exists
        assert "disclaimer" in data

    def test_successful_time_objective_optimization(self, client, five_stops_payload):
        five_stops_payload["objective"] = "time"
        response = client.post("/api/optimize", json=five_stops_payload)
        assert response.status_code == 200
        data = response.get_json()

        assert data["objective"] == "time"
        assert data["metrics"]["cost_unit"] == "seconds"
        assert data["optimized"]["total_duration_minutes"] > 0.0


class TestRouteEndpoint:
    """Tests for POST /api/route geometry endpoint."""

    def test_successful_route_call(self, client):
        payload = {
            "stops": [
                {"lat": 12.9784, "lng": 77.5726},
                {"lat": 12.9352, "lng": 77.6245},
                {"lat": 13.1986, "lng": 77.7066},
            ]
        }
        response = client.post("/api/route", json=payload)
        assert response.status_code == 200
        data = response.get_json()

        assert data["status"] == "success"
        assert data["dataSource"] == "SIMULATED DATA"
        assert isinstance(data["polyline"], str)
        assert len(data["legs"]) == 2
        assert data["total_distance_km"] > 0.0

    def test_route_fewer_than_two_stops(self, client):
        payload = {"stops": [{"lat": 12.9784, "lng": 77.5726}]}
        response = client.post("/api/route", json=payload)
        assert response.status_code == 400
        data = response.get_json()
        assert data["error_type"] == "VALIDATION_ERROR"
