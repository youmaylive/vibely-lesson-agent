# Maximum Likelihood Estimation for Neuronal Models

## Key Insight
Maximum likelihood provides a principled, general framework for fitting neuronal models to data by finding parameters that make observed data most probable, with Fisher information quantifying estimation accuracy.

## Learning Objectives
- Derive likelihood functions for neuronal models
- Implement numerical optimization for maximum likelihood
- Compute Fisher information and Cramér-Rao bounds
- Assess parameter identifiability and uncertainty

## Warmup (Callback)
Fisher information (lesson_06_03) bounds estimation accuracy; MLE achieves this bound asymptotically

## Content Outline
- Likelihood function: L(θ|data) = P(data|θ)
- Log-likelihood: ℓ(θ) = log L(θ|data), easier to optimize
- Maximum likelihood estimate: θ̂_MLE = argmax_θ ℓ(θ)
- Numerical optimization: gradient descent, Newton-Raphson, BFGS
- Fisher information from Hessian: I(θ) = -E[∂²ℓ/∂θ²]
- Asymptotic normality: θ̂_MLE ~ N(θ_true, I(θ)⁻¹)
- Confidence intervals: using Fisher information
- Identifiability analysis: when parameters can be uniquely determined

## Key Concepts
- Likelihood function
- Maximum likelihood estimate
- Fisher information matrix
- Cramér-Rao bound
- Identifiability
- Asymptotic normality

## Practical Examples
- MLE for Poisson neuron: rate parameter from spike counts
- IF model parameter estimation: threshold and time constant from voltage traces
- HH model fitting: conductances from voltage clamp data
- Fisher information computation: numerical Hessian
- Identifiability analysis: parameter correlation structure

## Verification Criteria

### Knowledge Check
Students should derive likelihoods, implement MLE optimization, compute Fisher information, and assess identifiability

### Success Indicators
- Correctly derives likelihood for neuronal model
- Implements numerical optimization achieving convergence
- Computes Fisher information and confidence intervals
- Identifies non-identifiable parameter combinations

### Common Misconceptions
- Confusing likelihood with probability of parameters
- Assuming MLE is always unbiased (true only asymptotically)
- Neglecting local maxima in optimization
- Misinterpreting confidence intervals as Bayesian credible intervals
