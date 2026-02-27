# Customization Guide

This document explains how to customize color schemes, sample ordering, plot dimensions, and other advanced options for root length analysis.

## Color Schemes

The skill provides 5 pre-defined color schemes optimized for different use cases and sample sizes.

### 1. `high_contrast` ⭐ Recommended

**Colors**: 24 predefined + dynamic generation for larger sets

**Characteristics**:
- Maximum visual distinction between samples
- Carefully selected for colorblind accessibility
- Automatically extends for >24 samples using HSV color space

**Best for**:
- Publications and presentations
- Datasets with 5-24 samples
- When visual clarity is critical

**Preview**:
```
#E31A1C (red), #1F78B4 (blue), #33A02C (green), #6A3D9A (purple)
#FF7F00 (orange), #dede8b (yellow), #A65628 (brown), #F781BF (pink)
...
```

**Usage**:
```bash
--color-scheme high_contrast
```

---

### 2. `default`

**Colors**: 32 diverse colors

**Characteristics**:
- Wide variety of hues
- Good for very large sample sets
- Some colors may be visually similar

**Best for**:
- Datasets with >20 samples
- Exploratory analysis where sample count varies

**Usage**:
```bash
--color-scheme default
```

---

### 3. `blue`

**Colors**: 16 shades from light to dark blue

**Characteristics**:
- Sequential gradient
- Professional, cohesive appearance
- Lower contrast between adjacent samples

**Best for**:
- 5-16 samples
- Presentations with blue theme
- Emphasizing gradient/order rather than categorical differences

**Preview**:
```
#deebf7 (lightest) → #08306b (darkest)
```

**Usage**:
```bash
--color-scheme blue
```

---

### 4. `green`

**Colors**: 16 shades from light to dark green

**Characteristics**:
- Sequential gradient
- Natural, plant-themed aesthetic
- Lower contrast between adjacent samples

**Best for**:
- Plant biology presentations
- 5-16 samples
- Natural/organic visual themes

**Preview**:
```
#edf8e9 (lightest) → #00441b (darkest)
```

**Usage**:
```bash
--color-scheme green
```

---

### 5. `qualitative`

**Colors**: 16 balanced categorical colors (ColorBrewer Set1)

**Characteristics**:
- Balanced hue, saturation, lightness
- Designed for categorical data
- Good printer reproduction

**Best for**:
- Printed publications
- Colorblind-friendly presentations
- 5-16 samples with no natural order

**Usage**:
```bash
--color-scheme qualitative
```

---

## Sample Ordering

Sample order determines the **left-to-right** arrangement in plots.

### Automatic Ordering (Default)

**Rules**:
1. `Col_0` (wild type) appears first
2. Non-OE (over-expression) samples in alphabetical order
3. OE samples last, in alphabetical order

**Example**:
```
Input samples: Aox1a OE, upox1_1, Col_0, om66, UPOX1 OE

Automatic order:
  1. Col_0
  2. om66
  3. upox1_1
  4. Aox1a OE
  5. UPOX1 OE
```

**Usage**:
```bash
# Use automatic ordering (default)
python generate_r_project.py --data-file data.csv
# OR explicitly:
python generate_r_project.py --data-file data.csv --sample-order auto
```

---

### Custom Ordering

Specify exact sample order for complete control.

**Syntax**: Comma-separated list of sample names

**Example**:
```bash
python generate_r_project.py \
  --data-file data.csv \
  --sample-order "Col_0,mutant1,mutant2,OE1,OE2"
```

**Rendered in main.R**:
```r
preferred_order <- c("Col_0", "mutant1", "mutant2", "OE1", "OE2")
```

**Rules**:
- Sample names must match data **exactly** (case-sensitive)
- If you omit a sample, it will be **appended** at the end
- If you include a sample not in data, it will be **ignored**

**Example with missing sample**:
```
Custom order: Col_0, mutant1, mutant2
Samples in data: Col_0, mutant1, mutant2, mutant3

Final order: Col_0, mutant1, mutant2, mutant3  (mutant3 auto-appended)
```

---

### Editing Order After Generation

You can also manually edit `main.R`:

```r
# Find this section in main.R
preferred_order <- c(
  "Col_0",
  "mutant1",
  "mutant2"
)

# Change to your desired order:
preferred_order <- c(
  "mutant2",  # Now first
  "Col_0",
  "mutant1"
)
```

Then re-run: `Rscript main.R`

---

## Plot Dimensions

### Setting Dimensions

**Width and height** are specified in **inches** (standard for R graphics).

