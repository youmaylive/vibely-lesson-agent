# Stability Analysis: Lyapunov Functions and Exponents

## Key Insight
Lyapunov methods provide rigorous mathematical proofs of stability and detect chaos, enabling prediction of long-term neuronal behavior and identification of parameter regimes where dynamics become unpredictable.

## Learning Objectives
- Construct Lyapunov functions to prove stability of equilibria
- Compute Lyapunov exponents numerically from trajectories
- Interpret positive Lyapunov exponents as signatures of chaos
- Apply stability analysis to neuronal models to predict response reliability

## Warmup (Callback)
Fixed point stability (lesson_01_04) via linearization; Lyapunov methods extend to nonlinear global analysis

## Content Outline
- Lyapunov function definition: V(x) > 0, dV/dt ≤ 0 along trajectories
- Energy-like functions for neuronal models
- Lyapunov's direct method: proving asymptotic stability
- Lyapunov exponents: λ = lim(t→∞) (1/t)ln|δx(t)/δx(0)|
- Numerical computation: trajectory separation method
- Interpretation: λ > 0 (chaos), λ = 0 (marginal), λ < 0 (stable)
- Spectrum of Lyapunov exponents for high-dimensional systems
- Application to neuronal models: detecting chaotic firing patterns

## Key Concepts
- Lyapunov function
- Asymptotic stability
- Lyapunov exponent
- Chaotic dynamics
- Trajectory separation
- Sensitive dependence on initial conditions

## Practical Examples
- Constructing quadratic Lyapunov function for linear system
- Numerical computation of largest Lyapunov exponent for FHN model
- Parameter scan: identifying chaotic regimes in modified HH model
- Comparison of regular vs. chaotic firing patterns
- Visualization: trajectory divergence in phase space

## Verification Criteria

### Knowledge Check
Students should construct Lyapunov functions for simple systems, compute Lyapunov exponents numerically, and identify chaotic parameter regimes

### Success Indicators
- Successfully constructs Lyapunov function proving stability
- Implements algorithm computing Lyapunov exponents from time series
- Correctly identifies chaotic vs. regular dynamics from exponent sign
- Relates chaos to unpredictability in neuronal firing

### Common Misconceptions
- Assuming Lyapunov function existence is easy to establish
- Confusing local (linearization) with global (Lyapunov function) stability
- Interpreting irregular firing as necessarily chaotic without computing exponents
- Neglecting finite-time effects in numerical Lyapunov exponent estimation
