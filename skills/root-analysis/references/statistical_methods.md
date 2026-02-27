# Statistical Methods for Root Length Analysis

This document explains the statistical methods used in plant root length analysis, including one-way ANOVA, Tukey HSD post-hoc testing, and ratio analysis.

## One-Way ANOVA (Analysis of Variance)

### Purpose

ANOVA tests whether there are statistically significant differences in mean root length among different plant samples within each treatment group (Mock or ISX).

### Null and Alternative Hypotheses

- **Null Hypothesis (H₀)**: All samples have equal mean root lengths
- **Alternative Hypothesis (H₁)**: At least one sample has a different mean root length
- **Significance level**: α = 0.05 (standard in biological research)

### Assumptions

1. **Normality**: Data within each group should be approximately normally distributed
2. **Homogeneity of variance**: Variance should be similar across all groups
3. **Independence**: Measurements should be independent of each other

### R Implementation

```r
# Perform ANOVA for each treatment group separately
model_mock <- aov(length ~ sample, data = subset(data, treatment == "Mock"))
model_isx <- aov(length ~ sample, data = subset(data, treatment == "ISX"))

# View results
summary(model_mock)
summary(model_isx)
```

### Interpreting Results

**F-statistic**: Ratio of between-group variance to within-group variance
- Larger F values indicate greater differences between groups
- F = variance_between_groups / variance_within_groups

**p-value**: Probability of observing this F-statistic by chance
- **p < 0.05**: Reject H₀ → samples have significantly different means
- **p ≥ 0.05**: Fail to reject H₀ → no significant difference detected

**Example output**:
```
            Df Sum Sq Mean Sq F value   Pr(>F)
sample       8  45.23   5.654   12.43 < 0.001 ***
Residuals  216  98.32   0.455
---
Signif. codes:  0 '***' 0.001 '**' 0.01 '*' 0.05 '.' 0.1 ' ' 1
```

Interpretation: F(8,216) = 12.43, p < 0.001 indicates significant differences among samples.

---

## Tukey HSD Post-Hoc Test

### Purpose

When ANOVA detects significant differences, Tukey's Honestly Significant Difference (HSD) test identifies **which specific pairs** of samples differ significantly.

### Why Use Tukey HSD?

- **Controls family-wise error rate (FWER)**: Prevents inflated Type I error from multiple comparisons
- **All pairwise comparisons**: Tests every possible sample pair
- **Conservative but powerful**: Balances sensitivity and specificity

### R Implementation

```r
# Perform Tukey HSD on ANOVA model
tukey_result <- TukeyHSD(model_mock)

# Generate compact letter display
library(multcompView)
letters <- multcompLetters4(model_mock, tukey_result)$sample$Letters
```

### Understanding Significance Letters

Tukey HSD results are displayed as **letters** (a, b, c, etc.) for easy interpretation:

**Rule**:
- Groups sharing at least one letter → **no significant difference**
- Groups with no shared letters → **significant difference**

**Example 1: Simple Case**
```
Col_0:    a
mutant1:  b
mutant2:  c
```
- Col_0 vs mutant1: **Significant** (no shared letters)
- Col_0 vs mutant2: **Significant** (no shared letters)
- mutant1 vs mutant2: **Significant** (no shared letters)

**Example 2: Overlapping Groups**
```
Col_0:    a
mutant1:  ab
mutant2:  b
mutant3:  c
```
- Col_0 vs mutant1: **Not significant** (share "a")
- mutant1 vs mutant2: **Not significant** (share "b")
- Col_0 vs mutant2: **Not significant** (connected through mutant1)
- Col_0 vs mutant3: **Significant** (no connection)
- mutant2 vs mutant3: **Significant** (no shared letters)

**Example 3: Complex Pattern**
```
Sample A: a
Sample B: ab
Sample C: abc
Sample D: bc
Sample E: c
```

This indicates a gradient:
- A and E are significantly different (no shared letters)
- A, B, C form a continuum with no sharp boundaries
- C, D, E form another continuum

### Reading Tukey Output Directly

