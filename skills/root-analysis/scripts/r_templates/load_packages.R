# ==== R/load_packages.R ====
load_required_packages <- function() {
  packages <- c(
    "readxl",      # 读取Excel文件
    "dplyr",       # 数据处理
    "purrr",       # map 函数
    "ggplot2",     # 绘图
    "multcompView", # 显著性字母生成
    "tidyr"        # unnest 函数
  )
  
  # 检查并安装缺失的包
  new_packages <- packages[!(packages %in% installed.packages()[,"Package"])]
  if(length(new_packages)) install.packages(new_packages)
  
  # 加载所有包
  invisible(lapply(packages, library, character.only = TRUE))
}