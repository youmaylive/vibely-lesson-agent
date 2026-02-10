# Bayesian Inference with Jeffreys Priors

## Key Insight
Bayesian inference combines prior knowledge with data through Bayes' theorem, with Jeffreys priors derived from Fisher information providing optimal non-informative priors that are invariant under reparameterization.

## Learning Objectives
- Apply Bayes' theorem to parameter estimation
- Derive Jeffreys priors from Fisher information
- Implement Markov Chain Monte Carlo (MCMC) for posterior sampling
- Compare Bayesian and frequentist approaches

## Warmup (Callback)
MLE (lesson_08_01) finds point estimates; Bayesian inference provides full posterior distributions

## Content Outline
- Bayes' theorem: P(θ|data) ∝ P(data|θ)P(θ)
- Prior distribution P(θ): encoding prior knowledge
- Jeffreys prior: P(θ) ∝ √det(I(θ)), reparameterization invariant
- Posterior distribution: combining prior and likelihood
- Posterior mean, median, mode as point estimates
- Credible intervals: Bayesian uncertainty quantification
- MCMC methods: Metropolis-Hastings, Hamiltonian Monte Carlo
- Model comparison: Bayes factors, DIC, WAIC

## Key Concepts
- Bayes' theorem
- Prior distribution
- Jeffreys prior
- Posterior distribution
- Credible interval
- MCMC

## Practical Examples
- Jeffreys prior derivation for Gaussian parameters
- Bayesian inference for IF model: MCMC sampling
- Posterior visualization: marginal distributions and correlations
- Credible interval computation: highest posterior density
- Model comparison: comparing IF vs. FHN using Bayes factors

## Verification Criteria

### Knowledge Check
Students should derive Jeffreys priors, implement MCMC, and perform Bayesian model comparison

### Success Indicators
- Correctly derives Jeffreys prior from Fisher information
- Implements MCMC achieving convergence (Gelman-Rubin diagnostic)
- Computes credible intervals from posterior samples
- Performs model comparison using appropriate metrics

### Common Misconceptions
- Confusing credible intervals with confidence intervals
- Assuming Jeffreys prior is always appropriate
- Neglecting MCMC convergence diagnostics
- Misinterpreting Bayes factors as posterior probabilities
