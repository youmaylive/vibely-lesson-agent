# Integrate-and-Fire Models: Minimal Neuronal Dynamics

## Key Insight
The integrate-and-fire model captures essential neuronal excitability with minimal mathematical complexity, revealing how threshold dynamics and reset mechanisms generate discrete spiking from continuous input integration.

## Learning Objectives
- Derive the integrate-and-fire model from RC circuit principles
- Analyze the role of threshold and reset in generating action potentials
- Compute firing rates analytically for constant and time-varying inputs
- Implement IF models computationally and validate against analytical solutions

## Warmup (Callback)
Recall fixed point attractors from lesson_01_01; IF model combines continuous dynamics with discrete reset

## Content Outline
- RC circuit analogy: C dV/dt = -g_L(V - V_rest) + I
- Dimensionless form: dV/dt = (V - V_rest)/γ + I/γ
- Threshold condition V ≥ V_thre triggers spike and reset
- Analytical solution for constant input: V(t) = V_rest + (I/g_L)(1 - exp(-t/τ))
- Firing rate calculation: f = 1/T where T is interspike interval
- Time-varying inputs and numerical integration requirements
- Limitations: no action potential shape, no refractoriness

## Key Concepts
- Membrane time constant τ = C/g_L
- Threshold potential V_thre
- Reset mechanism
- Interspike interval
- Firing rate
- Subthreshold integration

## Practical Examples
- Analytical derivation of firing rate for constant suprathreshold input
- Numerical simulation with Euler method: threshold detection and reset implementation
- Response to step current: latency to first spike
- Frequency-current (f-I) curve construction and interpretation

## Verification Criteria

### Knowledge Check
Students should derive firing rates analytically, implement IF model with proper threshold handling, and generate f-I curves matching theoretical predictions

### Success Indicators
- Correctly derives time to threshold for constant input
- Implements reset mechanism without numerical artifacts
- Generates f-I curves showing linear regime and saturation
- Explains biological significance of threshold and reset

### Common Misconceptions
- Treating threshold crossing as continuous rather than discrete event
- Forgetting to reset after spike detection in simulations
- Assuming linear f-I relationship holds for all input ranges