```r
print(tukey_result)

#   Tukey multiple comparisons of means
#     95% family-wise confidence level
#
# $sample
#                       diff        lwr        upr     p adj
# mutant1-Col_0   -1.2345678 -1.8234567 -0.6456789 0.000123
# mutant2-Col_0    0.1234567 -0.4654321  0.7123456 0.892345
# mutant2-mutant1  1.3580246  0.7691357  1.9469135 0.000012
```

- **diff**: Mean difference between groups
- **lwr, upr**: 95% confidence interval bounds
- **p adj**: Adjusted p-value (accounts for multiple comparisons)

If **p adj < 0.05** → significant difference

---

## ISX/Mock Ratio Analysis

### Purpose

Ratio analysis normalizes treatment effects relative to baseline (Mock), allowing comparison of **relative responses** to ISX treatment across samples.

### Calculation Method

For each ISX measurement:
```
Ratio = (Individual ISX length) / (Mean Mock length for that sample)
```

**Example**:
```
Sample: Col_0
Mock lengths: [5.2, 5.4, 5.1, 5.3, 5.0]  → Mean = 5.2
ISX lengths: [4.1, 4.3, 4.2, 4.0, 4.4]

Ratios:
  4.1 / 5.2 = 0.788
  4.3 / 5.2 = 0.827
  4.2 / 5.2 = 0.808
  ...
```

### Statistical Analysis of Ratios

After calculating ratios, perform ANOVA and Tukey HSD:

```r
# ANOVA on ratios
ratio_model <- aov(ratio ~ sample, data = ratios)
summary(ratio_model)

# Tukey HSD for ratio differences
ratio_tukey <- TukeyHSD(ratio_model)
ratio_letters <- multcompLetters4(ratio_model, ratio_tukey)$sample$Letters
```

### Biological Interpretation

**Ratio > 1.0**: ISX treatment **increases** root length
- Example: Ratio = 1.25 → 25% increase

**Ratio = 1.0**: ISX has **no effect** on root length
- Null effect

**Ratio < 1.0**: ISX treatment **decreases** root length
- Example: Ratio = 0.75 → 25% decrease

**Significant differences in ratios** indicate:
- Different genotypes respond differently to ISX
- Some samples may be resistant/sensitive to treatment
- Genetic variation affects ISX response

### Advantages of Ratio Analysis

1. **Normalizes baseline differences**: Removes inherent size variation between samples
2. **Highlights treatment effects**: Focuses on relative change, not absolute values
3. **Direct comparability**: All samples on same scale (ratio to Mock)
4. **Identifies phenotypes**: Easily spots resistant (ratio ≈ 1) vs sensitive (ratio << 1) genotypes

---

## When to Use Each Analysis

| Analysis | Question Answered | Use Case |
|----------|------------------|----------|
| **ANOVA (Mock)** | Do samples differ in baseline root length? | Characterize natural variation |
| **ANOVA (ISX)** | Do samples differ under treatment? | Identify treatment-responsive genotypes |
| **Ratio Analysis** | Which samples respond most/least to ISX? | Find resistant/sensitive lines |

---

## Common Questions

**Q: What if ANOVA is not significant (p > 0.05)?**

A: No significant differences detected. Either:
- Samples truly have similar means
- Sample size is too small (insufficient power)
- High variance masks true differences

Do **not** proceed with Tukey HSD if ANOVA is non-significant.

**Q: Can I use t-tests instead of ANOVA?**

A: Not recommended for >2 groups. Multiple t-tests inflate Type I error (false positives). ANOVA + Tukey HSD properly controls error rate.

**Q: What if assumptions are violated?**

A: Consider:
- **Non-parametric alternative**: Kruskal-Wallis test + Dunn's test
- **Transformation**: Log or square-root transform data
- **Check outliers**: Verify data quality

**Q: How many replicates do I need?**

A: Minimum 3 per sample×treatment group. Ideally 5-10 for robust estimates and good statistical power.

---

## References

- Maxwell, S. E., & Delaney, H. D. (2004). *Designing Experiments and Analyzing Data: A Model Comparison Perspective*. Psychology Press.
- Tukey, J. W. (1949). Comparing individual means in the analysis of variance. *Biometrics*, 5(2), 99-114.
- Kozak, M., & Piepho, H. P. (2018). What's normal anyway? Residual plots are more telling than significance tests when checking ANOVA assumptions. *Journal of Agronomy and Crop Science*, 204(1), 86-98.
