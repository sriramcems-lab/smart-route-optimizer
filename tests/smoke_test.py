"""
Smoke test verifying Flask routes and end-to-end optimization pipeline.
"""

import sys
from pathlib import Path
import json

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import create_app

def test_pipeline():
    app = create_app({"TESTING": True})
    client = app.test_client()

    print("=" * 60)
    print("STAGE 3: FLASK BACKEND & ROUTING PIPELINE SMOKE TEST")
    print("=" * 60)

    # 1. GET /
    res_index = client.get("/")
    print(f"1. GET / -> Status {res_index.status_code} (Length: {len(res_index.data)} bytes)")
    assert res_index.status_code == 200

    # 2. POST /api/optimize (Demo Mode)
    payload = {
        "stops": [
            {"label": "Start: Tech Park", "lat": 12.9716, "lng": 77.5946},
            {"label": "Stop A: Mall", "lat": 12.9352, "lng": 77.6245},
            {"label": "Stop B: Station", "lat": 12.9784, "lng": 77.5726},
            {"label": "Stop C: University", "lat": 12.9344, "lng": 77.6101},
            {"label": "Destination: Airport", "lat": 13.1986, "lng": 77.7066},
        ],
        "objective": "distance",
        "aco_params": {
            "num_ants": 20,
            "iterations": 30,
            "alpha": 1.0,
            "beta": 2.5,
            "evaporation_rate": 0.2,
            "q": 100.0,
            "random_seed": 42
        }
    }

    res_opt = client.post("/api/optimize", json=payload)
    print(f"2. POST /api/optimize -> Status {res_opt.status_code}")
    assert res_opt.status_code == 200
    data = res_opt.get_json()

    print(f"   Data Source : {data['dataSource']}")
    print(f"   Is Simulated: {data['isSimulated']}")
    print(f"   Baseline Tour      : {data['baseline']['tour']} ({data['baseline']['total_distance_km']} km)")
    print(f"   ACO Optimized Tour : {data['optimized']['tour']} ({data['optimized']['total_distance_km']} km)")
    print(f"   Improvement        : {data['metrics']['percentage_improvement']}%")
    print(f"   Distance Saved     : {data['metrics']['distance_saved_km']} km")
    print(f"   Encoded Polyline   : {data['route_geometry']['polyline'][:30]}...")

    # 3. POST /api/route
    res_route = client.post("/api/route", json={"stops": payload["stops"][:3]})
    print(f"3. POST /api/route -> Status {res_route.status_code}")
    assert res_route.status_code == 200
    route_data = res_route.get_json()
    print(f"   Route legs: {len(route_data['legs'])} legs, total distance: {route_data['total_distance_km']} km")

    # 4. Error validation test (fewer than 2 stops)
    res_err = client.post("/api/optimize", json={"stops": [{"lat": 12.97, "lng": 77.59}]})
    print(f"4. POST /api/optimize (validation check) -> Status {res_err.status_code} ({res_err.get_json()['error_type']})")
    assert res_err.status_code == 400

    print("=" * 60)
    print("ALL SMOKE TESTS PASSED CLEANLY!")
    print("=" * 60)

if __name__ == "__main__":
    test_pipeline()
