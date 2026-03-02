create_color_maps <- function(sample_names, color_scheme = "high_contrast", ordered_samples = NULL) {
  # 确保sample_names为字符类型，避免因子处理问题
  if (is.factor(sample_names)) {
    sample_names <- as.character(sample_names)
  }
  
  # 定义扩展的颜色方案，包含更多视觉上可区分的颜色
  color_schemes <- list(
    default = c(
      # 原有的12种颜色
      "#808080", "#8fb79d", "#dd3125", "#92bee1", 
      "#4c74b1", "#fc8c5a", "#6BAED6", "#969696",
      "#7f432a", "#a6cee3", "#1f78b4", "#b2df8a",
      # 新增的20种颜色，确保视觉区分度
      "#e31a1c", "#ff7f00", "#ff6b6b", "#33a02c",
      "#6a3d9a", "#b15928", "#4ecdc4", "#fdbf6f",
      "#45b7d1", "#cab2d6", "#ffff99", "#fb9a99",
      "#d62728", "#ff9800", "#2196f3", "#4caf50",
      "#9c27b0", "#795548", "#607d8b", "#e91e63",
      "#009688", "#cddc39", "#ffc107", "#673ab7",
      "#3f51b5", "#00bcd4", "#8bc34a", "#ff5722",
      "#9e9e9e", "#f44336", "#96ceb4", "#feca57"
    ),
    
    blue = c("#deebf7", "#c6dbef", "#9ecae1", "#6baed6",
             "#4292c6", "#2171b5", "#08519c", "#08306b",
             "#1e3a8a", "#1e40af", "#2563eb", "#3b82f6",
             "#60a5fa", "#93c5fd", "#bfdbfe", "#dbeafe"),
    
    green = c("#edf8e9", "#c7e9c0", "#a1d99b", "#74c476",
              "#41ab5d", "#238b45", "#006d2c", "#00441b",
              "#064e3b", "#065f46", "#047857", "#059669",
              "#10b981", "#34d399", "#6ee7b7", "#a7f3d0"),
    
    qualitative = c("#e41a1c", "#377eb8", "#4daf4a", "#984ea3",
                    "#ff7f00", "#ffff33", "#a65628", "#f781bf",
                    "#999999", "#66c2a5", "#fc8d62", "#8da0cb",
                    "#e78ac3", "#a6d854", "#ffd92f", "#e5c494"),
    
    # 高视觉区分度色彩方案 - 专为样本区分设计
    high_contrast = c("#E31A1C", "#1F78B4", "#33A02C", "#6A3D9A", 
                      "#FF7F00", "#dede8b", "#A65628", "#F781BF",
                      "#00CED1", "#006400", "#4B0082", "#FF4500",
                      "#DC143C", "#4169E1", "#228B22", "#8A2BE2",
                      "#FF8C00", "#FFD700", "#8B4513", "#FF1493",
                      "#0080ff", "#32CD32", "#9400D3", "#FF6347")
  )
  
  # 选择颜色方案 - 默认使用高区分度方案
  column_colors <- color_schemes[[color_scheme]] %||% color_schemes[["high_contrast"]]
  
  if (is.null(ordered_samples)) {
    col0_samples <- sample_names[sample_names == "Col_0"]
    oe_samples <- grep("OE", sample_names, value = TRUE)
    other_samples <- setdiff(sample_names, c(col0_samples, oe_samples))
    ordered_samples <- c(col0_samples, sort(other_samples), sort(oe_samples))
  } else {
    if (is.factor(ordered_samples)) {
      ordered_samples <- as.character(ordered_samples)
    }
    ordered_samples <- unique(ordered_samples)
    ordered_samples <- ordered_samples[ordered_samples %in% sample_names]
    missing <- setdiff(sample_names, ordered_samples)
    if (length(missing) > 0) {
      ordered_samples <- c(ordered_samples, missing)
    }
  }
  
  # 确保颜色数量足够 - 如果样本数量仍然超过颜色数量，生成额外的颜色
  if (length(ordered_samples) > length(column_colors)) {
    # 使用HSV颜色空间生成额外的颜色
    additional_colors_needed <- length(ordered_samples) - length(column_colors)
    
    # 生成均匀分布的色相值
    hue_values <- seq(0, 1, length.out = additional_colors_needed + 1)[1:additional_colors_needed]
    
    # 生成额外的颜色，使用不同的饱和度和明度确保区分度
    additional_colors <- hsv(h = hue_values, 
                           s = rep(c(0.8, 0.6, 0.9), length.out = additional_colors_needed),
                           v = rep(c(0.8, 0.9, 0.7), length.out = additional_colors_needed))
    
    # 合并颜色
    column_colors <- c(column_colors, additional_colors)
    
    cat("已为", length(ordered_samples), "个样本生成", length(column_colors), "种独特颜色\n")
  } else {
    cat("使用预定义颜色为", length(ordered_samples), "个样本分配颜色\n")
  }
  
  color_maps <- list(
    column = setNames(column_colors[1:length(ordered_samples)], ordered_samples),
    point = setNames(column_colors[1:length(ordered_samples)], ordered_samples)
  )
  
  # 强制确保Col_0获得灰色 (#808080) - 修复颜色分配问题
  if ("Col_0" %in% names(color_maps$column)) {
    cat("=== Col_0颜色强制修复 ===\n")
    cat("修复前Col_0颜色:", color_maps$column["Col_0"], "\n")
    
    # 强制设置Col_0为灰色
    color_maps$column["Col_0"] <- "#808080"
    color_maps$point["Col_0"] <- "#808080"
    
    cat("修复后Col_0颜色:", color_maps$column["Col_0"], "\n")
    cat("=== 修复完成 ===\n")
  } else {
    cat("警告：在样本中未找到Col_0\n")
  }
  
  # 打印详细调试信息
  cat("\n=== 详细调试信息 ===\n")
  cat("样本总数:", length(ordered_samples), "\n")
  cat("颜色总数:", length(column_colors), "\n")
  print("样本顺序：")
  print(ordered_samples)
  print("颜色映射（column）：")
  print(color_maps$column)
  
  # 特别检查Col_0的颜色分配
  if ("Col_0" %in% names(color_maps$column)) {
    cat("\n=== Col_0颜色验证 ===\n")
    cat("Col_0分配的颜色:", color_maps$column["Col_0"], "\n")
    cat("是否为灰色(#808080):", color_maps$column["Col_0"] == "#808080", "\n")
  }
  
  return(color_maps)
}

