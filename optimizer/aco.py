"""
Ant Colony Optimization (ACO) for Open TSP with Fixed Endpoints.

Problem Formulation:
-------------------
Given N locations with a pairwise cost matrix C (where C[i][j] is the cost
of traveling from stop i to stop j, either distance in meters or time in seconds):
- Stop 0 is the FIXED START point.
- Stop N-1 is the FIXED DESTINATION point.
- Stops 1 to N-2 are INTERMEDIATE STOPS that must each be visited EXACTLY ONCE.

This is a variant of the Traveling Salesperson Problem known as the
"Open TSP with Fixed Endpoints" or "Fixed-Endpoint Hamiltonian Path".

Pure Python & NumPy Implementation:
-----------------------------------
This module is strictly self-contained. It contains NO Flask, NO web requests,
and NO Google Maps dependencies.
"""

from typing import Dict, List, Optional, Tuple, Union, Any
import numpy as np


def validate_cost_matrix(matrix: Union[List[List[float]], np.ndarray]) -> np.ndarray:
    """
    Validate that the input cost matrix is a non-empty, square 2D array of non-negative numbers.

    Parameters:
    -----------
    matrix : list of lists or numpy.ndarray
        The pairwise cost matrix of shape (N, N).

    Returns:
    --------
    np.ndarray:
        The validated cost matrix as a 2D float64 NumPy array.

    Raises:
    -------
    TypeError:
        If input is None or cannot be converted to a numeric NumPy array.
    ValueError:
        If matrix is empty, not 2-dimensional, not square, has size < 2,
        or contains negative values, NaN, or infinite numbers.
    """
    if matrix is None:
        raise TypeError("Cost matrix cannot be None.")

    try:
        mat = np.array(matrix, dtype=np.float64)
    except (ValueError, TypeError) as exc:
        raise TypeError(f"Cost matrix must contain numeric values: {exc}") from exc

    if mat.size == 0:
        raise ValueError("Cost matrix cannot be empty.")

    if mat.ndim != 2:
        raise ValueError(f"Cost matrix must be 2-dimensional, but got {mat.ndim} dimensions.")

    n_rows, n_cols = mat.shape

    if n_rows != n_cols:
        raise ValueError(f"Cost matrix must be square (N x N), but got shape ({n_rows}, {n_cols}).")

    if n_rows < 2:
        raise ValueError(
            f"Cost matrix must have at least 2 stops (start and destination), but got {n_rows}."
        )

    if np.isnan(mat).any():
        raise ValueError("Cost matrix contains NaN (Not a Number) values.")

    if np.isinf(mat).any():
        raise ValueError("Cost matrix contains infinite values.")

    if (mat < 0).any():
        raise ValueError("Cost matrix cannot contain negative costs.")

    return mat


def calculate_path_cost(tour: List[int], cost_matrix: np.ndarray) -> float:
    """
    Calculate the total cost of a sequential path (tour) through the cost matrix.

    Total cost = sum of costs of all consecutive legs along the tour:
    L = C[tour[0]][tour[1]] + C[tour[1]][tour[2]] + ... + C[tour[k]][tour[k+1]]

    Parameters:
    -----------
    tour : list of int
        List of stop indices in visit order, e.g. [0, 2, 1, 3].
    cost_matrix : np.ndarray
        Square cost matrix of shape (N, N).

    Returns:
    --------
    float:
        The sum of travel costs across all sequential legs.
    """
    if not tour or len(tour) < 2:
        return 0.0

    total_cost = 0.0
    for idx in range(len(tour) - 1):
        from_node = tour[idx]
        to_node = tour[idx + 1]
        total_cost += float(cost_matrix[from_node, to_node])
    return total_cost


def compute_percentage_improvement(baseline_cost: float, optimized_cost: float) -> float:
    """
    Compute percentage improvement of the optimized cost over the baseline cost.

    Formula:
        improvement = ((baseline - optimized) / baseline) * 100

    Safely handles edge cases where baseline is zero or negative.

    Parameters:
    -----------
    baseline_cost : float
        The cost of the tour in the original user-specified order.
    optimized_cost : float
        The cost of the tour discovered by ACO.

    Returns:
    --------
    float:
        Percentage improvement rounded to 2 decimal places. Positive means ACO is better.
    """
    if baseline_cost <= 0.0:
        return 0.0

    raw_improvement = ((baseline_cost - optimized_cost) / baseline_cost) * 100.0
    return round(float(raw_improvement), 2)


