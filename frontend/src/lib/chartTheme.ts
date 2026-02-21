/**
 * ECharts 统一主题配置
 * 基于项目的设计系统，提供一致的图表样式
 */

// 主题色板
export const chartColors = {
  primary: '#0ea5e9',
  success: '#10b981',
  warning: '#f59e0b',
  danger: '#ef4444',
  info: '#3b82f6',
  purple: '#a855f7',
  pink: '#ec4899',
  slate: '#64748b',
  gray: '#94a3b8',
  lightGreen: '#4ade80',
  cyan: '#22d3ee',
  emerald: '#34d399',
}

// 模型专用色板
export const modelColors: Record<string, string> = {
  'gemini-3-pro-preview': chartColors.primary,
  'gemini-3.1-pro-preview': chartColors.primary,
  'gemini-2.5-pro': chartColors.cyan,
  'gemini-2.5-flash': chartColors.warning,
  'gemini-3-flash-preview': chartColors.pink,
  'gemini-imagen': chartColors.emerald,
  'gemini-veo': chartColors.success,
  'gemini-auto': chartColors.slate,
}

// 有效模型列表
export const validModels = [
  'gemini-auto',
  'gemini-2.5-flash',
  'gemini-2.5-pro',
  'gemini-3-flash-preview',
  'gemini-3-pro-preview',
  'gemini-3.1-pro-preview',
  'gemini-imagen',
  'gemini-veo',
]

// 获取模型颜色（带回退）
export function getModelColor(model: string): string {
  return modelColors[model] || chartColors.gray
}

// 过滤有效模型
export function filterValidModels(modelRequests: Record<string, number[]>): Record<string, number[]> {
  const filtered: Record<string, number[]> = {}
  validModels.forEach(model => {
    if (modelRequests[model]) {
      filtered[model] = modelRequests[model]
    }
  })
  return filtered
}

// 文本样式
const textStyle = {
  fontFamily: 'Noto Sans SC, -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif',
  color: '#6b6b6b',      // text-muted-foreground
  fontSize: 11,
}

// 网格配置
const gridConfig = {
  left: 24,
  right: 16,
  top: 44,
  bottom: 24,
  containLabel: true,
}

// 工具提示配置
const tooltipConfig = {
  backgroundColor: 'rgba(255, 255, 255, 0.95)',
  borderColor: '#e5e5e5',
  borderWidth: 1,
  textStyle: {
    color: '#1a1a1a',
    fontSize: 12,
  },
  padding: [8, 12],
  extraCssText: 'border-radius: 8px; box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);',
}

// 图例配置
const legendConfig = {
  textStyle: {
    ...textStyle,
    fontSize: 11,
  },
  itemWidth: 14,
  itemHeight: 14,
  itemGap: 16,
}

/**
 * 折线图主题配置
 */
export function getLineChartTheme() {
  return {
    tooltip: {
      ...tooltipConfig,
      trigger: 'axis',
      axisPointer: {
        type: 'line',
        lineStyle: {
          color: '#d4d4d4',
          type: 'dashed',
        },
      },
    },
    legend: {
      ...legendConfig,
      right: 0,
      top: 0,
    },
    grid: gridConfig,
    xAxis: {
      type: 'category',
      boundaryGap: false,
      axisLine: {
        lineStyle: {
          color: '#d4d4d4',
        },
      },
      axisTick: {
        show: false,
      },
      axisLabel: {
        ...textStyle,
        fontSize: 10,
      },
    },
    yAxis: {
      type: 'value',
      axisLine: {
        show: false,
      },
      axisTick: {
        show: false,
      },
      axisLabel: {
        ...textStyle,
        fontSize: 10,
      },
      splitLine: {
        lineStyle: {
          color: '#e5e5e5',
          type: 'solid',
        },
      },
    },
  }
}

/**
 * 饼图主题配置
 */
export function getPieChartTheme(isMobile = false) {
  const legendPosition = isMobile
    ? {
      left: 'center',
      bottom: 0,
      orient: 'horizontal' as const,
    }
    : {
      left: 0,
      top: 'middle',
      orient: 'vertical' as const,
    }

  const pieCenter = isMobile ? ['50%', '42%'] : ['60%', '50%']
  const pieRadius = isMobile ? ['35%', '55%'] : ['45%', '70%']

  return {
    animation: true,
    animationDuration: 600,
    animationEasing: 'cubicOut',
    animationDurationUpdate: 300,
    animationEasingUpdate: 'cubicOut',
    tooltip: {
      ...tooltipConfig,
      trigger: 'item',
    },
    legend: {
      ...legendConfig,
      ...legendPosition,
      type: isMobile ? 'scroll' : 'plain',
      pageIconSize: 10,
    },
    series: {
      type: 'pie',
      radius: pieRadius,
      center: pieCenter,
      startAngle: 90,
      animationType: 'scale',
      animationEasing: 'cubicOut',
      avoidLabelOverlap: true,
      label: {
        show: true,
        fontSize: 11,
        color: '#6b6b6b',
      },
      labelLine: {
        show: true,
        length: 12,
        length2: 10,
        lineStyle: {
          color: '#d4d4d4',
        },
      },
      itemStyle: {
        borderWidth: 2,
        borderColor: '#fff',
        borderRadius: 8,
      },
      emphasis: {
        label: {
          show: true,
          fontSize: 13,
          fontWeight: 'bold',
        },
      },
    },
  }
}

/**
 * 创建折线图系列配置
 */
export function createLineSeries(
  name: string,
  data: number[],
  color: string,
  options?: {
    smooth?: boolean
    showSymbol?: boolean
    areaOpacity?: number
    lineWidth?: number
    zIndex?: number
    lineStyle?: {
      type?: 'solid' | 'dashed' | 'dotted'
      width?: number
    }
  }
) {
  const {
    smooth = true,
    showSymbol = false,
    areaOpacity = 0.25,
    lineWidth = 2,
    zIndex = 1,
    lineStyle,
  } = options || {}

  return {
    name,
    type: 'line',
    data,
    smooth,
    showSymbol,
    lineStyle: {
      width: lineStyle?.width ?? lineWidth,
      ...(lineStyle?.type && { type: lineStyle.type }),
    },
    areaStyle: {
      opacity: areaOpacity,
    },
    itemStyle: {
      color,
    },
    emphasis: {
      disabled: true,
    },
    z: zIndex,
  }
}

/**
 * 创建饼图数据项配置
 */
export function createPieDataItem(
  name: string,
  value: number,
  color: string
) {
  return {
    name,
    value,
    itemStyle: {
      color,
      borderRadius: 8,
    },
  }
}