create_root_length_plot <- function(data, summary_stats, color_maps) {
  # 动态排序treatment：Mock优先（如果存在），其他按字母顺序
  all_treatments <- unique(c(as.character(data$treatment), as.character(summary_stats$treatment)))
  if ("Mock" %in% all_treatments) {
    treatment_order <- c("Mock", sort(setdiff(all_treatments, "Mock")))
  } else {
    treatment_order <- sort(all_treatments)
  }
  data$treatment <- factor(data$treatment, levels = treatment_order)
  summary_stats$treatment <- factor(summary_stats$treatment, levels = treatment_order)
  
  # 确保样本顺序与颜色映射一致
  data$sample <- factor(data$sample, levels = names(color_maps$column))
  summary_stats$sample <- factor(summary_stats$sample, levels = names(color_maps$column))
  
  # 计算每个treatment和sample组合的最大值位置
  sample_max_positions <- data %>%
    group_by(treatment, sample) %>%
    summarise(
      max_value = max(length),
      .groups = "drop"
    )
  
  # 合并最大值位置到summary_stats
  summary_stats <- summary_stats %>%
    left_join(sample_max_positions, by = c("treatment", "sample")) %>%
    mutate(
      letter_y_pos = pmax(max_value, mean_length + se) * 1.1  # 使用每个分组的最大值
    )
  
  # 计算整体y轴范围
  y_max <- max(summary_stats$letter_y_pos) * 1.1
  
  # 计算x轴范围
  n_samples <- length(unique(data$sample))
  x_min <- 0.5
  x_max <- n_samples + 0.5
  
  ggplot() +
    # 添加均值柱状图
    geom_col(data = summary_stats, 
             aes(x = sample, y = mean_length, fill = sample, color = sample),
             linewidth = 0.8,  # 修改: 使用 linewidth 替代 size
             alpha = 0.5, 
             width = 0.7) +
    
    # 添加原始数据散点
    geom_point(data = data,
               aes(x = sample, y = length, color = sample),
               position = position_jitter(width = 0.2),
               alpha = 0.9, 
               size = 1) +
    
    # 添加误差线和其他图形元素
    geom_errorbar(data = summary_stats,
                  aes(x = sample,
                      ymin = mean_length - se,
                      ymax = mean_length + se),
                  width = 0.2) +
    
    # 添加显著性字母标记
    geom_text(data = summary_stats,
              aes(x = sample,
                  y = letter_y_pos),  # 使用每个样本的独立位置
              label = summary_stats$letter,
              size = 6,
              vjust = -0.5) +
    
    # 设置主题和样式
    theme_classic() +
    labs(x = "Sample", y = "Root length (cm)") +
    apply_plot_theme() +
    
    # 设置颜色 - 使用传入的颜色映射
    scale_fill_manual(values = color_maps$column) +
    scale_color_manual(values = color_maps$point) +
    
    # 分面
    facet_wrap(~ treatment) +
    
    # 控制Y轴范围和扩展
    scale_y_continuous(
      limits = c(0, y_max),
      expand = expansion(mult = c(0, 0))
    ) +
    
    # 控制X轴扩展
    scale_x_discrete(
      expand = expansion(mult = c(0.2, 0.05))
    ) +
    
    # 修改坐标系
    coord_cartesian(
      xlim = c(x_min, x_max),
      clip = "off",
      expand = FALSE
    ) +
    
    # 添加主题调整确保轴线完整显示
    theme(
      axis.line = element_line(linewidth = 0.5, colour = "black"),
      panel.grid.major = element_blank(),
      panel.grid.minor = element_blank(),
      panel.border = element_blank(),
      panel.background = element_blank()
    )
}

