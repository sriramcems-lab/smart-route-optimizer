"""
Cost Matrix Service for Smart Shortest Path Finder.

Responsible for computing the pairwise cost matrices (distance in meters and
duration in seconds) between all user stops.

Supported Modes:
----------------
1. DEMO MODE:
   Calculates simulated real-world road costs using the Haversine great-circle formula,
   multiplied by an urban road circuity/detour factor (1.35) and a realistic city driving
   speed (35 km/h = ~9.72 m/s). Provides physically plausible, non-zero costs without
   requiring any API keys or billing.
   Tagged explicitly as "SIMULATED DATA".

2. LIVE MODE:
   Invokes Google Routes API (Compute Route Matrix v2):
   POST https://routes.googleapis.com/distanceMatrix/v2:computeRouteMatrix
   With required header:
   X-Goog-FieldMask: originIndex,destinationIndex,status,distanceMeters,duration,condition
   Tagged explicitly as "LIVE GOOGLE DATA".

Includes in-memory LRU caching to eliminate duplicate billable Google API calls.
"""

import math
import os
from typing import Any, Dict, List, Optional, Tuple
import requests
import numpy as np


# Earth's mean radius in meters
EARTH_RADIUS_METERS = 6371000.0

# Road circuity factor for urban environments (roads are rarely straight lines)
URBAN_CIRCUITY_FACTOR = 1.35

# Assumed average urban driving speed: 35 km/h in meters per second
URBAN_DRIVING_SPEED_MPS = 35.0 * (1000.0 / 3600.0)  # ~9.722 m/s

# In-memory cache: maps coordinate tuple hash -> cost matrix result
_MATRIX_CACHE: Dict[Tuple[Tuple[float, float], ...], Dict[str, Any]] = {}


class CostMatrixError(Exception):
    """Custom exception raised when cost matrix retrieval or computation fails."""

    def __init__(self, message: str, status_code: int = 502, details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.details = details or {}


def haversine_distance_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate the great-circle distance between two GPS points on Earth in meters.

    Parameters:
    -----------
    lat1, lon1 : float
        Latitude and longitude of point 1 in degrees.
    lat2, lon2 : float
        Latitude and longitude of point 2 in degrees.

    Returns:
    --------
    float:
        Great-circle distance in meters.
    """
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * (math.sin(delta_lambda / 2.0) ** 2)
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(max(0.0, 1.0 - a)))
    return EARTH_RADIUS_METERS * c


def compute_simulated_cost_matrix(
    stops: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Compute simulated pairwise distance and duration matrices using physical models.

    Parameters:
    -----------
    stops : list of dict
        List of stop dicts, each with 'lat' and 'lng'.

    Returns:
    --------
    dict:
        {
            'distance_matrix': np.ndarray (shape N x N, in meters),
            'duration_matrix': np.ndarray (shape N x N, in seconds),
            'dataSource': 'SIMULATED DATA',
            'is_simulated': True
        }
    """
    n = len(stops)
    dist_matrix = np.zeros((n, n), dtype=np.float64)
    time_matrix = np.zeros((n, n), dtype=np.float64)

    for i in range(n):
        lat_i = float(stops[i]["lat"])
        lng_i = float(stops[i]["lng"])
        for j in range(n):
            if i == j:
                dist_matrix[i, j] = 0.0
                time_matrix[i, j] = 0.0
            else:
                lat_j = float(stops[j]["lat"])
                lng_j = float(stops[j]["lng"])
                crow_dist = haversine_distance_meters(lat_i, lng_i, lat_j, lng_j)
                # Apply urban road circuity factor
                road_dist = max(1.0, crow_dist * URBAN_CIRCUITY_FACTOR)
                # Compute duration in seconds based on urban driving speed
                duration_sec = road_dist / URBAN_DRIVING_SPEED_MPS

                dist_matrix[i, j] = round(road_dist, 1)
                time_matrix[i, j] = round(duration_sec, 1)

    return {
        "distance_matrix": dist_matrix,
        "duration_matrix": time_matrix,
        "dataSource": "SIMULATED DATA",
        "is_simulated": True,
    }


def parse_duration_string(duration_str: str) -> float:
    """
    Parse a Google API duration string (e.g. '720s' or '120.5s') into seconds.

    Parameters:
    -----------
    duration_str : str
        String returned by Google Routes API.

    Returns:
    --------
    float:
        Duration in seconds.
    """
    if not duration_str:
        return 0.0
    cleaned = str(duration_str).strip().rstrip("s")
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def compute_live_google_route_matrix(
    stops: List[Dict[str, Any]], server_api_key: str, timeout: int = 15
) -> Dict[str, Any]:
    """
    Call Google Routes API v2 (computeRouteMatrix) to obtain live real-world road costs.

    Endpoint:
    POST https://routes.googleapis.com/distanceMatrix/v2:computeRouteMatrix

    Required Headers:
    - X-Goog-Api-Key: <server_api_key>
    - X-Goog-FieldMask: originIndex,destinationIndex,status,distanceMeters,duration,condition

    Parameters:
    -----------
    stops : list of dict
        List of stops containing 'lat' and 'lng'.
    server_api_key : str
        Valid Google Maps Server API Key.
    timeout : int
        HTTP request timeout in seconds.

    Returns:
    --------
    dict:
        {
            'distance_matrix': np.ndarray (shape N x N, in meters),
            'duration_matrix': np.ndarray (shape N x N, in seconds),
            'dataSource': 'LIVE GOOGLE DATA',
            'is_simulated': False
        }
    """
    n = len(stops)
    if n > 25:
        raise CostMatrixError(
            f"Google computeRouteMatrix supports up to 25 origins/destinations, but received {n}.",
            status_code=400,
        )

    url = "https://routes.googleapis.com/distanceMatrix/v2:computeRouteMatrix"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": server_api_key,
        "X-Goog-FieldMask": "originIndex,destinationIndex,status,distanceMeters,duration,condition",
    }

    waypoints = [
        {
            "waypoint": {
                "location": {
                    "latLng": {
                        "latitude": float(s["lat"]),
                        "longitude": float(s["lng"]),
                    }
                }
            }
        }
        for s in stops
    ]

    payload = {
        "origins": waypoints,
        "destinations": waypoints,
        "travelMode": "DRIVE",
        "routingPreference": "TRAFFIC_AWARE",
    }

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=timeout)
    except requests.exceptions.Timeout as exc:
        raise CostMatrixError("Google Routes API timed out.", status_code=504) from exc
    except requests.exceptions.RequestException as exc:
        raise CostMatrixError(f"Network error contacting Google Routes API: {exc}", status_code=502) from exc

    if response.status_code != 200:
        error_msg = f"Google Routes API returned HTTP {response.status_code}"
        try:
            err_json = response.json()
            if "error" in err_json and "message" in err_json["error"]:
                error_msg += f": {err_json['error']['message']}"
        except Exception:
            error_msg += f": {response.text[:200]}"
        raise CostMatrixError(error_msg, status_code=response.status_code)

    try:
        matrix_elements = response.json()
    except Exception as exc:
        raise CostMatrixError("Failed to parse JSON response from Google Routes API.", status_code=502) from exc

    if not isinstance(matrix_elements, list):
        raise CostMatrixError("Unexpected response structure from Google Routes API.", status_code=502)

    dist_matrix = np.zeros((n, n), dtype=np.float64)
    time_matrix = np.zeros((n, n), dtype=np.float64)

    for item in matrix_elements:
        # Check element status / condition
        condition = item.get("condition", "ROUTE_EXISTS")
        if condition == "ROUTE_NOT_FOUND":
            origin = item.get("originIndex", "?")
            dest = item.get("destinationIndex", "?")
            raise CostMatrixError(
                f"No driving route could be found between stop {origin} and stop {dest}.",
                status_code=400,
            )

        u = item.get("originIndex")
        v = item.get("destinationIndex")
        if u is not None and v is not None and 0 <= u < n and 0 <= v < n:
            dist = float(item.get("distanceMeters", 0.0))
            dur = parse_duration_string(item.get("duration", "0s"))
            dist_matrix[u, v] = dist
            time_matrix[u, v] = dur

    # Set self-loops to 0.0 explicitly
    np.fill_diagonal(dist_matrix, 0.0)
    np.fill_diagonal(time_matrix, 0.0)

    return {
        "distance_matrix": dist_matrix,
        "duration_matrix": time_matrix,
        "dataSource": "LIVE GOOGLE DATA",
        "is_simulated": False,
    }


