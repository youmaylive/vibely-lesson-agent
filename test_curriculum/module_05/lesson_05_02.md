# Kuramoto Model: Collective Synchronization

## Key Insight
The Kuramoto model reveals how coupling strength and frequency heterogeneity compete to determine collective synchronization, exhibiting a phase transition where coherent oscillations emerge above critical coupling—a paradigm for understanding brain rhythms.

## Learning Objectives
- Derive Kuramoto model from phase-coupled oscillators
- Analyze mean-field theory and order parameter dynamics
- Compute critical coupling strength for synchronization transition
- Relate Kuramoto dynamics to neuronal network synchronization

## Warmup (Callback)
Phase reduction (lesson_05_01) gives single oscillator; Kuramoto couples many oscillators

## Content Outline
- Kuramoto model: dθ_i/dt = ω_i + (K/N)Σ_j sin(θ_j - θ_i)
- Natural frequency distribution: g(ω), often Lorentzian
- Order parameter: r exp(iψ) = (1/N)Σ_j exp(iθ_j)
- Mean-field reduction: dθ_i/dt = ω_i + Kr sin(ψ - θ_i)
- Self-consistency equation for r(K)
- Critical coupling: K_c = 2/(πg(0)) for Lorentzian g(ω)
- Phase transition: r = 0 (incoherent) to r > 0 (synchronized)
- Biological interpretation: brain rhythms, epileptic seizures

## Key Concepts
- Kuramoto model
- Order parameter
- Natural frequency distribution
- Critical coupling
- Phase transition
- Mean-field theory

## Practical Examples
- Numerical simulation: N oscillators with Lorentzian frequency distribution
- Order parameter evolution: tracking r(t) and ψ(t)
- Critical coupling determination: r vs. K bifurcation diagram
- Frequency distribution effects: comparing Lorentzian vs. Gaussian
- Biological application: modeling alpha rhythm synchronization

## Verification Criteria

### Knowledge Check
Students should simulate Kuramoto model, compute order parameter, identify critical coupling, and relate to neuronal synchronization

### Success Indicators
- Correctly implements Kuramoto model for N oscillators
- Computes order parameter showing synchronization transition
- Identifies K_c matching theoretical prediction
- Explains biological relevance to brain rhythms

### Common Misconceptions
- Assuming synchronization occurs for any K > 0
- Confusing order parameter r with firing rate
- Neglecting frequency distribution shape effects on K_c
- Misinterpreting partial synchronization (0 < r < 1)
