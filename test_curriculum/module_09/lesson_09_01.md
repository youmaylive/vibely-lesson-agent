# Spike-Timing-Dependent Plasticity (STDP)

## Key Insight
STDP implements a local, temporally asymmetric learning rule where synaptic strength changes depend on precise spike timing, providing a biologically plausible mechanism for learning temporal sequences and causal relationships.

## Learning Objectives
- Derive STDP learning rules from experimental data
- Implement STDP in network simulations
- Analyze stability and competition in STDP learning
- Relate STDP to computational learning theories

## Warmup (Callback)
Synaptic transmission (module_03) with fixed weights; STDP makes weights plastic based on timing

## Content Outline
- STDP experimental observations: timing-dependent weight changes
- STDP window: Δw = A_+ exp(-Δt/τ_+) for Δt > 0, Δw = -A_- exp(Δt/τ_-) for Δt < 0
- Temporal asymmetry: causality detection
- Additive vs. multiplicative STDP
- Weight dynamics: dw/dt = Σ_spikes STDP_window(Δt)
- Stability analysis: weight competition and normalization
- Computational functions: sequence learning, temporal coding
- Relationship to reinforcement learning and temporal difference learning

## Key Concepts
- STDP
- Temporal asymmetry
- Synaptic plasticity
- Weight competition
- Sequence learning
- Causality detection

## Practical Examples
- STDP window implementation: exponential kernels
- Network simulation: STDP in recurrent network
- Sequence learning: training network to replay temporal patterns
- Weight distribution evolution: competition and stabilization
- Comparison with Hebbian learning: advantages of temporal precision

## Verification Criteria

### Knowledge Check
Students should implement STDP rules, simulate network learning, and analyze stability

### Success Indicators
- Correctly implements STDP window with temporal asymmetry
- Demonstrates sequence learning in network simulation
- Analyzes weight competition and stability
- Relates STDP to computational learning principles

### Common Misconceptions
- Assuming STDP always leads to stable weight distributions
- Neglecting weight normalization mechanisms
- Confusing STDP with rate-based Hebbian learning
- Misinterpreting temporal asymmetry as purely causal
