"""
Route Geometry Service for Smart Shortest Path Finder.

Responsible for retrieving or computing the path geometry (polyline) and leg details
for a sequence of stops ordered by the Ant Colony Optimizer.

Supported Modes:
----------------
1. DEMO MODE:
   Encodes the ordered GPS stops into a standard 5-decimal Google-compatible encoded
   polyline string and calculates simulated leg distances and durations. Works offline
   without requiring Google API credentials.
   Tagged explicitly as "SIMULATED DATA".

2. LIVE MODE:
   Invokes Google Routes API (Compute Routes v2):
   POST https://routes.googleapis.com/directions/v2:computeRoutes
   With required header:
   X-Goog-FieldMask: routes.duration,routes.distanceMeters,routes.polyline.encodedPolyline,routes.legs
   STRICT REQUIREMENT: Waypoint reordering is NEVER enabled on Google Routes API.
   The intermediate stops are submitted in the EXACT sequence determined by our ACO solver.
   Tagged explicitly as "LIVE GOOGLE DATA".
"""

from typing import Any, Dict, List, Optional, Tuple
import requests

from optimizer.cost_matrix import (
    haversine_distance_meters,
    parse_duration_string,
    is_live_key_available,
    URBAN_CIRCUITY_FACTOR,
    URBAN_DRIVING_SPEED_MPS,
)


