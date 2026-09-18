# investment-dashboard

小王投资盯盘系统。

## 当前部署

- Dashboard: `site/index.html`
- GitHub Pages: 由 `.github/workflows/pages.yml` 自动部署
- 当前快照基准日：2026-09-18
- 13 笔实际持仓、9 个估值监控
- 正式 L2 历史计算门槛：至少 60 个真实历史点
- 不插值、不模拟、不伪造历史数据
- 基金净值严格区分“正式净值日期”和估算值
- 黄金仅作为参考仓位，不设硬目标
- 仓位映射未经用户明确变更不得修改

## 后续自动更新

每日盯盘任务应更新同一站点的数据/历史，并保持数据日期、来源、失败/过期状态可追溯。GitHub Pages 只负责展示，不负责计算估值信号；正式 L2 数值计算应由 `valuation_engine.py` 完成。