def is_live_key_available(api_key: Optional[str]) -> bool:
    """
    Check if a Google Server API key is present and is not a default placeholder.
    """
    if not api_key:
        return False
    key_str = str(api_key).strip()
    if not key_str or "your_" in key_str.lower() or "placeholder" in key_str.lower():
        return False
    return True


def get_cost_matrices(
    stops: List[Dict[str, Any]],
    server_api_key: Optional[str] = None,
    force_demo: bool = False,
) -> Dict[str, Any]:
    """
    Retrieve pairwise distance and duration matrices with caching and automatic Demo fallback.

    Parameters:
    -----------
    stops : list of dict
        List of stops containing 'lat' and 'lng'.
    server_api_key : str or None
        Google Maps Server API Key from environment.
    force_demo : bool
        If True, forces simulated Demo mode even if a server key exists.

    Returns:
    --------
    dict:
        {
            'distance_matrix': np.ndarray,
            'duration_matrix': np.ndarray,
            'dataSource': 'LIVE GOOGLE DATA' or 'SIMULATED DATA',
            'is_simulated': bool
        }
    """
    if not stops or len(stops) < 2:
        raise ValueError("At least 2 stops are required to compute a cost matrix.")

    # Create coordinate cache key (rounded to 5 decimal places ~= 1m precision)
    coord_key = tuple(
        (round(float(s["lat"]), 5), round(float(s["lng"]), 5))
        for s in stops
    )

    # Determine whether to use Live mode or Demo mode
    use_live = (not force_demo) and is_live_key_available(server_api_key)
    cache_lookup_key = (("LIVE",) if use_live else ("DEMO",)) + coord_key

    if cache_lookup_key in _MATRIX_CACHE:
        cached = _MATRIX_CACHE[cache_lookup_key]
        return {
            "distance_matrix": cached["distance_matrix"].copy(),
            "duration_matrix": cached["duration_matrix"].copy(),
            "dataSource": cached["dataSource"],
            "is_simulated": cached["is_simulated"],
        }

    if use_live and server_api_key:
        result = compute_live_google_route_matrix(stops, server_api_key=server_api_key)
    else:
        result = compute_simulated_cost_matrix(stops)

    # Store in memory cache
    _MATRIX_CACHE[cache_lookup_key] = {
        "distance_matrix": result["distance_matrix"].copy(),
        "duration_matrix": result["duration_matrix"].copy(),
        "dataSource": result["dataSource"],
        "is_simulated": result["is_simulated"],
    }

    return result


def clear_matrix_cache() -> None:
    """Clear in-memory matrix cache (useful for isolated unit testing)."""
    _MATRIX_CACHE.clear()
