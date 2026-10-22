"""
Demonstration script for pure Ant Colony Optimization (ACO).
Runs on a known asymmetric/straight-line cost matrix to prove convergence and cost reduction.
"""

import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from optimizer.aco import solve_aco, calculate_path_cost

def main():
    # 5 stops along a line:
    # Stop 0 (Start): 0 km
    # Stop 1: 30 km
    # Stop 2: 10 km
    # Stop 3: 40 km
    # Stop 4 (Destination): 50 km
    #
    # Baseline user order: 0 -> 1 -> 2 -> 3 -> 4
    # Distance: 30 + 20 + 30 + 10 = 90 km
    #
    # Optimal ACO order: 0 -> 2 -> 1 -> 3 -> 4
    # Distance: 10 + 20 + 10 + 10 = 50 km (44.44% improvement)
    coords = [0.0, 30.0, 10.0, 40.0, 50.0]
    n = len(coords)
    matrix = [[abs(coords[i] - coords[j]) for j in range(n)] for i in range(n)]

    print("=" * 60)
    print("ANT COLONY OPTIMIZATION (ACO) - RUNTIME DEMONSTRATION")
    print("=" * 60)
    print(f"Number of stops: {n} (Fixed Start: 0, Fixed Destination: {n-1})")
    print("\nPairwise Cost Matrix (km):")
    for idx, row in enumerate(matrix):
        print(f"  Stop {idx}: {row}")

    result = solve_aco(
        matrix,
        num_ants=20,
        iterations=30,
        alpha=1.0,
        beta=2.5,
        evaporation_rate=0.2,
        q=100.0,
        random_seed=42
    )

    print("\n--- RESULTS ---")
    print(f"Original Baseline Tour : {result['baseline_tour']}")
    print(f"Baseline Cost          : {result['baseline_cost']} km")
    print(f"ACO Optimized Tour     : {result['best_tour']}")
    print(f"Optimized Cost         : {result['best_cost']} km")
    print(f"Improvement            : {result['improvement_percentage']}%")
    print(f"Iteration History      : {result['iteration_history'][:5]} ... -> final: {result['iteration_history'][-1]} km")
    print("=" * 60)

if __name__ == "__main__":
    main()
