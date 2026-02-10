# Fisher Information: Parameter Estimation Bounds

## Key Insight
Fisher information quantifies how much data reveals about parameters, providing the Cramér-Rao bound on estimation accuracy and guiding optimal experimental design—connecting information theory to statistical inference in neuroscience.

## Learning Objectives
- Derive Fisher information from likelihood functions
- Apply Cramér-Rao bound to parameter estimation problems
- Compute Fisher information for neuronal models
- Use Fisher information to design optimal experiments and priors

## Warmup (Callback)
Mutual information (lesson_06_02) measures stimulus-response information; Fisher information measures parameter information

## Content Outline
- Fisher information definition: I(θ) = E[(∂log p(x;θ)/∂θ)²] = -E[∂²log p(x;θ)/∂θ²]
- Cramér-Rao bound: Var(θ̂) ≥ 1/I(θ)
- Multi-parameter case: Fisher information matrix
- Jeffreys prior: p(θ) ∝ √I(θ), optimal non-informative prior
- Application to neuronal models: estimating conductances, time constants
- Experimental design: maximizing Fisher information
- Relationship to mutual information: asymptotic equivalence
- Efficient estimators: achieving Cramér-Rao bound

## Key Concepts
- Fisher information
- Cramér-Rao bound
- Jeffreys prior
- Efficient estimator
- Fisher information matrix
- Optimal experimental design

## Practical Examples
- Fisher information for Gaussian: I(μ) = 1/σ², I(σ²) = 1/(2σ⁴)
- Poisson neuron: Fisher information for rate parameter
- Parameter estimation in IF model: computing I(θ) for threshold
- Jeffreys prior derivation for neuronal model parameters
- Optimal stimulus design: maximizing information about parameter

## Verification Criteria

### Knowledge Check
Students should compute Fisher information, apply Cramér-Rao bound, derive Jeffreys priors, and design optimal experiments

### Success Indicators
- Correctly computes Fisher information from likelihood
- Applies Cramér-Rao bound to assess estimator quality
- Derives Jeffreys prior from Fisher information
- Designs experiments maximizing information gain

### Common Misconceptions
- Confusing Fisher information with Shannon information
- Assuming all estimators achieve Cramér-Rao bound
- Neglecting regularity conditions for Cramér-Rao bound
- Misapplying single-parameter formulas to multi-parameter cases
