"""
Smart Route Optimizer - Flask Web Application
=============================================
A modern Flask application that optimizes multi-stop travel routes using
Ant Colony Optimization (ACO) and Google Routes API (with built-in simulated Demo Mode).

Architecture:
-------------
- Frontend: HTML5/CSS3/Vanilla JS + Google Maps JavaScript API (or fallback map).
- Backend: Flask REST API + Pure Python ACO Engine + Google Routes API (v2).
- Security: Server keys strictly isolated on the backend; never exposed to templates or JSON.
"""

import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from flask import Flask, jsonify, render_template, request
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Ensure local packages are importable
sys.path.insert(0, str(Path(__file__).resolve().parent))

from optimizer.aco import (
    solve_aco,
    calculate_path_cost,
    compute_percentage_improvement,
)
from optimizer.cost_matrix import (
    get_cost_matrices,
    is_live_key_available,
    CostMatrixError,
)
from optimizer.route_service import (
    get_route_geometry,
    RouteServiceError,
)


def validate_stop_item(stop: Any, index: int) -> Dict[str, Any]:
    """
    Validate an individual stop object.

    Must contain numeric 'lat' in [-90, 90] and 'lng' in [-180, 180].
    Optional 'label' string up to 100 characters.
    """
    if not isinstance(stop, dict):
        raise ValueError(f"Stop at index {index} must be a JSON object.")

    if "lat" not in stop or "lng" not in stop:
        raise ValueError(f"Stop at index {index} must contain 'lat' and 'lng'.")

    try:
        lat = float(stop["lat"])
        lng = float(stop["lng"])
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Coordinates at stop {index} must be valid numbers: {exc}") from exc

    if not (-90.0 <= lat <= 90.0):
        raise ValueError(f"Latitude at stop {index} must be between -90.0 and 90.0, but got {lat}.")

    if not (-180.0 <= lng <= 180.0):
        raise ValueError(f"Longitude at stop {index} must be between -180.0 and 180.0, but got {lng}.")

    label = str(stop.get("label", f"Stop {index}")).strip()[:100]

    return {"lat": lat, "lng": lng, "label": label, "index": index}


def validate_optimize_request(data: Any) -> Tuple[List[Dict[str, Any]], str, Dict[str, Any], bool]:
    """
    Validate the complete JSON payload for POST /api/optimize.

    Returns:
    --------
    tuple (stops, objective, aco_params, force_demo)
    """
    if not isinstance(data, dict):
        raise ValueError("Request body must be a valid JSON object.")

    # 1. Validate stops array
    raw_stops = data.get("stops")
    if not isinstance(raw_stops, list):
        raise ValueError("Field 'stops' must be a list of location objects.")

    if len(raw_stops) < 2:
        raise ValueError("At least 2 stops (start and destination) are required.")

    if len(raw_stops) > 15:
        raise ValueError("Maximum 15 stops are supported per optimization request to preserve API quotas.")

    validated_stops = [validate_stop_item(stop, idx) for idx, stop in enumerate(raw_stops)]

    # 2. Validate objective
    raw_objective = str(data.get("objective", "distance")).strip().lower()
    if raw_objective in ("distance", "dist"):
        objective = "distance"
    elif raw_objective in ("time", "duration"):
        objective = "time"
    else:
        raise ValueError("Objective must be either 'distance' or 'time'.")

    # 3. Validate ACO hyperparameters
    raw_params = data.get("aco_params", {})
    if not isinstance(raw_params, dict):
        raise ValueError("Field 'aco_params' must be a JSON dictionary.")

    num_ants = raw_params.get("num_ants", 20)
    iterations = raw_params.get("iterations", 50)
    alpha = raw_params.get("alpha", 1.0)
    beta = raw_params.get("beta", 2.5)
    evaporation_rate = raw_params.get("evaporation_rate", 0.2)
    q = raw_params.get("q", 100.0)
    random_seed = raw_params.get("random_seed")

    try:
        num_ants = int(num_ants)
        iterations = int(iterations)
        alpha = float(alpha)
        beta = float(beta)
        evaporation_rate = float(evaporation_rate)
        q = float(q)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"Invalid ACO parameter type: {exc}") from exc

    if not (1 <= num_ants <= 100):
        raise ValueError(f"num_ants must be between 1 and 100, but got {num_ants}.")
    if not (1 <= iterations <= 200):
        raise ValueError(f"iterations must be between 1 and 200, but got {iterations}.")
    if not (0.0 <= alpha <= 5.0):
        raise ValueError(f"alpha must be between 0.0 and 5.0, but got {alpha}.")
    if not (0.0 <= beta <= 10.0):
        raise ValueError(f"beta must be between 0.0 and 10.0, but got {beta}.")
    if not (0.01 <= evaporation_rate <= 0.99):
        raise ValueError(f"evaporation_rate must be between 0.01 and 0.99, but got {evaporation_rate}.")
    if not (1.0 <= q <= 1000.0):
        raise ValueError(f"q must be between 1.0 and 1000.0, but got {q}.")

    if random_seed is not None:
        try:
            random_seed = int(random_seed)
        except (ValueError, TypeError):
            raise ValueError("random_seed must be an integer or null.")

    aco_params = {
        "num_ants": num_ants,
        "iterations": iterations,
        "alpha": alpha,
        "beta": beta,
        "evaporation_rate": evaporation_rate,
        "q": q,
        "random_seed": random_seed,
    }

    force_demo = bool(data.get("force_demo", False))

    return validated_stops, objective, aco_params, force_demo