**Defaults**: 8 inches wide × 6 inches tall

**Usage**:
```bash
python generate_r_project.py \
  --data-file data.csv \
  --width 10 \
  --height 8
```

---

### Recommended Dimensions

| Use Case | Width | Height | Aspect Ratio |
|----------|-------|--------|--------------|
| **Default (general)** | 8 | 6 | 4:3 |
| **Presentation (16:9)** | 10 | 5.625 | 16:9 |
| **Publication (single column)** | 3.5 | 4.5 | Portrait |
| **Publication (double column)** | 7 | 5 | Landscape |
| **Poster** | 12 | 9 | 4:3 |
| **Square plots** | 6 | 6 | 1:1 |

---

### Adjusting After Generation

Edit `main.R`:

```r
# Find the ggsave() calls
ggsave("output/figures/root_length_plot.pdf", plot,
       width = 8, height = 6)  # Change these values

ggsave("output/figures/ratio_plot.pdf", ratio_plot,
       width = 8, height = 6)  # Change these too
```

**Resolution**: PDF output is vector-based (scales infinitely), so no need to adjust DPI.

---

## Output Directory

### Custom Output Location

**Default**: `output/` within project directory

**Change via command line**:
```bash
python generate_r_project.py \
  --data-file data.csv \
  --output-dir "results/experiment_2024"
```

This creates:
```
r_analysis_project/
  └── results/
      └── experiment_2024/
          ├── figures/
          │   ├── root_length_plot.pdf
          │   └── ratio_plot.pdf
          └── records/
              ├── sample_order.txt
              └── color_mapping.csv
```

---

### Editing Output Path in main.R

```r
# Change output directory
output_dir <- "custom_output"

dir.create(paste0(output_dir, "/figures"), recursive = TRUE)
ggsave(paste0(output_dir, "/figures/root_length_plot.pdf"), plot, ...)
```

---

## Font Sizes and Styling

Edit `R/plotting.R` in the `apply_plot_theme()` function:

```r
apply_plot_theme <- function() {
  theme(
    axis.text.x = element_text(angle = 45, hjust = 1, size = 12),  # X-axis labels
    axis.text.y = element_text(size = 12),                         # Y-axis numbers
    axis.title = element_text(size = 14),                          # Axis titles
    strip.text.x = element_text(size = 14)                         # Facet labels
  )
}
```

**Common adjustments**:

| Element | Parameter | Default | Large (poster) | Small (publication) |
|---------|-----------|---------|----------------|---------------------|
| Axis labels | `axis.text` | 12 | 18 | 8 |
| Axis titles | `axis.title` | 14 | 20 | 10 |
| Facet titles | `strip.text` | 14 | 20 | 10 |
| Legend text | `legend.text` | 12 | 18 | 8 |

---

## Advanced Customizations

### Adding a New Color Scheme

Edit `R/plotting.R` in the `create_color_maps()` function:

```r
color_schemes <- list(
  default = c(...),
  high_contrast = c(...),
  # ... other schemes ...

  # Add your custom scheme here
  my_custom = c(
    "#FF0000",  # Red
    "#00FF00",  # Green
    "#0000FF",  # Blue
    "#FFFF00",  # Yellow
    "#FF00FF",  # Magenta
    "#00FFFF"   # Cyan
    # Add more colors as needed
  )
)
```

**Usage**:
```r
# In main.R
color_maps <- create_color_maps(
  sample_names = actual_samples,
  color_scheme = "my_custom",  # Use your new scheme
  ordered_samples = preferred_order
)
```

---

### Changing Significance Level

**Default**: α = 0.05 (95% confidence)

To use **α = 0.01** (99% confidence, more stringent):

Edit `R/statistical_analysis.R`:

```r
# Change confidence level in TukeyHSD
tukey_result <- TukeyHSD(model, conf.level = 0.99)  # Instead of default 0.95
```

**Effect**: Fewer pairs will be marked as significantly different.

---

### Using Alternative Post-Hoc Tests

Replace Tukey HSD with other tests by editing `R/statistical_analysis.R`:

#### Bonferroni Correction
```r
# More conservative than Tukey
pairwise.t.test(data$length, data$sample,
                p.adjust.method = "bonferroni")
```

#### Dunnett's Test (compare to control only)
```r
library(multcomp)

# Compare all samples to Col_0 only
dunnett_result <- glht(model, linfct = mcp(sample = "Dunnett"))
summary(dunnett_result)
```

---

### Modifying Plot Aesthetics

Edit `R/plotting.R` in the `create_root_length_plot()` function:

