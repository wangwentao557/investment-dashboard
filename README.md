# 小王投资仪表盘

在线地址：
https://wangwentao557.github.io/investment-dashboard/

## 自动数据链

每日 17:00（Asia/Shanghai）：

1. 回补/校验 5 年估值历史；当 5 年数据稳定且可用时扩展至 10 年。
2. 抓取 13 笔实际持仓的最新可用净值。
3. 抓取 9 个估值监控对象与宏观数据。
4. 仅使用真实历史点进行正式 L2；每个非黄金目标至少 60 个点才计算。
5. 生成 data/latest、data/history、data/l2_latest、data/history_status。
6. 同步到 site/data。
7. GitHub Pages 自动部署。

## 理杏仁历史数据

正式 5 年/10 年估值历史使用理杏仁开放平台。该 API 要求用户专属 Token，因此需要在 GitHub 仓库设置一次：

Settings → Secrets and variables → Actions → New repository secret

名称：LIXINGER_TOKEN

值：你的理杏仁开放平台 Token。

未设置 Token 时，系统仍会运行每日更新，并保留公共页面可获得的数据；但不会伪造 5 年历史，也不会因为历史不足而输出正式 L2。

## 数据规则

失败或过期数据保留上一可靠值并显式标记；估算值不作为正式当日值。

历史序列禁止插值、模拟和伪造。

黄金为参考仓位，不设置硬性目标，也不进入 PE/PB/PS 的正式 L2。

仓位监控只显示参考区间偏离，不自动调仓。

## 工作流

- .github/workflows/daily_update.yml：每日 17:00
- .github/workflows/backfill_history.yml：可手动回补历史