BASE_DIR = Path(__file__).resolve().parent


def create_app(test_config: Optional[Dict[str, Any]] = None) -> Flask:
    """
    Application factory for the Flask app.
    Supports dependency injection for test configurations.
    """
    app = Flask(
        __name__,
        template_folder=str(BASE_DIR / "templates"),
        static_folder=str(BASE_DIR / "static"),
    )

    # Configure secret key for session security
    app.config["SECRET_KEY"] = os.getenv("FLASK_SECRET_KEY", "default-dev-secret-key-change-in-prod")
    app.config["GOOGLE_MAPS_BROWSER_API_KEY"] = os.getenv("GOOGLE_MAPS_BROWSER_API_KEY", "")
    app.config["GOOGLE_MAPS_SERVER_API_KEY"] = os.getenv("GOOGLE_MAPS_SERVER_API_KEY", "")

    if test_config:
        app.config.update(test_config)

    @app.route("/", methods=["GET"])
    def index():
        """Render the main single-page application dashboard."""
        browser_key = app.config.get("GOOGLE_MAPS_BROWSER_API_KEY", "")
        server_key = app.config.get("GOOGLE_MAPS_SERVER_API_KEY", "")
        # App is in Demo Mode if server key is absent or placeholder
        is_demo = not is_live_key_available(server_key)

        return render_template(
            "index.html",
            browser_api_key=browser_key,
            is_demo_mode=is_demo,
        )

    @app.route("/api/optimize", methods=["POST"])
    def optimize_route():
        """
        API endpoint to solve the Open TSP using Ant Colony Optimization.

        Input JSON:
        -----------
        {
          "stops": [{"lat": 12.97, "lng": 77.59, "label": "Start"}, ...],
          "objective": "distance" | "time",
          "aco_params": { ... }
        }
        """
        if not request.is_json:
            return jsonify({
                "status": "error",
                "error_type": "INVALID_CONTENT_TYPE",
                "message": "Request Content-Type must be application/json.",
            }), 400

        try:
            data = request.get_json(silent=True)
            if data is None:
                return jsonify({
                    "status": "error",
                    "error_type": "MALFORMED_JSON",
                    "message": "Malformed or empty JSON payload.",
                }), 400

            stops, objective, aco_params, force_demo = validate_optimize_request(data)
        except ValueError as err:
            return jsonify({
                "status": "error",
                "error_type": "VALIDATION_ERROR",
                "message": str(err),
            }), 400

        server_key = app.config.get("GOOGLE_MAPS_SERVER_API_KEY", "")

        # 1. Fetch pairwise cost matrices
        try:
            matrix_result = get_cost_matrices(
                stops=stops,
                server_api_key=server_key,
                force_demo=force_demo,
            )
        except CostMatrixError as err:
            return jsonify({
                "status": "error",
                "error_type": "COST_MATRIX_ERROR",
                "message": err.message,
                "details": err.details,
            }), err.status_code
        except Exception as exc:
            return jsonify({
                "status": "error",
                "error_type": "INTERNAL_MATRIX_ERROR",
                "message": f"Unexpected error computing cost matrix: {exc}",
            }), 500

        dist_matrix = matrix_result["distance_matrix"]
        time_matrix = matrix_result["duration_matrix"]
        data_source = matrix_result["dataSource"]
        is_simulated = matrix_result["is_simulated"]

        # Select target matrix according to optimization objective
        if objective == "time":
            target_matrix = time_matrix
            cost_unit = "seconds"
        else:
            target_matrix = dist_matrix
            cost_unit = "meters"

        # 2. Run Ant Colony Optimization
        try:
            aco_result = solve_aco(target_matrix, **aco_params)
        except Exception as exc:
            return jsonify({
                "status": "error",
                "error_type": "OPTIMIZER_ERROR",
                "message": f"ACO algorithm failed: {exc}",
            }), 500

        best_tour = aco_result["best_tour"]
        baseline_tour = aco_result["baseline_tour"]

        # 3. Calculate both distance & duration for Baseline and Optimized tours
        baseline_dist_m = calculate_path_cost(baseline_tour, dist_matrix)
        baseline_time_s = calculate_path_cost(baseline_tour, time_matrix)

        optimized_dist_m = calculate_path_cost(best_tour, dist_matrix)
        optimized_time_s = calculate_path_cost(best_tour, time_matrix)

        # Baseline and optimized primary costs
        if objective == "time":
            baseline_primary = baseline_time_s
            optimized_primary = optimized_time_s
        else:
            baseline_primary = baseline_dist_m
            optimized_primary = optimized_dist_m

        improvement_pct = compute_percentage_improvement(baseline_primary, optimized_primary)
        abs_savings = max(0.0, baseline_primary - optimized_primary)

        # 4. Construct ordered stop objects
        ordered_stops = [
            {
                "tour_order": order_idx,
                "original_index": stop_idx,
                "label": stops[stop_idx]["label"],
                "lat": stops[stop_idx]["lat"],
                "lng": stops[stop_idx]["lng"],
            }
            for order_idx, stop_idx in enumerate(best_tour)
        ]

        baseline_ordered_stops = [
            {
                "tour_order": order_idx,
                "original_index": stop_idx,
                "label": stops[stop_idx]["label"],
                "lat": stops[stop_idx]["lat"],
                "lng": stops[stop_idx]["lng"],
            }
            for order_idx, stop_idx in enumerate(baseline_tour)
        ]

        # 5. Fetch polyline geometry for both optimized and baseline orders
        try:
            route_info = get_route_geometry(
                ordered_stops=ordered_stops,
                server_api_key=server_key,
                force_demo=force_demo or is_simulated,
            )
            polyline = route_info.get("polyline", "")
            legs = route_info.get("legs", [])
        except Exception:
            polyline = ""
            legs = []

        try:
            base_route_info = get_route_geometry(
                ordered_stops=baseline_ordered_stops,
                server_api_key=server_key,
                force_demo=force_demo or is_simulated,
            )
            base_polyline = base_route_info.get("polyline", "")
        except Exception:
            base_polyline = ""

        response_payload = {
            "status": "success",
            "dataSource": data_source,
            "isSimulated": is_simulated,
            "objective": objective,
            "baseline": {
                "tour": baseline_tour,
                "ordered_stops": baseline_ordered_stops,
                "total_distance_meters": round(baseline_dist_m, 1),
                "total_distance_km": round(baseline_dist_m / 1000.0, 2),
                "total_duration_seconds": round(baseline_time_s, 1),
                "total_duration_minutes": round(baseline_time_s / 60.0, 1),
                "primary_cost": round(baseline_primary, 1),
            },
            "optimized": {
                "tour": best_tour,
                "ordered_stops": ordered_stops,
                "total_distance_meters": round(optimized_dist_m, 1),
                "total_distance_km": round(optimized_dist_m / 1000.0, 2),
                "total_duration_seconds": round(optimized_time_s, 1),
                "total_duration_minutes": round(optimized_time_s / 60.0, 1),
                "primary_cost": round(optimized_primary, 1),
            },
            "metrics": {
                "cost_unit": cost_unit,
                "absolute_savings": round(abs_savings, 1),
                "percentage_improvement": improvement_pct,
                "distance_saved_km": round(max(0.0, baseline_dist_m - optimized_dist_m) / 1000.0, 2),
                "duration_saved_minutes": round(max(0.0, baseline_time_s - optimized_time_s) / 60.0, 1),
            },
            "route_geometry": {
                "polyline": polyline,
                "legs": legs,
                "baseline_polyline": base_polyline,
            },
            "convergence": {
                "iterations": list(range(1, len(aco_result["iteration_history"]) + 1)),
                "best_costs": [round(c, 1) for c in aco_result["iteration_history"]],
            },
            "disclaimer": (
                "ACO is a metaheuristic algorithm that evaluates permutations of the discrete pairwise "
                "cost matrix of selected stops. It finds high-quality near-optimal routes but does not "
                "guarantee the mathematical global optimum."
            ),
        }

        return jsonify(response_payload), 200

    @app.route("/api/route", methods=["POST"])
    def get_route():
        """
        API endpoint to retrieve polyline geometry and legs for an ordered sequence of stops.
        """
        if not request.is_json:
            return jsonify({
                "status": "error",
                "error_type": "INVALID_CONTENT_TYPE",
                "message": "Request Content-Type must be application/json.",
            }), 400

        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify({
                "status": "error",
                "error_type": "MALFORMED_JSON",
                "message": "Request body must be a valid JSON dictionary.",
            }), 400

        raw_stops = data.get("stops")
        if not isinstance(raw_stops, list) or len(raw_stops) < 2:
            return jsonify({
                "status": "error",
                "error_type": "VALIDATION_ERROR",
                "message": "At least 2 stops are required to compute route geometry.",
            }), 400

        try:
            validated_stops = [validate_stop_item(stop, idx) for idx, stop in enumerate(raw_stops)]
        except ValueError as err:
            return jsonify({
                "status": "error",
                "error_type": "VALIDATION_ERROR",
                "message": str(err),
            }), 400

        server_key = app.config.get("GOOGLE_MAPS_SERVER_API_KEY", "")
        force_demo = bool(data.get("force_demo", False))

        try:
            result = get_route_geometry(
                ordered_stops=validated_stops,
                server_api_key=server_key,
                force_demo=force_demo,
            )
        except RouteServiceError as err:
            return jsonify({
                "status": "error",
                "error_type": "ROUTE_SERVICE_ERROR",
                "message": err.message,
                "details": err.details,
            }), err.status_code
        except Exception as exc:
            return jsonify({
                "status": "error",
                "error_type": "ROUTE_INTERNAL_ERROR",
                "message": f"Unexpected error computing route: {exc}",
            }), 500

        return jsonify({
            "status": "success",
            "dataSource": result["dataSource"],
            "isSimulated": result["is_simulated"],
            "polyline": result["polyline"],
            "legs": result["legs"],
            "total_distance_meters": result["total_distance_meters"],
            "total_duration_seconds": result["total_duration_seconds"],
            "total_distance_km": result["total_distance_km"],
            "total_duration_minutes": result["total_duration_minutes"],
        }), 200

    @app.errorhandler(404)
    def not_found_handler(error):
        return jsonify({
            "status": "error",
            "error_type": "NOT_FOUND",
            "message": "The requested resource was not found.",
        }), 404

    @app.errorhandler(405)
    def method_not_allowed_handler(error):
        return jsonify({
            "status": "error",
            "error_type": "METHOD_NOT_ALLOWED",
            "message": "The requested HTTP method is not allowed on this endpoint.",
        }), 405

    @app.errorhandler(500)
    def internal_error_handler(error):
        return jsonify({
            "status": "error",
            "error_type": "INTERNAL_SERVER_ERROR",
            "message": "An internal server error occurred.",
        }), 500

    return app


# Default application instance for WSGI / Flask CLI runners
app = create_app()

if __name__ == "__main__":
    port = int(os.getenv("FLASK_PORT", 5000))
    debug_mode = os.getenv("FLASK_DEBUG", "0") in ("1", "true", "True")
    print(f"Starting Smart Route Optimizer on http://localhost:{port}")
    app.run(host="0.0.0.0", port=port, debug=debug_mode)