class AntColonyOptimizer:
    """
    Ant Colony Optimization (ACO) algorithm tailored for the Open TSP with Fixed Endpoints.
    """

    def __init__(
        self,
        cost_matrix: Union[List[List[float]], np.ndarray],
        num_ants: int = 20,
        iterations: int = 50,
        alpha: float = 1.0,
        beta: float = 2.5,
        evaporation_rate: float = 0.2,
        q: float = 100.0,
        elitist_weight: float = 1.0,
        random_seed: Optional[int] = None,
    ) -> None:
        self.matrix = validate_cost_matrix(cost_matrix)
        self.num_nodes = int(self.matrix.shape[0])

        self._validate_parameters(
            num_ants=num_ants,
            iterations=iterations,
            alpha=alpha,
            beta=beta,
            evaporation_rate=evaporation_rate,
            q=q,
            elitist_weight=elitist_weight,
            random_seed=random_seed,
        )

        self.num_ants = int(num_ants)
        self.iterations = int(iterations)
        self.alpha = float(alpha)
        self.beta = float(beta)
        self.rho = float(evaporation_rate)
        self.q = float(q)
        self.elitist_weight = float(elitist_weight)
        self.random_seed = random_seed

        self.rng = np.random.default_rng(seed=self.random_seed)
        self.eps = 1e-6

        # Initialize heuristic matrix eta = 1 / max(cost, eps)
        self.heuristic = np.zeros_like(self.matrix, dtype=np.float64)
        for i in range(self.num_nodes):
            for j in range(self.num_nodes):
                if i != j:
                    c = self.matrix[i, j]
                    self.heuristic[i, j] = 1.0 / max(c, self.eps)

        self.baseline_tour = list(range(self.num_nodes))
        self.baseline_cost = calculate_path_cost(self.baseline_tour, self.matrix)

        initial_pheromone = 1.0
        if self.baseline_cost > self.eps:
            initial_pheromone = self.q / self.baseline_cost
        self.initial_pheromone = max(initial_pheromone, self.eps)
        self.min_pheromone = self.initial_pheromone * 1e-4

        self.pheromone = np.full(
            (self.num_nodes, self.num_nodes),
            fill_value=self.initial_pheromone,
            dtype=np.float64,
        )

    def _validate_parameters(
        self,
        num_ants: int,
        iterations: int,
        alpha: float,
        beta: float,
        evaporation_rate: float,
        q: float,
        elitist_weight: float,
        random_seed: Optional[int],
    ) -> None:
        if not isinstance(num_ants, (int, np.integer)) or num_ants < 1:
            raise ValueError(f"num_ants must be an integer >= 1, but got {num_ants}.")

        if not isinstance(iterations, (int, np.integer)) or iterations < 1:
            raise ValueError(f"iterations must be an integer >= 1, but got {iterations}.")

        if not isinstance(alpha, (int, float, np.floating)) or alpha < 0.0:
            raise ValueError(f"alpha must be a non-negative number >= 0.0, but got {alpha}.")

        if not isinstance(beta, (int, float, np.floating)) or beta < 0.0:
            raise ValueError(f"beta must be a non-negative number >= 0.0, but got {beta}.")

        if (
            not isinstance(evaporation_rate, (int, float, np.floating))
            or evaporation_rate <= 0.0
            or evaporation_rate >= 1.0
        ):
            raise ValueError(
                f"evaporation_rate must be strictly between 0.0 and 1.0, but got {evaporation_rate}."
            )

        if not isinstance(q, (int, float, np.floating)) or q <= 0.0:
            raise ValueError(f"q must be a positive number > 0.0, but got {q}.")

        if not isinstance(elitist_weight, (int, float, np.floating)) or elitist_weight < 0.0:
            raise ValueError(
                f"elitist_weight must be a non-negative number >= 0.0, but got {elitist_weight}."
            )

        if random_seed is not None and not isinstance(random_seed, (int, np.integer)):
            raise TypeError(f"random_seed must be an integer or None, but got {type(random_seed)}.")

    def _construct_single_ant_tour(self) -> Tuple[List[int], float]:
        start_node = 0
        dest_node = self.num_nodes - 1
        intermediate_nodes = list(range(1, dest_node))

        if not intermediate_nodes:
            tour = [start_node, dest_node]
            cost = calculate_path_cost(tour, self.matrix)
            return tour, cost

        if len(intermediate_nodes) == 1:
            tour = [start_node, intermediate_nodes[0], dest_node]
            cost = calculate_path_cost(tour, self.matrix)
            return tour, cost

        tour = [start_node]
        current_node = start_node
        unvisited = set(intermediate_nodes)

        while unvisited:
            candidates = list(unvisited)
            probs = np.zeros(len(candidates), dtype=np.float64)
            for idx, candidate in enumerate(candidates):
                tau = self.pheromone[current_node, candidate]
                eta = self.heuristic[current_node, candidate]
                tau_term = (tau ** self.alpha) if self.alpha > 0.0 else 1.0
                eta_term = (eta ** self.beta) if self.beta > 0.0 else 1.0
                probs[idx] = tau_term * eta_term

            prob_sum = float(np.sum(probs))
            if prob_sum > self.eps and not np.isnan(prob_sum):
                probs = probs / prob_sum
            else:
                probs = np.full(len(candidates), 1.0 / len(candidates), dtype=np.float64)

            selected_candidate = self.rng.choice(candidates, p=probs)
            tour.append(int(selected_candidate))
            unvisited.remove(selected_candidate)
            current_node = selected_candidate

        tour.append(dest_node)
        cost = calculate_path_cost(tour, self.matrix)
        return tour, cost

    def _evaporate_pheromone(self) -> None:
        self.pheromone = (1.0 - self.rho) * self.pheromone
        self.pheromone = np.maximum(self.pheromone, self.min_pheromone)

    def _deposit_pheromone(
        self, ant_tours: List[Tuple[List[int], float]], best_tour: List[int], best_cost: float
    ) -> None:
        deposit_matrix = np.zeros_like(self.pheromone, dtype=np.float64)

        for tour, cost in ant_tours:
            deposit_amount = self.q / max(cost, self.eps)
            for idx in range(len(tour) - 1):
                u = tour[idx]
                v = tour[idx + 1]
                deposit_matrix[u, v] += deposit_amount

        if self.elitist_weight > 0.0 and best_tour:
            best_deposit = self.elitist_weight * (self.q / max(best_cost, self.eps))
            for idx in range(len(best_tour) - 1):
                u = best_tour[idx]
                v = best_tour[idx + 1]
                deposit_matrix[u, v] += best_deposit

        self.pheromone += deposit_matrix

    def run(self) -> Dict[str, Any]:
        if self.num_nodes <= 3:
            best_tour = self.baseline_tour.copy()
            best_cost = self.baseline_cost
            improvement = compute_percentage_improvement(self.baseline_cost, best_cost)
            history = [best_cost] * self.iterations
            return {
                "best_tour": best_tour,
                "best_cost": float(best_cost),
                "baseline_tour": self.baseline_tour,
                "baseline_cost": float(self.baseline_cost),
                "improvement_percentage": float(improvement),
                "iteration_history": history,
                "num_iterations": self.iterations,
                "num_ants": self.num_ants,
            }

        best_tour = self.baseline_tour.copy()
        best_cost = self.baseline_cost
        iteration_history: List[float] = []

        for _ in range(self.iterations):
            iteration_tours: List[Tuple[List[int], float]] = []

            for _ in range(self.num_ants):
                tour, cost = self._construct_single_ant_tour()
                iteration_tours.append((tour, cost))

                if cost < best_cost:
                    best_cost = cost
                    best_tour = tour.copy()

            self._evaporate_pheromone()
            self._deposit_pheromone(iteration_tours, best_tour, best_cost)
            iteration_history.append(float(best_cost))

        improvement = compute_percentage_improvement(self.baseline_cost, best_cost)

        return {
            "best_tour": best_tour,
            "best_cost": float(best_cost),
            "baseline_tour": self.baseline_tour,
            "baseline_cost": float(self.baseline_cost),
            "improvement_percentage": float(improvement),
            "iteration_history": iteration_history,
            "num_iterations": self.iterations,
            "num_ants": self.num_ants,
        }


def solve_aco(
    cost_matrix: Union[List[List[float]], np.ndarray],
    num_ants: int = 20,
    iterations: int = 50,
    alpha: float = 1.0,
    beta: float = 2.5,
    evaporation_rate: float = 0.2,
    q: float = 100.0,
    elitist_weight: float = 1.0,
    random_seed: Optional[int] = None,
) -> Dict[str, Any]:
    optimizer = AntColonyOptimizer(
        cost_matrix=cost_matrix,
        num_ants=num_ants,
        iterations=iterations,
        alpha=alpha,
        beta=beta,
        evaporation_rate=evaporation_rate,
        q=q,
        elitist_weight=elitist_weight,
        random_seed=random_seed,
    )
    return optimizer.run()
