# Data Format Requirements

This document specifies the required format for root length data files and provides examples of valid and invalid data.

## Required Columns

Your data file **must** contain exactly these three columns with these exact names (case-sensitive):

### 1. `sample`

**Type**: Text (character or factor)

**Description**: Plant sample or genotype identifier

**Examples**:
- Wild type: `Col_0`, `WT`, `wild-type`
- Mutants: `mutant1`, `upox1_1`, `1cbk1_5`
- Overexpression lines: `Aox1a OE`, `UPOX1 OE`

**Requirements**:
- Must be spelled **consistently** throughout the file
- Case-sensitive: `mutant1` ≠ `Mutant1`
- Avoid special characters except: underscore `_`, hyphen `-`, space ` `

### 2. `treatment`

**Type**: Text (character or factor)

**Description**: Experimental treatment group

**Requirements**:
- **Must include** `Mock` (control group) - case-sensitive!
- Common treatment: `ISX` (or your chemical/condition name)
- Can have 2+ treatments, but `Mock` is mandatory

**Examples**:
- ✅ Valid: `Mock`, `ISX`
- ✅ Valid: `Mock`, `Treatment1`, `Treatment2`
- ❌ Invalid: `mock` (lowercase), `Control` (should be "Mock")

### 3. `length`

**Type**: Numeric (numbers only)

**Description**: Root length measurement

**Units**: Centimeters (cm) or millimeters (mm) - be consistent!

**Requirements**:
- Must be numeric values only
- Decimal numbers allowed: `5.23`
- Missing values: Use blank or `NA` (will be excluded from analysis)

**Examples**:
- ✅ Valid: `5.2`, `4.753`, `3.0`, `NA`
- ❌ Invalid: `5.2 cm`, `not measured`, `~5`

---

## Supported File Formats

### CSV (Recommended)

```csv
sample,treatment,length
Col_0,Mock,5.2
Col_0,Mock,5.4
Col_0,ISX,4.1
mutant1,Mock,3.8
mutant1,ISX,5.2
```

**Advantages**:
- Universal compatibility
- Easy to edit in Excel, Google Sheets, or text editors
- Small file size

### Excel (.xlsx or .xls)

| sample | treatment | length |
|--------|-----------|--------|
| Col_0  | Mock      | 5.2    |
| Col_0  | Mock      | 5.4    |
| Col_0  | ISX       | 4.1    |

**Note**: Only the first sheet will be read

---

## Data Structure Requirements

### Replication

**Minimum**: 3 biological replicates per sample×treatment combination

**Recommended**: 5-10 replicates for robust statistics

**Example** (3 replicates):
```csv
sample,treatment,length
Col_0,Mock,5.2
Col_0,Mock,5.3
Col_0,Mock,5.1
Col_0,ISX,4.1
Col_0,ISX,4.2
Col_0,ISX,4.0
```

### Complete Design

Every sample should appear in **both** Mock and treatment groups.

**Example** (incomplete - will work but suboptimal):
```csv
sample,treatment,length
Col_0,Mock,5.2
Col_0,ISX,4.1
mutant1,Mock,3.8
# Missing: mutant1 ISX data
```

⚠️ **Warning**: Missing combinations reduce analysis power

---

## Valid Data Examples

### Example 1: Minimal Valid Dataset

```csv
sample,treatment,length
WT,Mock,5.2
WT,Mock,5.4
WT,Mock,5.1
WT,ISX,4.1
WT,ISX,4.3
WT,ISX,4.2
mutant,Mock,3.8
mutant,Mock,4.0
mutant,Mock,3.9
mutant,ISX,5.1
mutant,ISX,5.3
mutant,ISX,5.2
```

**Valid because**:
- ✅ Has `sample`, `treatment`, `length` columns
- ✅ Contains `Mock` group
- ✅ All lengths are numeric
- ✅ 3 replicates per group

### Example 2: Multiple Samples

```csv
sample,treatment,length
Col_0,Mock,5.2
Col_0,Mock,5.4
Col_0,Mock,5.1
Col_0,ISX,4.1
Col_0,ISX,4.3
Aox1a OE,Mock,4.5
Aox1a OE,Mock,4.7
Aox1a OE,ISX,5.0
Aox1a OE,ISX,5.2
upox1_1,Mock,3.8
upox1_1,Mock,4.0
upox1_1,ISX,4.9
upox1_1,ISX,5.1
```

### Example 3: With Missing Values

