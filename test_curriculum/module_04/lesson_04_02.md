# Active Dendrites: Propagation and Amplification

## Key Insight
Voltage-gated channels in dendrites enable active signal propagation, amplification, and even dendritic spikes, transforming dendrites from passive cables into computational subunits with nonlinear integration properties.

## Learning Objectives
- Extend cable equation to include active conductances
- Analyze conditions for dendritic spike initiation and propagation
- Understand dendritic amplification and its computational implications
- Implement active cable models numerically

## Warmup (Callback)
Passive cable (lesson_04_01) attenuates signals; active channels can amplify and regenerate

## Content Outline
- Active cable equation: λ²∂²V/∂x² = τ∂V/∂t + V + I_active(V, x, t)
- Dendritic sodium and calcium channels: distribution and kinetics
- Dendritic spike initiation: local threshold mechanisms
- Backpropagating action potentials: soma-to-dendrite propagation
- Dendritic amplification: boosting distal synaptic inputs
- Computational implications: coincidence detection, direction selectivity
- Numerical methods: operator splitting for reaction-diffusion systems
- Experimental validation: dendritic recordings and imaging

## Key Concepts
- Active cable equation
- Dendritic spike
- Backpropagating action potential
- Dendritic amplification
- Reaction-diffusion system
- Coincidence detection

## Practical Examples
- Dendritic spike simulation: local Na+ channel activation
- Backpropagation simulation: AP initiated at soma propagating to dendrites
- Amplification demonstration: comparing passive vs. active integration
- Coincidence detection: temporal window for dendritic spike generation
- Parameter sensitivity: channel density effects on propagation

## Verification Criteria

### Knowledge Check
Students should implement active cable models, demonstrate dendritic spikes and backpropagation, and analyze computational implications

### Success Indicators
- Successfully simulates dendritic spike initiation and propagation
- Demonstrates backpropagating AP with realistic attenuation
- Shows amplification of distal inputs by active conductances
- Explains computational advantages of active dendrites

### Common Misconceptions
- Assuming all dendrites support full action potentials
- Neglecting calcium vs. sodium channel contributions
- Confusing backpropagation with antidromic propagation
- Misinterpreting amplification as eliminating distance dependence
