# Model Selection and Validation

## Key Insight
Selecting among competing neuronal models requires balancing goodness-of-fit with complexity, using information criteria (AIC, BIC) and cross-validation to avoid overfitting while ensuring predictive power on new data.

## Learning Objectives
- Apply information criteria (AIC, BIC, DIC) for model selection
- Implement cross-validation for predictive performance assessment
- Perform residual analysis to diagnose model inadequacies
- Use posterior predictive checks for Bayesian model validation

## Warmup (Callback)
Parameter estimation (lessons 08_01-02) fits models; now assess which model is best

## Content Outline
- Bias-variance tradeoff: underfitting vs. overfitting
- Akaike Information Criterion: AIC = -2ℓ(θ̂) + 2k
- Bayesian Information Criterion: BIC = -2ℓ(θ̂) + k log(n)
- Cross-validation: k-fold, leave-one-out
- Residual analysis: checking model assumptions
- Posterior predictive checks: P(y_rep|data)
- Goodness-of-fit tests: Kolmogorov-Smirnov, chi-square
- Practical considerations: computational cost, interpretability

## Key Concepts
- Model selection
- AIC/BIC
- Cross-validation
- Overfitting
- Residual analysis
- Posterior predictive check

## Practical Examples
- AIC/BIC comparison: IF vs. FHN vs. HH models
- Cross-validation: predicting held-out spike trains
- Residual analysis: checking for autocorrelation and heteroscedasticity
- Posterior predictive checks: comparing simulated to observed data
- Practical model selection: balancing accuracy and interpretability

## Verification Criteria

### Knowledge Check
Students should compute information criteria, perform cross-validation, and conduct model validation

### Success Indicators
- Correctly computes AIC/BIC for competing models
- Implements cross-validation with proper data splitting
- Performs residual analysis identifying model deficiencies
- Conducts posterior predictive checks validating model

### Common Misconceptions
- Assuming lower AIC/BIC always means better model
- Neglecting to validate on held-out data
- Confusing in-sample fit with out-of-sample prediction
- Misinterpreting residual patterns without statistical tests
