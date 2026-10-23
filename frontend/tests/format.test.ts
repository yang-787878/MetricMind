import { describe, expect, it } from 'vitest'

import {
  formatAxis,
  formatBytes,
  formatCount,
  formatDuration,
  formatPercent,
  formatRelativeTime,
  formatValue,
  truncate,
  unitLabel,
} from '@/lib/format'

describe('format.ts', () => {
  it('金额按万/亿简化', () => {
    expect(formatValue(1042180, 'CNY')).toBe('¥104.2 万')
    expect(formatValue(197028789, 'CNY')).toBe('¥1.97 亿')
    expect(formatValue(4200, 'CNY')).toBe('¥4,200')
  })

  it('比率转百分比、计数带千分位', () => {
    expect(formatValue(-0.1849, 'ratio')).toBe('-18.5%')
    expect(formatValue(7180, 'count')).toBe('7,180')
    expect(formatPercent(0.94)).toBe('94%')
    expect(formatCount(1234567)).toBe('1,234,567')
  })

  it('空值统一显示为破折号', () => {
    expect(formatValue(null, 'CNY')).toBe('—')
    expect(formatValue(undefined, 'ratio')).toBe('—')
    expect(formatDuration(null)).toBe('—')
  })

  it('时长按 ms/s/min 分级', () => {
    expect(formatDuration(320)).toBe('320ms')
    expect(formatDuration(12400)).toBe('12.4s')
    expect(formatDuration(125000)).toBe('2m 05s')
  })

  it('坐标轴刻度紧凑且带单位语义', () => {
    expect(formatAxis(1838980, null)).toBe('184万')
    expect(formatAxis(0.184, 'ratio')).toBe('18%')
    expect(formatAxis(720, null)).toBe('720')
  })

  it('单位与字节、截断、相对时间的展示', () => {
    expect(unitLabel('CNY')).toBe('人民币')
    expect(unitLabel('ratio')).toBe('比率')
    expect(unitLabel(undefined)).toBe('')
    expect(formatBytes(2048)).toBe('2.0 KB')
    expect(truncate('abcdefghij', 5)).toBe('abcd…')
    expect(formatRelativeTime(new Date().toISOString())).toBe('刚刚')
  })
})
