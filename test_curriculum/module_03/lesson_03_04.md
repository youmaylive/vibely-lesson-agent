# Large Deviation Theory for Rare Events

## Key Insight
Large deviation theory provides the mathematical framework to quantify probabilities of rare but significant neuronal events—spontaneous synchronization, rare bursts, or escape from attractors—that standard perturbation theory cannot address.

## Learning Objectives
- Understand rate functions and large deviation principles
- Apply Freidlin-Wentzell theory to compute escape rates
- Identify most probable escape paths in neuronal models
- Relate large deviations to biological phenomena like spontaneous activity

## Warmup (Callback)
Kramers' rate (lesson_02_03) is special case; large deviation theory generalizes to complex landscapes

## Content Outline
- Large deviation principle: P(X ∈ A) ≈ exp(-I(A)/ε²)
- Rate function I(x): quantifying exponential decay of rare event probability
- Freidlin-Wentzell theory: escape from attractors in small noise limit
- Quasipotential: generalization of potential for non-gradient systems
- Most probable escape path: minimizing action functional
- Application to neuronal models: spontaneous firing, synchronization
- Numerical methods: minimum action path algorithms
- Connection to Kramers' formula: special case of large deviation theory

## Key Concepts
- Large deviation principle
- Rate function
- Freidlin-Wentzell theory
- Quasipotential
- Most probable path
- Action functional

## Practical Examples
- Escape from fixed point in FHN model: quasipotential calculation
- Most probable path computation using geometric minimum action method
- Spontaneous synchronization in coupled oscillators: rare event analysis
- Comparison: large deviation prediction vs. direct simulation
- Parameter dependence: how rate function varies with noise intensity

## Verification Criteria

### Knowledge Check
Students should compute rate functions, identify most probable paths, and validate large deviation predictions against simulations

### Success Indicators
- Correctly formulates rate function for given stochastic system
- Computes quasipotential for non-gradient neuronal models
- Identifies most probable escape path using variational methods
- Validates exponential scaling of rare event probabilities

### Common Misconceptions
- Assuming large deviation theory applies for moderate noise
- Confusing quasipotential with thermodynamic potential
- Neglecting non-gradient effects in neuronal systems
- Misapplying gradient descent to find most probable paths