#### Change Bar Transparency
```r
geom_col(..., alpha = 0.7)  # Default: 0.5 (range: 0-1)
```

#### Change Point Size
```r
geom_point(..., size = 2)  # Default: 1
```

#### Change Error Bar Width
```r
geom_errorbar(..., width = 0.3)  # Default: 0.2
```

#### Change Significance Letter Size
```r
geom_text(..., size = 8)  # Default: 6
```

#### Rotate X-Axis Labels
```r
theme(
  axis.text.x = element_text(angle = 90, hjust = 1)  # Vertical instead of 45°
)
```

---

### Changing Y-Axis Label

Edit `R/plotting.R`:

```r
# Root length plot
labs(x = "Sample", y = "Primary root length (cm)")  # Add detail

# Ratio plot
labs(x = NULL, y = "Relative root length (ISX/Mock)")
```

---

### Saving in Different Formats

By default, plots are saved as **PDF** (vector format, best for publications).

To save in other formats, edit `main.R`:

```r
# PNG (raster, good for presentations)
ggsave("output/figures/root_length_plot.png", plot,
       width = 8, height = 6, dpi = 300)

# TIFF (required by some journals)
ggsave("output/figures/root_length_plot.tiff", plot,
       width = 8, height = 6, dpi = 600, compression = "lzw")

# SVG (vector, web-friendly)
ggsave("output/figures/root_length_plot.svg", plot,
       width = 8, height = 6)
```

**DPI recommendations**:
- Screen/web: 150 dpi
- Print/publication: 300-600 dpi

---

## Special Case: Col_0 Color Override

The wild-type sample `Col_0` is **automatically assigned gray** (`#808080`) regardless of color scheme.

**Why?**: Standardization across experiments - wild type is always visually identifiable.

**To disable**:

Edit `R/plotting.R`, remove this section in `create_color_maps()`:

```r
# REMOVE OR COMMENT OUT:
# if ("Col_0" %in% names(color_maps$column)) {
#   color_maps$column["Col_0"] <- "#808080"
#   color_maps$point["Col_0"] <- "#808080"
# }
```

---

## Troubleshooting Customizations

### Color scheme not found

**Error**: `Color scheme 'xyz' not found, using default`

**Fix**: Check spelling and use one of: `default`, `high_contrast`, `blue`, `green`, `qualitative`

---

### Sample order ignored

**Issue**: Custom order doesn't match plot

**Fix**: Verify sample names match data exactly:
```r
# Check actual sample names
print(unique(data$sample))

# Compare to your preferred_order
```

---

### Plot elements cut off

**Issue**: Labels or text extend beyond plot boundaries

**Fix**: Increase plot dimensions or decrease font sizes

```r
# Increase width for long sample names
ggsave(..., width = 10, height = 6)

# OR reduce label font size
theme(axis.text.x = element_text(size = 10))  # Instead of 12
```

---

## Examples

### Example 1: Large Poster

```bash
python generate_r_project.py \
  --data-file data.csv \
  --color-scheme high_contrast \
  --width 16 \
  --height 12
```

Then edit `R/plotting.R`:
```r
apply_plot_theme <- function() {
  theme(
    axis.text.x = element_text(angle = 45, hjust = 1, size = 20),
    axis.text.y = element_text(size = 20),
    axis.title = element_text(size = 24),
    strip.text.x = element_text(size = 24)
  )
}
```

---

### Example 2: Publication-Ready

```bash
python generate_r_project.py \
  --data-file data.csv \
  --color-scheme qualitative \
  --width 3.5 \
  --height 4.5 \
  --sample-order "Col_0,mutant1,mutant2,mutant3"
```

Save as TIFF:
```r
ggsave("output/figures/root_length_plot.tiff", plot,
       width = 3.5, height = 4.5, dpi = 600, compression = "lzw")
```

---

### Example 3: Presentation Slide

```bash
python generate_r_project.py \
  --data-file data.csv \
  --color-scheme blue \
  --width 10 \
  --height 5.625  # 16:9 aspect ratio
```

Save as PNG:
```r
ggsave("output/figures/root_length_plot.png", plot,
       width = 10, height = 5.625, dpi = 150)
```

---

## Getting Help

For advanced customizations not covered here:

1. **R plotting**: See `ggplot2` documentation: https://ggplot2.tidyverse.org
2. **Color selection**: Use ColorBrewer: https://colorbrewer2.org
3. **Theme customization**: ggplot2 theme reference: https://ggplot2.tidyverse.org/reference/theme.html