apply_plot_theme <- function() {
  theme(
    axis.text.x = element_text(angle = 45, hjust = 1, size = 12),
    axis.text.y = element_text(size = 12),
    axis.title = element_text(size = 14),
    plot.title = element_text(hjust = 0.5, vjust = 1),
    legend.position = "none",
    legend.text = element_text(size = 12, face = "plain"),
    legend.title = element_text(size = 14, face = "bold"),
    strip.text.x = element_text(size = 14)
  )
}


# 创建比率图
create_ratio_plot <- function(ratios_data, ratio_letters) {
  # 准备数据
  ratio_summary <- ratios_data %>%
    filter(treatment != "Mock") %>%  # 移除Mock组
    group_by(sample) %>%
    summarise(
      mean_ratio = mean(ratio, na.rm = TRUE),
      se = sd(ratio, na.rm = TRUE) / sqrt(n()),
      .groups = "drop"
    ) %>%
    left_join(ratio_letters, by = "sample")
  
  # 设置颜色
  sample_colors <- c("#ffde91", "#8fb79d", "#dd3125")
  names(sample_colors) <- unique(ratios_data$sample)
  
  # 创建图形
  y_max <- max(ratio_summary$mean_ratio + ratio_summary$se) + 0.2
  
  plot <- ggplot() +
    # 添加柱状图
    geom_col(data = ratio_summary,
             aes(x = sample, y = mean_ratio, fill = sample),
             alpha = 0.5,
             width = 0.7) +
    
    # 添加误差线
    geom_errorbar(data = ratio_summary,
                  aes(x = sample,
                      ymin = mean_ratio - se,
                      ymax = mean_ratio + se),
                  width = 0.2) +
    
    # 添加显著性字母
    geom_text(data = ratio_summary,
              aes(x = sample,
                  y = mean_ratio + se + 0.1,
                  label = letter),
              size = 6) +
    
    # 设置主题和标签
    theme_classic() +
    labs(x = "Sample",
         y = "Relative root length (treatment/mock)") +
    
    # 设置颜色
    scale_fill_manual(values = sample_colors) +
    
    # 控制坐标轴
    scale_y_continuous(
      limits = c(0, y_max),
      expand = c(0, 0)
    ) +
    
    theme(
      axis.text.x = element_text(angle = 45, hjust = 1, size = 12),
      axis.text.y = element_text(size = 12),
      axis.title = element_text(size = 14),
      legend.position = "none"
    )
  
  return(plot)
}

