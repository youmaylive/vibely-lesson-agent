# Mutual Information: Quantifying Neural Coding

## Key Insight
Mutual information measures how much knowing neuronal responses reduces uncertainty about stimuli, providing a universal, model-free metric for neural coding quality that accounts for both signal and noise.

## Learning Objectives
- Derive mutual information from entropy definitions
- Compute mutual information between stimuli and spike responses
- Estimate mutual information from limited data with bias correction
- Apply mutual information to analyze neural coding schemes

## Warmup (Callback)
Entropy (lesson_06_01) measures uncertainty; mutual information measures shared uncertainty between stimulus and response

## Content Outline
- Mutual information definition: I(X;Y) = H(Y) - H(Y|X) = H(X) + H(Y) - H(X,Y)
- Symmetry: I(X;Y) = I(Y;X)
- Bounds: 0 ≤ I(X;Y) ≤ min(H(X), H(Y))
- Continuous case: I(X;Y) = ∫∫ f(x,y)log₂(f(x,y)/(f_X(x)f_Y(y)))dxdy
- Estimation from data: histogram methods, kernel density estimation
- Bias correction: finite sample effects, Panzeri-Treves correction
- Application: stimulus-response mutual information in sensory neurons
- Information-theoretic bounds on coding capacity

## Key Concepts
- Mutual information
- Conditional entropy
- Information bottleneck
- Bias correction
- Coding capacity
- Stimulus-response relationship

## Practical Examples
- Mutual information calculation: Gaussian stimulus and response
- Spike count coding: I(stimulus; spike count)
- Temporal coding: I(stimulus; spike times)
- Bias correction demonstration: finite sample effects
- Comparing coding schemes: rate vs. temporal coding efficiency

## Verification Criteria

### Knowledge Check
Students should compute mutual information analytically and from data, apply bias corrections, and compare neural coding schemes

### Success Indicators
- Correctly computes mutual information for joint distributions
- Implements estimation from data with appropriate binning
- Applies bias correction methods effectively
- Interprets mutual information in terms of coding quality

### Common Misconceptions
- Assuming mutual information measures correlation (it's more general)
- Neglecting finite sample bias in estimation
- Confusing mutual information with channel capacity
- Misinterpreting I(X;Y) = 0 as independence without sufficient data
