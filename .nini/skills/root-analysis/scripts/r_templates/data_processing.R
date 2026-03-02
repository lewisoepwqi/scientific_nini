normalize_sample_names <- function(x) {
  x <- as.character(x)
  x <- dplyr::recode(
    x,
    "upox1-1" = "upox1_1",
    "upox1-2" = "upox1_2",
    "1cbk1-5" = "1cbk1_5",
    .default = x,
    .missing = x
  )
  x
}

read_and_process_data <- function(file_path) {
  data <- read_excel(file_path)
  data$sample <- normalize_sample_names(data$sample)
  data$sample <- factor(data$sample, levels = unique(data$sample))
  data$treatment <- factor(data$treatment, levels = unique(data$treatment))
  return(data)
}

calculate_summary_statistics <- function(data) {
  summary_stats <- data %>%
    group_by(treatment, sample) %>%
    summarise(
      n = n(),
      mean_length = mean(length, na.rm = TRUE),
      se = sd(length, na.rm = TRUE) / sqrt(n()),
      .groups = "drop"
    )
  return(summary_stats)
}

# 计算同一分组中相同样品的均值
calculate_group_means <- function(data) {
  group_means <- data %>%
    group_by(sample) %>%
    summarise(
      n = n(),
      mean_length = mean(length, na.rm = TRUE),
      se = sd(length, na.rm = TRUE) / sqrt(n()),
      .groups = "drop"
    )
  return(group_means)
}

# 计算比率（支持任意基线处理组）
calculate_ratios <- function(data, baseline_treatment = "Mock") {
  # 数据检查
  if(any(is.na(data$length))) {
    warning("数据中存在NA值，这可能影响比率计算")
    print("NA值位置：")
    print(which(is.na(data$length)))
  }

  # 检查基线处理组是否存在
  if (!baseline_treatment %in% unique(data$treatment)) {
    available_treatments <- unique(data$treatment)
    stop(paste0("基线处理组 '", baseline_treatment, "' 不存在。",
                "可用的处理组: ", paste(available_treatments, collapse = ", ")))
  }

  # 计算基线组每个样本的平均值
  baseline_means <- data %>%
    filter(treatment == baseline_treatment) %>%
    group_by(sample) %>%
    summarise(
      baseline_mean = mean(length, na.rm = TRUE),
      .groups = "drop"
    )

  # 获取所有非基线组的值并计算比率
  ratios <- data %>%
    filter(treatment != baseline_treatment) %>%
    select(sample, treatment, length) %>%
    # 与基线均值配对
    left_join(baseline_means, by = "sample") %>%
    # 计算比率
    mutate(ratio = length / baseline_mean)

  return(ratios)
}