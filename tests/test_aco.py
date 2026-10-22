"""
Unit tests for Ant Colony Optimization (optimizer/aco.py).
Tests pure algorithmic correctness, edge cases, parameter validations,
and reproducibility without any web or external dependencies.
"""

import pytest
import numpy as np
from optimizer.aco import (
    AntColonyOptimizer,
    solve_aco,
    validate_cost_matrix,
    calculate_path_cost,
    compute_percentage_improvement,
)


class TestCostMatrixValidation:
    """Tests for input validation of the pairwise cost matrix."""

    def test_valid_square_matrix(self):
        matrix = [
            [0.0, 10.0, 15.0],
            [10.0, 0.0, 20.0],
            [15.0, 20.0, 0.0],
        ]
        validated = validate_cost_matrix(matrix)
        assert isinstance(validated, np.ndarray)
        assert validated.shape == (3, 3)

    def test_none_matrix_raises_type_error(self):
        with pytest.raises(TypeError, match="cannot be None"):
            validate_cost_matrix(None)

    def test_empty_matrix_raises_value_error(self):
        with pytest.raises(ValueError, match="cannot be empty"):
            validate_cost_matrix([])

    def test_non_square_matrix_raises_value_error(self):
        matrix = [
            [0.0, 10.0, 20.0],
            [10.0, 0.0, 30.0],
        ]
        with pytest.raises(ValueError, match="must be square"):
            validate_cost_matrix(matrix)

    def test_single_element_matrix_raises_value_error(self):
        matrix = [[0.0]]
        with pytest.raises(ValueError, match="at least 2 stops"):
            validate_cost_matrix(matrix)

    def test_negative_costs_raise_value_error(self):
        matrix = [
            [0.0, -5.0],
            [5.0, 0.0],
        ]
        with pytest.raises(ValueError, match="negative"):
            validate_cost_matrix(matrix)

    def test_nan_or_inf_raises_value_error(self):
        matrix_nan = [
            [0.0, np.nan],
            [10.0, 0.0],
        ]
        with pytest.raises(ValueError, match="NaN"):
            validate_cost_matrix(matrix_nan)

        matrix_inf = [
            [0.0, np.inf],
            [10.0, 0.0],
        ]
        with pytest.raises(ValueError, match="infinite"):
            validate_cost_matrix(matrix_inf)

    def test_non_numeric_matrix_raises_type_error(self):
        matrix = [
            ["0", "abc"],
            ["xyz", "0"],
        ]
        with pytest.raises(TypeError, match="numeric"):
            validate_cost_matrix(matrix)


class TestHyperparameterValidation:
    """Tests for hyperparameter bounds and type validation."""

    @pytest.fixture
    def sample_matrix(self):
        return [
            [0.0, 10.0, 20.0, 30.0],
            [10.0, 0.0, 15.0, 25.0],
            [20.0, 15.0, 0.0, 10.0],
            [30.0, 25.0, 10.0, 0.0],
        ]

    def test_invalid_num_ants(self, sample_matrix):
        with pytest.raises(ValueError, match="num_ants must be an integer >= 1"):
            AntColonyOptimizer(sample_matrix, num_ants=0)
        with pytest.raises(ValueError, match="num_ants must be an integer >= 1"):
            AntColonyOptimizer(sample_matrix, num_ants=-5)

    def test_invalid_iterations(self, sample_matrix):
        with pytest.raises(ValueError, match="iterations must be an integer >= 1"):
            AntColonyOptimizer(sample_matrix, iterations=0)

    def test_invalid_alpha(self, sample_matrix):
        with pytest.raises(ValueError, match="alpha must be a non-negative number"):
            AntColonyOptimizer(sample_matrix, alpha=-0.5)

    def test_invalid_beta(self, sample_matrix):
        with pytest.raises(ValueError, match="beta must be a non-negative number"):
            AntColonyOptimizer(sample_matrix, beta=-1.0)

    def test_invalid_evaporation_rate(self, sample_matrix):
        with pytest.raises(ValueError, match="evaporation_rate must be strictly between 0.0 and 1.0"):
            AntColonyOptimizer(sample_matrix, evaporation_rate=0.0)
        with pytest.raises(ValueError, match="evaporation_rate must be strictly between 0.0 and 1.0"):
            AntColonyOptimizer(sample_matrix, evaporation_rate=1.0)
        with pytest.raises(ValueError, match="evaporation_rate must be strictly between 0.0 and 1.0"):
            AntColonyOptimizer(sample_matrix, evaporation_rate=1.5)

    def test_invalid_q(self, sample_matrix):
        with pytest.raises(ValueError, match="q must be a positive number"):
            AntColonyOptimizer(sample_matrix, q=0.0)
        with pytest.raises(ValueError, match="q must be a positive number"):
            AntColonyOptimizer(sample_matrix, q=-50.0)

    def test_invalid_seed_type(self, sample_matrix):
        with pytest.raises(TypeError, match="random_seed must be an integer"):
            AntColonyOptimizer(sample_matrix, random_seed="not_an_int")


