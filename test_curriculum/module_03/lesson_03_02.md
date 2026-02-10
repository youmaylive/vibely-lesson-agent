# Jump Processes: Poisson Synaptic Input

## Key Insight
Synaptic inputs arrive as discrete, random events best modeled by jump processes, where Poisson statistics capture the stochastic timing and jump amplitudes represent postsynaptic potential sizes.

## Learning Objectives
- Derive Poisson process properties: exponential inter-event intervals
- Model synaptic input as compound Poisson process with random amplitudes
- Implement event-driven simulation of jump processes
- Analyze firing statistics of neurons driven by Poisson input

## Warmup (Callback)
OU process (lesson_03_01) models continuous noise; jump processes capture discrete synaptic events

## Content Outline
- Poisson process: N(t) counting events with rate λ
- Inter-event interval distribution: P(τ) = λexp(-λτ)
- Compound Poisson process: random jump amplitudes aε
- SDE with jumps: dV = -(V - V_rest)/γ dt + aε dN
- Event-driven vs. time-driven simulation strategies
- Firing rate calculation with Poisson input: renewal theory
- Coefficient of variation: CV = σ_ISI / μ_ISI
- Comparison with experimental data: irregular firing patterns

## Key Concepts
- Poisson process
- Compound Poisson process
- Jump amplitude
- Inter-event interval
- Event-driven simulation
- Coefficient of variation

## Practical Examples
- Poisson event generation: exponential interval sampling
- Event-driven IF simulation with Poisson synaptic input
- ISI distribution analysis: exponential vs. gamma distributions
- CV calculation: quantifying firing irregularity
- Rate modulation: varying λ to control input statistics

## Verification Criteria

### Knowledge Check
Students should implement event-driven Poisson simulations, analyze ISI distributions, and compute CV from spike trains

### Success Indicators
- Correctly generates Poisson events with exponential intervals
- Implements event-driven simulation efficiently
- ISI histogram matches theoretical predictions
- Computes CV showing irregular firing (CV ≈ 1 for Poisson)

### Common Misconceptions
- Assuming fixed inter-event intervals for Poisson process
- Confusing event rate λ with firing rate
- Using time-driven simulation inefficiently for rare events
- Misinterpreting CV: CV = 1 is irregular, not regular
