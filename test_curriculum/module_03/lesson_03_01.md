# Diffusion Processes: Ornstein-Uhlenbeck and Beyond

## Key Insight
The Ornstein-Uhlenbeck process provides the canonical model for continuous stochastic fluctuations in membrane potential, balancing mean reversion with diffusive noise to capture subthreshold dynamics.

## Learning Objectives
- Derive the Ornstein-Uhlenbeck process from physical principles
- Solve for stationary distribution and correlation functions analytically
- Implement numerical integration using Euler-Maruyama method
- Apply OU process to model subthreshold membrane potential fluctuations

## Warmup (Callback)
Deterministic IF model (lesson_01_02) with constant input; OU process adds realistic fluctuations

## Content Outline
- Wiener process (Brownian motion): dW with Gaussian increments
- OU process definition: dV = -(V - μ)/γ dt + σ dW
- Mean reversion: drift toward μ with timescale γ
- Analytical solution: V(t) = μ + (V₀ - μ)exp(-t/γ) + noise integral
- Stationary distribution: Gaussian with mean μ, variance σ²γ/2
- Autocorrelation function: C(τ) = (σ²γ/2)exp(-|τ|/γ)
- Numerical integration: Euler-Maruyama scheme
- Application: subthreshold membrane potential with synaptic bombardment

## Key Concepts
- Wiener process
- Ornstein-Uhlenbeck process
- Mean reversion
- Stationary distribution
- Autocorrelation function
- Euler-Maruyama method

## Practical Examples
- Analytical derivation of OU stationary distribution
- Numerical simulation: trajectory generation and histogram comparison
- Autocorrelation estimation from simulated data
- Parameter fitting: estimating μ, γ, σ from experimental traces
- OU-driven IF model: firing rate with fluctuating input

## Verification Criteria

### Knowledge Check
Students should derive stationary distribution, implement Euler-Maruyama integration, and validate numerical results against analytical predictions

### Success Indicators
- Correctly derives stationary Gaussian distribution
- Implements Euler-Maruyama with appropriate timestep
- Numerical histogram matches analytical distribution
- Computes autocorrelation matching exponential decay

### Common Misconceptions
- Confusing Wiener process increments with Gaussian white noise
- Using deterministic integration schemes for SDEs
- Assuming OU process is always at stationarity
- Neglecting timestep dependence in numerical accuracy