class TestPathCostAndImprovement:
    """Tests for path cost calculation and percentage improvement formulas."""

    def test_calculate_path_cost(self):
        matrix = np.array([
            [0.0, 10.0, 20.0, 30.0],
            [10.0, 0.0, 15.0, 25.0],
            [20.0, 15.0, 0.0, 12.0],
            [30.0, 25.0, 12.0, 0.0],
        ])
        # Tour 0 -> 2 -> 1 -> 3
        # Cost: matrix[0,2] + matrix[2,1] + matrix[1,3] = 20 + 15 + 25 = 60
        tour = [0, 2, 1, 3]
        cost = calculate_path_cost(tour, matrix)
        assert cost == 60.0

    def test_percentage_improvement_normal(self):
        baseline = 100.0
        optimized = 70.0
        # ((100 - 70) / 100) * 100 = 30.0%
        improvement = compute_percentage_improvement(baseline, optimized)
        assert improvement == 30.0

    def test_percentage_improvement_zero_baseline(self):
        # Must not raise ZeroDivisionError
        improvement = compute_percentage_improvement(0.0, 0.0)
        assert improvement == 0.0

    def test_percentage_improvement_no_change(self):
        improvement = compute_percentage_improvement(50.0, 50.0)
        assert improvement == 0.0


