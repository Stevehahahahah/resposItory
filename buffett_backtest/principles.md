# 巴菲特的决策原则 → 量化规则

下面每条原则都在本地语料里核对过（`python corpus.py grep <关键词>` 可以复查）。语料范围：
1959–1970 年合伙人信件（扫描件，已 OCR）、1972–2024 年致股东信、2021–2025 年他的几封公开信、所有者手册、
1951–2008 年的文章和讲座，rbcpa.com 收集的 47 篇访谈和讲座笔记，以及 buffettfaq.com 按主题整理的股东大会问答。
完整清单见 [sources.csv](sources.csv)。

| # | 原则 | 原文（出处） | 怎么量化 | 代码 |
|---|---|---|---|---|
| 1 | **能力圈** | "You only have to be able to evaluate companies within your circle of competence. The size of that circle is not very important; knowing its boundaries, however, is vital."（1996 信） | 排除金融、保险、REIT（SIC 6000–6799）：ROE、负债这些尺子量不了它们；其他行业交给下面的规则去筛 | `run.py: Universe.financial` |
| 2 | **看不加杠杆的 ROE，不看每股收益增长** | "The primary test of managerial economic performance is the achievement of a high earnings rate on equity capital employed (without undue leverage, accounting gimmickry, etc.) and not the achievement of consistent gains in earnings per share."（1979 信） | 5 年平均 ROE ≥ 15%，单年 ≥ 12%；权益因回购变成负数时，改用 净利润 ÷（权益 + 长期负债） | `roe_avg`, `roe_floor` |
| 3 | **收购标准**（1982 年起几乎每年都登） | "(2) demonstrated consistent earning power (future projections are of little interest to us, nor are 'turn-around' situations), (3) businesses earning good returns on equity while employing little or no debt, (4) management in place … (5) simple businesses … (6) an offering price"（1982–2024 信） | 5 年净利润全部为正，并且有增长；长期负债 ≤ 3 年净利润 | `ni_positive`, `ni_growth`, `debt_years` |
| 4 | **护城河 / 经济特许权** | "a kind of moat that protects a valuable and much-sought-after business castle"（1986 信，GEICO）；特许权来自"needed or desired / no close substitute / not subject to price regulation"的产品（1991 信） | 毛利率 5 年内下滑不超过 5 个百分点（有定价权的公司毛利率稳），再加上规则 2 | `gm_drop` |
| 5 | **所有者盈余** | "(a) reported earnings plus (b) depreciation, depletion, amortization, and certain other non-cash charges … less (c) the average annual amount of capitalized expenditures"；"the relevant item for valuation purposes"（1986 信） | 净利润 + 折旧摊销 − 资本开支（缺折旧数据时用 经营现金流 − 资本开支），取最近 3 年平均 | `owner_earnings` |
| 6 | **1 美元测试** | "We test the wisdom of retaining earnings by assessing whether retention, over time, delivers shareholders at least $1 of market value for each $1 retained … on a five-year rolling basis."（1983 信） | 5 年市值增加额 ÷（净利润 − 分红 − 回购）≥ 1 | `dollar_test` |
| 7 | **不稀释股东** | "We will issue common stock only when we receive as much in business value as we give."（1983 信） | 稀释后股数 5 年内增加不超过 2% | `dilution` |
| 8 | **内在价值 = 现金流折现** | "The value of any stock, bond or business today is determined by the cash inflows and outflows – discounted at an appropriate interest rate – that can be expected to occur during the remaining life of the asset."（1992 信，引用 John Burr Williams） | 10 年两阶段 DCF：所有者盈余按 5 年净利润增速增长（限制在 0–10% 之间），之后每年 3% 永续增长 | `strategy.dcf` |
| 9 | **折现率：所有股票用同一个，而且远高于国债利率** | "We use the same discount rate across all securities … Just because interest rates are at 1.5% doesn't mean we like an investment that yields 2-3%. We have minimum thresholds in our mind that are a whole lot higher than government rates."（2003 年股东大会） | 固定 10%，不随利率变化 | `DEFAULTS["discount"]` |
| 10 | **安全边际** | "Confronted with a challenge to distill the secret of sound investment into three words, we venture the motto, Margin of Safety."（1990 信引用格雷厄姆） | 市值比内在价值低至少 25% 才买 | `mos` |
| 11 | **市场先生** | "imagine market quotations as coming from a remarkably accommodating fellow named Mr. Market who is your partner in a private business"（1987 信） | 只拿价格和价值比：便宜才买、贵得离谱才卖，不看走势 | `mos`, `sell_over` |
| 12 | **好公司比便宜货重要** | "It's far better to buy a wonderful company at a fair price than a fair company at a wonderful price."（1989 信） | 先过质量规则 2–7，再比价格；不买烟蒂股 | `buyable` |
| 13 | **集中** | "If you really know businesses, you probably shouldn't own more than six of them."（1998 佛罗里达大学讲座）；1993 信批评过度分散 | 最多持有 10 只（另外测试 8 只和 15 只），等权买入，之后不再平衡 | `n_hold` |
| 14 | **长期持有** | "when we own portions of outstanding businesses with outstanding managements, our favorite holding period is forever"（1988 信）；"We won't sell a business just because it's underperforming."（2005 年股东大会） | 每季度复查一次；连续两次质量不合格、股价超过内在价值 1.5 倍、或退市，才卖出 | `backtest.run_rules` |
| 15 | **别人贪婪时恐惧** | "we simply attempt to be fearful when others are greedy and to be greedy only when others are fearful"（1986 信；2008 年《纽约时报》"Buy American. I Am."） | 规则只看估值，不看情绪；股市大跌时更多股票达到安全边际，买入自然变多 | — |
| 16 | **没机会就拿现金** | 他的信里年年报告大量短期国债 | 空出来的仓位放在 BIL（1–3 个月国债 ETF） | `Book` |
| 17 | **他的看法会变** | 早年说"simple businesses (if there's lots of technology, we won't understand it)"，2016 年开始大量买苹果 | 策略 B 不写死阈值：每个复查日都用当时已经公开的伯克希尔真实买入数据重新校准 | `strategy.calibrate` |

## 规则里的数字是哪来的

- 他在信里只说过"good returns on equity""little or no debt"这类话，**没有给出 15% ROE、3 年还清负债、25% 安全边际这样的硬性数字**。这几个数字是研究巴菲特的书里常用的解读，策略 A 用的就是它们。
- 10% 折现率依据第 9 条：他说所有股票用同一个折现率，而且远高于国债利率。
- 策略 B 用伯克希尔的真实买入去检验这些数字：每个阈值取"伯克希尔买过的公司里有 75% 能通过"的那个值，只用复查日之前已经公开的 13F。

## 经典投资（13F 之前，来自信件）

见 [investments.csv](investments.csv)。这些投资发生在 XBRL 财报数据出现之前，所以只作为案例，不参与量化回测。
