# Beyond Kuramoto: Realistic Network Synchronization

## Key Insight
Real neuronal networks exhibit complex synchronization patterns—clustering, chimera states, metastability—requiring extensions beyond Kuramoto including heterogeneous coupling, delays, and noise to capture experimental observations.

## Learning Objectives
- Extend Kuramoto model to include coupling heterogeneity and delays
- Analyze chimera states: coexistence of synchrony and asynchrony
- Incorporate noise and study noise-induced synchronization
- Connect extended models to experimental data on brain rhythms

## Warmup (Callback)
Basic Kuramoto (lesson_05_02) assumes uniform coupling; realistic networks have heterogeneous, delayed connections

## Content Outline
- Heterogeneous coupling: dθ_i/dt = ω_i + Σ_j K_ij sin(θ_j - θ_i)
- Coupling matrix K_ij: distance-dependent, small-world, scale-free
- Time delays: dθ_i/dt = ω_i + Σ_j K_ij sin(θ_j(t - τ_ij) - θ_i)
- Chimera states: spatially localized synchrony/asynchrony
- Noise effects: common noise synchronization, diversity-induced resonance
- Metastability: transient synchronization patterns
- Experimental validation: EEG/MEG rhythms, in vitro networks
- Computational tools: network analysis, spectral methods

## Key Concepts
- Heterogeneous coupling
- Time delays
- Chimera states
- Metastability
- Common noise synchronization
- Network topology

## Practical Examples
- Distance-dependent coupling: spatial Kuramoto model
- Delay effects: stability analysis and oscillation death
- Chimera state simulation: non-local coupling with phase lag
- Noise-induced synchronization: common input to subpopulation
- EEG data analysis: extracting phase and computing synchronization measures

## Verification Criteria

### Knowledge Check
Students should implement extended Kuramoto models, demonstrate chimera states, and analyze experimental synchronization data

### Success Indicators
- Correctly implements heterogeneous coupling and delays
- Demonstrates chimera states with appropriate parameters
- Shows noise-induced synchronization effects
- Analyzes experimental data using phase synchronization measures

### Common Misconceptions
- Assuming delays always destabilize synchronization
- Confusing chimera states with partial synchronization
- Neglecting network topology effects on synchronization
- Misapplying Kuramoto framework to non-oscillatory neurons