class TestAcoAlgorithmCore:
    """Core algorithmic tests on known matrices."""

    def test_fixed_endpoints_and_single_visit(self):
        """
        Verify that Start (0) is first, Destination (N-1) is last,
        and intermediate stops are visited exactly once.
        """
        matrix = [
            [0.0, 12.0, 25.0, 19.0, 40.0],
            [12.0, 0.0, 10.0, 15.0, 35.0],
            [25.0, 10.0, 0.0, 8.0, 22.0],
            [19.0, 15.0, 8.0, 0.0, 14.0],
            [40.0, 35.0, 22.0, 14.0, 0.0],
        ]
        result = solve_aco(matrix, num_ants=15, iterations=30, random_seed=42)

        best_tour = result["best_tour"]
        n = len(matrix)

        # 1. Start is index 0
        assert best_tour[0] == 0

        # 2. Destination is index N-1
        assert best_tour[-1] == n - 1

        # 3. Every node visited exactly once
        assert sorted(best_tour) == list(range(n))
        assert len(best_tour) == n
        assert len(set(best_tour)) == n

    def test_small_known_matrix_finds_optimal_solution(self):
        """
        Create a 5-stop problem where stops lie on a line:
        0 at 0km, 1 at 30km, 2 at 10km, 3 at 40km, 4 at 50km.
        Baseline order: 0 -> 1 -> 2 -> 3 -> 4
        Costs:
          0 -> 1 = 30
          1 -> 2 = 20
          2 -> 3 = 30
          3 -> 4 = 10
          Total Baseline Cost = 90

        Optimal order: 0 -> 2 -> 1 -> 3 -> 4
        Costs:
          0 -> 2 = 10
          2 -> 1 = 20
          1 -> 3 = 10
          3 -> 4 = 10
          Total Optimal Cost = 50 (44.44% improvement)
        """
        coords = [0.0, 30.0, 10.0, 40.0, 50.0]
        n = len(coords)
        matrix = [[abs(coords[i] - coords[j]) for j in range(n)] for i in range(n)]

        result = solve_aco(
            matrix,
            num_ants=20,
            iterations=40,
            alpha=1.0,
            beta=3.0,
            evaporation_rate=0.2,
            random_seed=123,
        )

        assert result["baseline_cost"] == 90.0
        assert result["best_tour"] == [0, 2, 1, 3, 4]
        assert result["best_cost"] == 50.0
        assert result["improvement_percentage"] == 44.44

    def test_asymmetric_cost_matrix(self):
        """
        Test with an asymmetric cost matrix (where cost(A->B) != cost(B->A)).
        Simulates one-way city streets.
        """
        matrix = [
            [0.0, 10.0, 100.0, 200.0],
            [100.0, 0.0, 10.0, 100.0],
            [10.0, 100.0, 0.0, 10.0],
            [200.0, 100.0, 10.0, 0.0],
        ]
        # Baseline: 0 -> 1 -> 2 -> 3
        # Cost: 0->1 (10) + 1->2 (10) + 2->3 (10) = 30
        # Alternative: 0 -> 2 -> 1 -> 3
        # Cost: 0->2 (100) + 2->1 (100) + 1->3 (100) = 300
        result = solve_aco(matrix, num_ants=15, iterations=25, random_seed=99)
        assert result["best_tour"] == [0, 1, 2, 3]
        assert result["best_cost"] == 30.0

    def test_reproducibility_with_fixed_seed(self):
        """Two runs with the identical random_seed must produce identical tours and costs."""
        matrix = [
            [0.0, 14.0, 35.0, 18.0, 50.0],
            [14.0, 0.0, 22.0, 11.0, 42.0],
            [35.0, 22.0, 0.0, 16.0, 25.0],
            [18.0, 11.0, 16.0, 0.0, 30.0],
            [50.0, 42.0, 25.0, 30.0, 0.0],
        ]
        run1 = solve_aco(matrix, num_ants=10, iterations=20, random_seed=777)
        run2 = solve_aco(matrix, num_ants=10, iterations=20, random_seed=777)

        assert run1["best_tour"] == run2["best_tour"]
        assert run1["best_cost"] == run2["best_cost"]
        assert run1["iteration_history"] == run2["iteration_history"]

    def test_zero_cost_edge_case(self):
        """Co-located stops with cost 0 must not cause division by zero."""
        matrix = [
            [0.0, 0.0, 20.0],
            [0.0, 0.0, 15.0],
            [20.0, 15.0, 0.0],
        ]
        result = solve_aco(matrix, num_ants=5, iterations=10, random_seed=1)
        assert result["best_cost"] >= 0.0
        assert len(result["best_tour"]) == 3

    def test_all_zeros_matrix(self):
        """All zero costs should complete cleanly without errors."""
        matrix = [
            [0.0, 0.0, 0.0],
            [0.0, 0.0, 0.0],
            [0.0, 0.0, 0.0],
        ]
        result = solve_aco(matrix, num_ants=5, iterations=5, random_seed=1)
        assert result["best_cost"] == 0.0
        assert result["improvement_percentage"] == 0.0

    def test_degenerate_two_nodes(self):
        """Only start and destination (no intermediate stops)."""
        matrix = [
            [0.0, 42.5],
            [42.5, 0.0],
        ]
        result = solve_aco(matrix, num_ants=5, iterations=5)
        assert result["best_tour"] == [0, 1]
        assert result["best_cost"] == 42.5
        assert result["improvement_percentage"] == 0.0

    def test_degenerate_three_nodes(self):
        """Start, exactly one intermediate stop, destination."""
        matrix = [
            [0.0, 15.0, 50.0],
            [15.0, 0.0, 25.0],
            [50.0, 25.0, 0.0],
        ]
        result = solve_aco(matrix, num_ants=5, iterations=5)
        assert result["best_tour"] == [0, 1, 2]
        assert result["best_cost"] == 40.0
        assert result["improvement_percentage"] == 0.0

    def test_pheromone_evaporation_and_deposit_internals(self):
        """Test internal pheromone evaporation and deposit mechanics directly."""
        matrix = np.array([
            [0.0, 10.0, 20.0, 30.0],
            [10.0, 0.0, 15.0, 25.0],
            [20.0, 15.0, 0.0, 10.0],
            [30.0, 25.0, 10.0, 0.0],
        ])
        optimizer = AntColonyOptimizer(
            matrix,
            num_ants=2,
            iterations=5,
            evaporation_rate=0.2,
            q=100.0,
            elitist_weight=1.0,
            random_seed=42,
        )

        initial_ph = optimizer.pheromone.copy()

        # Test evaporation: tau <- (1 - 0.2) * tau = 0.8 * tau
        optimizer._evaporate_pheromone()
        expected_evaporation = initial_ph * 0.8
        np.testing.assert_allclose(optimizer.pheromone, expected_evaporation, rtol=1e-5)

        # Test deposit: tour [0, 1, 2, 3], cost = 35.0
        # Delta tau = 100 / 35 = 2.85714
        tour = [0, 1, 2, 3]
        cost = 35.0
        optimizer._deposit_pheromone(ant_tours=[(tour, cost)], best_tour=tour, best_cost=cost)

        # Edge (0, 1) was traversed by ant + elitist: + 2 * (100 / 35)
        expected_boost = 2.0 * (100.0 / 35.0)
        assert optimizer.pheromone[0, 1] > expected_evaporation[0, 1] + expected_boost - 1e-4
