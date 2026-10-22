"""
Optimizer package for Smart Shortest Path Finder.
Provides pure Ant Colony Optimization (ACO), cost matrix services, and route geometry services.
"""

from optimizer.aco import (
    AntColonyOptimizer,
    solve_aco,
    calculate_path_cost,
    compute_percentage_improvement,
    validate_cost_matrix,
)
from optimizer.cost_matrix import (
    get_cost_matrices,
    compute_simulated_cost_matrix,
    compute_live_google_route_matrix,
    haversine_distance_meters,
    is_live_key_available,
    clear_matrix_cache,
    CostMatrixError,
)
from optimizer.route_service import (
    get_route_geometry,
    compute_simulated_route_geometry,
    compute_live_google_route,
    encode_polyline,
    clear_route_cache,
    RouteServiceError,
)

__all__ = [
    "AntColonyOptimizer",
    "solve_aco",
    "calculate_path_cost",
    "compute_percentage_improvement",
    "validate_cost_matrix",
    "get_cost_matrices",
    "compute_simulated_cost_matrix",
    "compute_live_google_route_matrix",
    "haversine_distance_meters",
    "is_live_key_available",
    "clear_matrix_cache",
    "CostMatrixError",
    "get_route_geometry",
    "compute_simulated_route_geometry",
    "compute_live_google_route",
    "encode_polyline",
    "clear_route_cache",
    "RouteServiceError",
]