class RouteServiceError(Exception):
    """Custom exception raised when route geometry retrieval fails."""

    def __init__(self, message: str, status_code: int = 502, details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.details = details or {}


# In-memory cache for route geometry responses
_ROUTE_CACHE: Dict[Tuple[Tuple[float, float], ...], Dict[str, Any]] = {}


def encode_polyline(points: List[Tuple[float, float]]) -> str:
    """
    Encode a list of (latitude, longitude) tuples into a Google standard encoded polyline string.

    Specification:
    https://developers.google.com/maps/documentation/utilities/polylinealgorithm

    Parameters:
    -----------
    points : list of tuple (lat, lng)
        Coordinates in degrees.

    Returns:
    --------
    str:
        Encoded polyline string.
    """
    if not points:
        return ""

    def encode_value(val: int) -> str:
        # Shift left by 1 bit, invert if negative
        val = ~(val << 1) if val < 0 else (val << 1)
        chunks = []
        while val >= 0x20:
            chunks.append(chr((0x20 | (val & 0x1F)) + 63))
            val >>= 5
        chunks.append(chr(val + 63))
        return "".join(chunks)

    output = []
    prev_lat = 0
    prev_lng = 0

    for lat, lng in points:
        lat_int = round(lat * 1e5)
        lng_int = round(lng * 1e5)

        delta_lat = lat_int - prev_lat
        delta_lng = lng_int - prev_lng

        prev_lat = lat_int
        prev_lng = lng_int

        output.append(encode_value(delta_lat))
        output.append(encode_value(delta_lng))

    return "".join(output)


def compute_simulated_route_geometry(stops: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Generate simulated route geometry (polyline and legs) for ordered stops.

    Parameters:
    -----------
    stops : list of dict
        Ordered list of stops, each containing 'lat' and 'lng'.

    Returns:
    --------
    dict:
        {
            'polyline': str,
            'legs': list of dict,
            'total_distance_meters': float,
            'total_duration_seconds': float,
            'dataSource': 'SIMULATED DATA',
            'is_simulated': True
        }
    """
    coords = [(float(s["lat"]), float(s["lng"])) for s in stops]
    encoded = encode_polyline(coords)

    legs = []
    total_dist = 0.0
    total_dur = 0.0

    for idx in range(len(stops) - 1):
        lat1, lon1 = coords[idx]
        lat2, lon2 = coords[idx + 1]
        crow_dist = haversine_distance_meters(lat1, lon1, lat2, lon2)
        road_dist = max(1.0, crow_dist * URBAN_CIRCUITY_FACTOR)
        leg_dur = road_dist / URBAN_DRIVING_SPEED_MPS

        total_dist += road_dist
        total_dur += leg_dur

        legs.append({
            "start_index": idx,
            "end_index": idx + 1,
            "distance_meters": round(road_dist, 1),
            "duration_seconds": round(leg_dur, 1),
            "distance_km": round(road_dist / 1000.0, 2),
            "duration_minutes": round(leg_dur / 60.0, 1),
        })

    return {
        "polyline": encoded,
        "legs": legs,
        "total_distance_meters": round(total_dist, 1),
        "total_duration_seconds": round(total_dur, 1),
        "total_distance_km": round(total_dist / 1000.0, 2),
        "total_duration_minutes": round(total_dur / 60.0, 1),
        "dataSource": "SIMULATED DATA",
        "is_simulated": True,
    }


def compute_live_google_route(
    stops: List[Dict[str, Any]], server_api_key: str, timeout: int = 15
) -> Dict[str, Any]:
    """
    Call Google Routes API v2 (computeRoutes) for the exact ordered sequence of stops.

    Endpoint:
    POST https://routes.googleapis.com/directions/v2:computeRoutes

    Required Headers:
    - X-Goog-Api-Key: <server_api_key>
    - X-Goog-FieldMask: routes.duration,routes.distanceMeters,routes.polyline.encodedPolyline,routes.legs

    Notice:
    Waypoints are passed in the ACO order. We do NOT enable Google's waypoint optimization.
    """
    if len(stops) < 2:
        raise RouteServiceError("At least 2 stops are required for route geometry.", status_code=400)

    url = "https://routes.googleapis.com/directions/v2:computeRoutes"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": server_api_key,
        "X-Goog-FieldMask": "routes.duration,routes.distanceMeters,routes.polyline.encodedPolyline,routes.legs",
    }

    origin = {
        "location": {
            "latLng": {
                "latitude": float(stops[0]["lat"]),
                "longitude": float(stops[0]["lng"]),
            }
        }
    }

    destination = {
        "location": {
            "latLng": {
                "latitude": float(stops[-1]["lat"]),
                "longitude": float(stops[-1]["lng"]),
            }
        }
    }

    intermediates = [
        {
            "location": {
                "latLng": {
                    "latitude": float(s["lat"]),
                    "longitude": float(s["lng"]),
                }
            }
        }
        for s in stops[1:-1]
    ]

    payload: Dict[str, Any] = {
        "origin": origin,
        "destination": destination,
        "travelMode": "DRIVE",
        "routingPreference": "TRAFFIC_AWARE",
        "polylineQuality": "OVERVIEW",
    }
    if intermediates:
        payload["intermediates"] = intermediates

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=timeout)
    except requests.exceptions.Timeout as exc:
        raise RouteServiceError("Google Routes API timed out.", status_code=504) from exc
    except requests.exceptions.RequestException as exc:
        raise RouteServiceError(f"Network error contacting Google Routes API: {exc}", status_code=502) from exc

    if response.status_code != 200:
        error_msg = f"Google Routes API returned HTTP {response.status_code}"
        try:
            err_json = response.json()
            if "error" in err_json and "message" in err_json["error"]:
                error_msg += f": {err_json['error']['message']}"
        except Exception:
            error_msg += f": {response.text[:200]}"
        raise RouteServiceError(error_msg, status_code=response.status_code)

    data = response.json()
    routes = data.get("routes", [])
    if not routes:
        raise RouteServiceError("No driving route was returned by Google Routes API.", status_code=400)

    primary_route = routes[0]
    encoded_poly = primary_route.get("polyline", {}).get("encodedPolyline", "")
    total_dist = float(primary_route.get("distanceMeters", 0.0))
    total_dur = parse_duration_string(primary_route.get("duration", "0s"))

    raw_legs = primary_route.get("legs", [])
    parsed_legs = []
    for idx, leg in enumerate(raw_legs):
        leg_dist = float(leg.get("distanceMeters", 0.0))
        leg_dur = parse_duration_string(leg.get("duration", "0s"))
        parsed_legs.append({
            "start_index": idx,
            "end_index": idx + 1,
            "distance_meters": leg_dist,
            "duration_seconds": leg_dur,
            "distance_km": round(leg_dist / 1000.0, 2),
            "duration_minutes": round(leg_dur / 60.0, 1),
        })

    return {
        "polyline": encoded_poly,
        "legs": parsed_legs,
        "total_distance_meters": total_dist,
        "total_duration_seconds": total_dur,
        "total_distance_km": round(total_dist / 1000.0, 2),
        "total_duration_minutes": round(total_dur / 60.0, 1),
        "dataSource": "LIVE GOOGLE DATA",
        "is_simulated": False,
    }


def get_route_geometry(
    ordered_stops: List[Dict[str, Any]],
    server_api_key: Optional[str] = None,
    force_demo: bool = False,
) -> Dict[str, Any]:
    """
    Retrieve route polyline and leg details with caching and automatic Demo fallback.

    Parameters:
    -----------
    ordered_stops : list of dict
        List of stops in visiting order.
    server_api_key : str or None
        Google Maps Server API Key.
    force_demo : bool
        If True, forces simulated polyline.

    Returns:
    --------
    dict:
        Polyline geometry, legs, distance, duration, and data source metadata.
    """
    if not ordered_stops or len(ordered_stops) < 2:
        raise ValueError("At least 2 stops are required to compute route geometry.")

    coord_key = tuple(
        (round(float(s["lat"]), 5), round(float(s["lng"]), 5))
        for s in ordered_stops
    )

    use_live = (not force_demo) and is_live_key_available(server_api_key)
    cache_lookup_key = (("LIVE",) if use_live else ("DEMO",)) + coord_key

    if cache_lookup_key in _ROUTE_CACHE:
        return _ROUTE_CACHE[cache_lookup_key]

    if use_live and server_api_key:
        result = compute_live_google_route(ordered_stops, server_api_key=server_api_key)
    else:
        result = compute_simulated_route_geometry(ordered_stops)

    _ROUTE_CACHE[cache_lookup_key] = result
    return result


def clear_route_cache() -> None:
    """Clear in-memory route cache (for isolated tests)."""
    _ROUTE_CACHE.clear()
