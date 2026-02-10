# Shannon Information and Entropy

## Key Insight
Shannon's framework quantifies information as reduction in uncertainty, providing fundamental limits on neural coding capacity and revealing that rare, surprising events carry more information than common ones.

## Learning Objectives
- Define Shannon information and entropy rigorously
- Compute entropy for discrete and continuous distributions
- Apply maximum entropy principle to neural coding
- Relate entropy to neural coding efficiency and capacity

## Warmup (Callback)
Stochastic processes (module_03) generate random spike trains; information theory quantifies their information content

## Content Outline
- Shannon information: S(A) = -log₂(P(A)) bits
- Entropy: H(X) = -Σ_x P(x)log₂(P(x)) for discrete X
- Differential entropy: h(X) = -∫ f(x)log₂(f(x))dx for continuous X
- Maximum entropy principle: least biased distribution given constraints
- Joint entropy: H(X,Y) and conditional entropy: H(Y|X)
- Chain rule: H(X,Y) = H(X) + H(Y|X)
- Application to spike trains: entropy rate of point processes
- Coding efficiency: actual vs. maximum possible entropy

## Key Concepts
- Shannon information
- Entropy
- Differential entropy
- Maximum entropy principle
- Conditional entropy
- Entropy rate

## Practical Examples
- Entropy calculation for Bernoulli spike train
- Maximum entropy distribution: Gaussian with fixed variance
- Spike train entropy rate estimation from data
- Comparing entropy of regular vs. irregular firing
- Coding efficiency: entropy relative to theoretical maximum

## Verification Criteria

### Knowledge Check
Students should compute entropy for various distributions, apply maximum entropy principle, and estimate entropy from neural data

### Success Indicators
- Correctly computes entropy for discrete and continuous distributions
- Derives maximum entropy distributions under constraints
- Estimates entropy rate from spike train data
- Interprets entropy in terms of coding capacity

### Common Misconceptions
- Confusing Shannon information with Fisher information
- Assuming differential entropy is always positive
- Neglecting units: bits vs. nats
- Misapplying discrete entropy formulas to continuous variables