create_ratio_plot_with_points <- function(ratios_data, letters_df, color_maps) {
  # 打印调试信息
  print("原始样本顺序：")
  print(unique(ratios_data$sample))
  print("颜色映射中的样本顺序：")
  print(names(color_maps$column))
  
  # 确保样本顺序与颜色映射一致
  ratios_data$sample <- factor(ratios_data$sample, levels = names(color_maps$column))
  
  # 打印转换后的顺序
  print("转换为因子后的样本顺序：")
  print(levels(ratios_data$sample))
  
  # 计算统计摘要
  summary_stats <- ratios_data %>%
    group_by(sample) %>%
    summarise(
      mean_ratio = mean(ratio, na.rm = TRUE),
      se = sd(ratio, na.rm = TRUE) / sqrt(n()),
      max_value = max(ratio),
      .groups = "drop"
    ) %>%
    left_join(letters_df, by = "sample") %>%
    mutate(
      letter_y_pos = pmax(max_value, mean_ratio + se) * 1.1,
      # 重要：确保保持正确的顺序
      sample = factor(sample, levels = names(color_maps$column))
    )
  
  # 打印最终的统计数据顺序
  print("统计数据中的样本顺序：")
  print(levels(summary_stats$sample))
  
  # 计算整体y轴范围
  y_max <- max(summary_stats$letter_y_pos) * 1.1
  
  # 计算x轴范围
  n_samples <- length(unique(ratios_data$sample))
  x_min <- 0.5
  x_max <- n_samples + 0.5
  
  ggplot() +
    # 添加柱状图
    geom_col(data = summary_stats,
             aes(x = sample, y = mean_ratio, fill = sample, color = sample),
             linewidth = 0.8,
             alpha = 0.5,
             width = 0.7) +
    
    # 添加散点
    geom_point(data = ratios_data,
               aes(x = sample, y = ratio, color = sample),
               position = position_jitter(width = 0.2),
               alpha = 0.9,
               size = 2) +
    
    # 添加误差线
    geom_errorbar(data = summary_stats,
                  aes(x = sample,
                      ymin = mean_ratio - se,
                      ymax = mean_ratio + se),
                  width = 0.2) +
    
    # 添加显著性字母
    geom_text(data = summary_stats,
              aes(x = sample,
                  y = letter_y_pos),  # 使用每个样本的独立位置
              label = summary_stats$letter,
              size = 6,
              vjust = -0.5) +
    
    # 设置主题和标签
    theme_classic() +
    labs(x = NULL,
         y = "Root length ratio (ISX/Mock)") +
    apply_plot_theme() +
    
    # 设置颜色 - 使用传入的颜色映射
    scale_fill_manual(values = color_maps$column) +
    scale_color_manual(values = color_maps$point) +
    
    # 设置y轴范围
    scale_y_continuous(
      limits = c(0, y_max),
      expand = expansion(mult = c(0, 0))
    ) +
    
    # 控制X轴扩展
    scale_x_discrete(
      expand = expansion(mult = c(0.2, 0.05))
    ) +
    
    # 修改坐标系
    coord_cartesian(
      xlim = c(x_min, x_max),
      clip = "off",
      expand = FALSE
    ) +
    
    # 添加主题调整
    theme(
      axis.line = element_line(linewidth = 0.5, colour = "black"),
      panel.grid.major = element_blank(),
      panel.grid.minor = element_blank(),
      panel.border = element_blank(),
      panel.background = element_blank(),
      axis.title.x = element_blank(), # 隐藏 X 轴标题
      #axis.text.x = element_blank()   # 隐藏 X 轴刻度标签
    )
}