```csv
sample,treatment,length
Col_0,Mock,5.2
Col_0,Mock,NA
Col_0,Mock,5.1
Col_0,ISX,4.1
Col_0,ISX,4.3
mutant,Mock,3.8
mutant,Mock,4.0
mutant,ISX,
mutant,ISX,5.2
```

**Valid**: NA values are automatically excluded. Blank cells treated as NA.

---

## Common Errors and Fixes

### Error 1: Wrong Column Names

❌ **Invalid**:
```csv
Sample_Name,Treatment_Group,Root_Length
Col_0,Mock,5.2
```

✅ **Fixed**:
```csv
sample,treatment,length
Col_0,Mock,5.2
```

**Solution**: Rename columns to exactly `sample`, `treatment`, `length` (all lowercase)

---

### Error 2: Missing Mock Group

❌ **Invalid**:
```csv
sample,treatment,length
Col_0,control,5.2
Col_0,ISX,4.1
```

✅ **Fixed**:
```csv
sample,treatment,length
Col_0,Mock,5.2
Col_0,ISX,4.1
```

**Solution**: Rename control group to `Mock` (capital M)

---

### Error 3: Inconsistent Sample Names

❌ **Invalid**:
```csv
sample,treatment,length
upox1-1,Mock,5.2
upox1_1,ISX,4.1
```

These will be treated as **two different samples**!

✅ **Fixed** (choose one naming style):
```csv
sample,treatment,length
upox1_1,Mock,5.2
upox1_1,ISX,4.1
```

**Solution**: Use Find & Replace to standardize names

---

### Error 4: Non-Numeric Length Values

❌ **Invalid**:
```csv
sample,treatment,length
Col_0,Mock,5.2 cm
Col_0,ISX,not measured
mutant,Mock,~4
```

✅ **Fixed**:
```csv
sample,treatment,length
Col_0,Mock,5.2
Col_0,ISX,NA
mutant,Mock,4.0
```

**Solution**: Remove units, use NA for missing data, estimate ranges as single values

---

### Error 5: Extra Columns

✅ **Valid** (extra columns are OK):
```csv
sample,treatment,length,date,researcher,notes
Col_0,Mock,5.2,2024-01-15,John,good quality
Col_0,ISX,4.1,2024-01-15,John,
```

**Note**: Extra columns are ignored - only `sample`, `treatment`, `length` are used

---

## Data Validation Checklist

Before analysis, verify:

- [ ] File is `.csv`, `.xlsx`, or `.xls` format
- [ ] Columns named exactly: `sample`, `treatment`, `length`
- [ ] `treatment` column contains `Mock` (case-sensitive)
- [ ] `length` column contains only numbers (or NA)
- [ ] Each sample×treatment group has ≥3 measurements
- [ ] Sample names are spelled consistently
- [ ] No typos in treatment names

---

## Data Preparation Tips

### 1. Use Consistent Units

Choose cm or mm and stick to it:
```csv
# Good: All in cm
Col_0,Mock,5.2
mutant,Mock,3.8

# Bad: Mixed units
Col_0,Mock,52    # mm
mutant,Mock,3.8  # cm
```

### 2. Randomize Measurement Order

Measure samples in random order to avoid systematic bias:
- Not: All Mock first, then all ISX
- Better: Randomized sample × treatment order

### 3. Record Metadata Separately

Store experimental conditions in a separate file:
```csv
# metadata.csv
experiment_date,growth_conditions,ISX_concentration
2024-01-15,22°C 16h light,10 µM
```

Keep raw data clean - only `sample`, `treatment`, `length` in the analysis file.

### 4. Backup Original Data

Always keep an unmodified copy before any cleanup or analysis.

### 5. Check for Outliers Visually

Plot your data first:
```r
boxplot(length ~ sample, data = data)
```

Identify and investigate extreme values before analysis.

---

## Example Dataset

A complete example dataset is provided with this skill at:
```
assets/example_data.csv
```

This dataset contains:
- 3 samples (Col_0, mutant1, mutant2)
- 2 treatments (Mock, ISX)
- 5 replicates each (30 total measurements)

Use it to test the analysis workflow.

---

## Getting Help

If you encounter data format issues:

1. **Use the validation tool**:
   ```bash
   python scripts/validate_data.py your_data.csv
   ```

   This will identify specific problems and suggest fixes.

2. **Check error messages**: Look for clues about which column or value is problematic

3. **Compare to example data**: Open `assets/example_data.csv` to see correct format

4. **Common fix**: Export your data as CSV and verify column names match exactly
