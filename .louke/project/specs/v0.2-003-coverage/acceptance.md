# Millionaire Coverage — Acceptance Criteria

- **Spec ID**: v0.2-003-coverage
- **复核日期**: 2026-07-10
- **对应 spec**: [spec.md](./spec.md)

编号约定：每个 FR/NFR 内 `AC-N` 从 1 开始。完整引用写作 `AC-FRXXXX-YY` 或 `AC-NFRXXXX-YY`。

只有同一次 `tests/unit` 运行满足“pytest 全绿 + 整体 ≥95% + 非豁免逐文件 ≥80%”时，覆盖率验收才成立。

<a id="ac-fr-0001"></a>
## FR-0001 契约来源与冲突判定

### AC-1

- 每个新增/修改测试文件的模块 docstring、测试 docstring 或紧邻断言注释至少含一个可解析引用：`v0.2-001 ... FR/AC`、`v0.2-002 ... FR/AC` 或 `v0.2-003 ... FR/AC`。

### AC-2

- 抽查本 spec 每个 FR 至少一项行为断言，期望值可追到上游公式/schema/示例或独立 fixture；不得通过调用被测函数生成 expected value。

### AC-3

- 当上游合同与当前实现冲突时，测试名或缺陷记录标为 `implementation-defect`，测试期望保持上游值；不得以“现有实现为准”让冲突测试通过。

### AC-4

- 对无上游引用、无生产消费方的模块，提交物包含 `rg` 消费方证据并标记 `dead-or-marker` 或 `spec-gap`；没有新造 CRUD、序列化、状态机或异常类型。

<a id="ac-fr-0101"></a>
## FR-0101 pytest 配置与规范命令

### AC-1

- 项目根执行规范命令 `poetry run pytest tests/unit --cov=quantide --cov-fail-under=95 --cov-report=term-missing --cov-report=json:coverage.json --cov-report=html:htmlcov`，发布候选上 exit 0。

### AC-2

- 若任一 unit test 失败或报错，即使已执行行的覆盖率 ≥95%，命令仍 exit 非 0。

### AC-3

- 将整体阈值临时提高到高于实测值时命令 exit 非 0；恢复 95 后由真实覆盖率决定，证明门禁未被吞掉。

### AC-4

- `coverage.json` 存在且 `totals.percent_covered >= 95`；`htmlcov/index.html` 存在并含生产源码链接。

### AC-5

- pytest/coverage 配置只来自 `pyproject.toml`；不存在项目级 `pytest.ini`/`setup.cfg` 重复配置；`asyncio_mode = "auto"`。

<a id="ac-fr-0102"></a>
## FR-0102 逐文件覆盖率检查与豁免清单

### AC-1

- 给检查器输入 synthetic `coverage.json`：overall=96%，一个 79.99% 的非豁免生产文件 → exit 非 0，并输出该文件路径与百分比。

### AC-2

- synthetic JSON 中所有 `quantide/**/*.py` 且 `num_statements>0` 文件 ≥80% → exit 0；`num_statements=0` 文件被跳过。

### AC-3

- 含 1 条 import/re-export statement 且覆盖率 <80% 的 `__init__.py` 仍触发失败，证明它未被误当空文件。

### AC-4

- 合法 waiver 含 `module/current_coverage/reason/expires_at/followup_issue` 且未过期时可跳过对应文件；缺字段、过期、模块不存在或 issue 为空时 exit 非 0。

### AC-5

- 默认 [coverage-waivers.json](./coverage-waivers.json) 的 `waivers` 为空；`pyproject.toml` coverage omit/exclude 没有为本任务新增生产模块排除。

<a id="ac-fr-0103"></a>
## FR-0103 Mock 边界与共享 Fixture

### AC-1

- pytest 自动加载 `tests/unit/conftest.py`；`env` 暴露 `manifest/universe/calendar/daily_bars/adj_factor/st_info/limit_price`，fixture version 与 manifest 一致。

### AC-2

- 网络、SMTP、Tushare 与 qmt-gateway 用例安装边界 mock 后，开启“禁止真实 socket”守卫仍全部通过。

### AC-3

- app factory 测试调用 `create_app(app_config_dir=tmp_path, enforce_single_instance=False)` 或等价隔离 fixture；断言 DB/PID/runtime state 路径均在 tmp_path 下。

### AC-4

- 新增测试没有 patch 当前被测函数/方法的主体；patch 目标仅为其外部边界或下游 port/service。

<a id="ac-fr-0104"></a>
## FR-0104 测试隔离与确定性

### AC-1

- 任取每个低覆盖域至少一条关键测试，单独运行与整套运行结果一致；随机化测试文件顺序时结果不变。

### AC-2

- 使用全新临时 `HOME/XDG_CONFIG_HOME/data home` 运行完整 unit suite，测试不读取仓库 `.sesskey` 或开发者 `~/.config/quantide`。

### AC-3

- suite 结束后没有存活的测试 scheduler/message-hub worker/async task，没有未关闭 SQLite client 警告，仓库内无新增 `.db/.sqlite/.parquet/.log/pid`。

### AC-4

- 重复运行完整 unit suite 两次，pass/fail/skip 数量相同，coverage 总 statements 与 covered statements 相同。

<a id="ac-fr-0201"></a>
## FR-0201 core/domain 事件 DTO

### AC-1

- 用完整字段构造 MarketEvent/QuoteSnapshot/OrderEvent/TradeEvent/ErrorEvent，逐字段读取值与输入完全一致。

### AC-2

- MarketEvent 未传 source/event_id 时分别为 `unknown`/空串；OrderEvent 的 filled_qty/filled_price 为 0.0、reason 为空串；ErrorEvent.retryable 为 False。

### AC-3

- 创建两个 ErrorEvent，只修改第一个 `details`，第二个仍为空，证明 mutable default 不共享。

### AC-4

- 事件测试不调用或要求 `to_dict/from_dict/to_json/from_json`；若未来添加，必须另有上游/兼容合同。

<a id="ac-fr-0202"></a>
## FR-0202 core/runtime 时钟适配

### AC-1

- `BacktestClockAdapter.set_now(t)` 后 `now() is/equal t`；不同实例互不影响。

### AC-2

- `SystemClockAdapter.set_now(t)` 抛 RuntimeError，消息包含不支持设置系统时钟的语义。

### AC-3

- monkeypatch 交易日历 `get_frames` 返回 sentinel iterable；两类 adapter 的 `iter_frames(start,end,frame_type)` 返回 sentinel，并把三个参数各传一次且不改写。

### AC-4

- 依赖回测时钟的业务测试先 set/inject 固定时间；不存在断言真实“今天”的 flaky 用例。

<a id="ac-fr-0203"></a>
## FR-0203 core/runtime 网关客户端与 BrokerPort 适配

### AC-1

- fake opener 连续执行两次 API 请求，只收到一次 `/auth/login`；登录表单含 username/password/auto_login=false，后续 GET/POST path、query/form 与输入相同。

### AC-2

- application/json 或 text/plain 的 JSON body 返回解析对象；空 body 返回 None；text/html 与未允许 content type 抛 GatewayProtocolError。

### AC-3

- cookie jar 含两个 cookie 时 `cookie_header()` 同时包含 `name=value`；http/https/no-scheme base 分别产生 ws/wss/ws URL 且 path 不丢失。

### AC-4

- fake GatewayClient 捕获 buy/sell/cancel/query 请求；GatewayBrokerAdapter 输出对应 OrderAck/ExecutionResult/CancelAck/PositionView/AssetView/OrderView/Trade 字段，与 001 interfaces 一致。

### AC-5

- 网关响应的 qtoid/external order id 与请求归因冲突时抛一致性错误；没有写入错误 portfolio 的 position/order/trade。

<a id="ac-fr-0204"></a>
## FR-0204 core/runtime 装配与兼容 Broker

### AC-1

- `RuntimeBootstrap(mode="paper", clock=fake_clock).bootstrap()` 输出 context.mode=`paper` 且 context.clock 为同一 fake；registry/adapters/market_data 非空并可按公开 API 查询。

### AC-2

- 自动 mode：配置 gateway disabled 或 livequote none → backtest；合法显式 live/paper/backtest 不被改写。

### AC-3

- DB 返回 simulation、QMT 与损坏 portfolio 时，只成功加载合法 simulation；坏账户不阻止 context 创建。

### AC-4

- PortBackedBroker 把 AssetView/PositionView/OrderView 映射为同 portfolio 的 Asset/Position/Order；query_assets=None 时返回零值 Asset。

### AC-5

- buy/buy_percent/buy_amount/sell/sell_percent/sell_amount/trade_target_pct/cancel_order/cancel_all_orders 的参数与返回值原样透传；未知 side/status 映射 UNKNOWN。

### AC-6

- 本 FR 没有端口注册/注销、一对多消息路由或模式转换状态机测试。

<a id="ac-fr-0205"></a>
## FR-0205 core 策略、发现与调度

### AC-1

- 反射 `BaseStrategy.on_bar` 签名仅为 self+tm；Strategy 的 init/on_start/on_stop/on_day_open/on_day_close 默认 await 后无副作用。

### AC-2

- fake broker 捕获 BaseStrategy 的 get_bars/record/九类交易与撤单委托；输入参数、返回 DTO 不丢失。

### AC-3

- RiskStrategy 实例无 buy/buy_amount/buy_percent API；`sell_host_position(asset,shares,reason)` 归属宿主 broker，并能读取 get_prices/get_ticks。

### AC-4

- 临时策略目录含合法 Base/Risk 子类、普通类、损坏文件和子目录策略：discover 只返回根目录合法具体子类，元数据字段满足 001-FR-020，其他项进入 skipped 且整次扫描成功。

### AC-5

- SchedulerManager 首次访问 scheduler 才 init；重复 start/stop 不重复调用底层；add_job/add_listener 参数原样透传。

### AC-6

- 测试不要求 SchedulerManager 提供 remove_job/list_jobs；若调用底层 scheduler 的对应方法，明确标为 APScheduler compatibility 而非本类 API。

<a id="ac-fr-0206"></a>
## FR-0206 core 枚举、消息、SDK 与辅助规则

### AC-1

- FrameType 的已定义 int round-trip 与跨周期比较返回预期；非法 int/不可比对象走明确 ValueError/NotImplemented/TypeError 分支。

### AC-2

- 同一 callback 重复 subscribe 只收到一次消息；unsubscribe 后不再收到；一个 callback 抛错不影响同 topic 的其他 callback。

### AC-3

- topic 无 subscriber 时 publish 的 payload 可由 get/get_no_wait 取得；不存在 topic 的 get_no_wait 抛可判定错误；stop 后 worker 在限定时间内退出。

### AC-4

- CalendarSDK 五个方法把输入原样交给 calendar 并返回 bool/date/int/list[date]；SecurityListSDK 对上市/退市/ST/未知/名称按 001-FR-015 返回。

### AC-5

- core 辅助 DTO/规则各有至少一个上游字段正常例与非法/边界例，异常消息不丢失原始 code/category/details。

<a id="ac-fr-0207"></a>
## FR-0207 core/ports 结构契约

### AC-1

- 一个实现 BrokerPort 全部方法的 fake 可被 Strategy/adapter 消费；submit/buy/sell/cancel/query 的输入输出 DTO 字段完整。

### AC-2

- ClockPort fake 可注入 RuntimeBootstrap/Runner；DataFetcherPort fake 可注入数据获取/存储消费方；MarketDataPort fake 可被 RuntimeBootstrap/PaperBroker 消费。

### AC-3

- DataFetcherPort 的七个方法签名分别返回 DataFrame 或 `(DataFrame, errors)`；MarketDataPort.stream 可 async iterate MarketEvent，snapshot 返回 symbol→QuoteSnapshot。

### AC-4

- 两个 OrderRequest/OrderAck/ExecutionResult 实例的 extra/trades 容器互不共享。

### AC-5

- 验收不以“Protocol 实例化抛 TypeError”为条件；使用结构化替身验证真实消费方兼容性。

<a id="ac-fr-0301"></a>
## FR-0301 data/fetchers

### AC-1

- fake Tushare SDK 捕获 calendar/stock/adjust/daily/limit/ST 调用；日期边界和批次与输入一致，没有外网请求。

### AC-2

- `fetch_bars_ext` 对固定 fixture 输出至少包含资产/日期、OHLCV、amount、adjust、is_st、up_limit、down_limit 可消费列，值与各上游 frame 的 join 结果一致。

### AC-3

- 单个日期批次失败时 errors 记录该批次而成功批次仍返回；整体鉴权失败和空结果分别有明确异常/空 frame 断言。

### AC-4

- DataFetcherRegistry 注册后 has/get/list_names 可观察；默认项通过 get(None) 返回；未知 name 抛 KeyError 或当前公开约定异常；重复注册行为有明确断言。

<a id="ac-fr-0302"></a>
## FR-0302 data/models

### AC-1

- Calendar 用固定交易日 fixture 验证 date/time int round-trip、day/week/month shift、get_frames、get_trade_dates/count 和开闭市边界。

### AC-2

- StockList 对代码/中文/拼音查询、上市前/退市后、ST 排除和 days_since_ipo 返回独立 fixture 期望。

### AC-3

- DailyBars 对日期范围/count、price、price limits、close adjustment factor 和 match price 的正常/空数据输出列与值正确。

### AC-4

- AppState 合法 dict round-trip；非法端口/日期/必填配置被拒；is_fully_initialized/can_use_live_trading/can_use_backtest 与步骤状态一致。

### AC-5

- `IndexBars.SCHEMA` 精确含 `sector_id,date,open,high,low,close,volume,amount` 与约定 Polars 类型；测试不实例化并调用不存在的 CRUD/serialization。

### AC-6

- entities/strategy config 的 datetime/date/enum 默认和 `to_db_schema/to_dict` 输出与 001 interfaces §4 字段一致。

<a id="ac-fr-0303"></a>
## FR-0303 data/stores 与 SQLite

### AC-1

- 临时 Parquet store 从空状态 append 固定两年数据后，单文件/按年分区路径、size/start/end/available_dates 与输入一致。

### AC-2

- Parquet get 的 date 闭区间、columns、eager/lazy 与空 store 分支返回正确行列；fetch progress 与错误列表可断言。

### AC-3

- IndexBarsStore.get 的 symbols 过滤命中 `sector_id`，start/end 为闭区间，eager 返回 DataFrame、lazy 返回 LazyFrame、空 store 返回对应空对象。

### AC-4

- IndexBarsStore.rec_counts_per_date 返回每个 date 的准确计数；fetch 总是抛包含“主体移除”语义的 RuntimeError，且不触发网络。

### AC-5

- 临时 SQLite 完成 portfolio→asset/position/order/trade/log 的 insert/upsert/query/update，字段与 001 interfaces §4 一致；过滤条件返回正确子集。

### AC-6

- delete_portfolio_cascade 后该 portfolio 的关联记录清空、其他 portfolio 不变；测试数据库/连接在 teardown 后可删除。

<a id="ac-fr-0304"></a>
## FR-0304 data/helper 与 resampler

### AC-1

- 给定手算 OHLC+adjust fixture，qfq/hfq 输出与独立公式在容差内一致；空 frame 保持空，缺必需列走明确错误。

### AC-2

- pandas、Polars DataFrame、Polars LazyFrame 分别按整体和 asset group 切分，train/valid/test 时间有序、无重叠、合并后不丢业务行，输出类型与输入一致。

### AC-3

- 周/月聚合满足 open=首、high=max、low=min、close=末、volume/amount=sum、adjust=末；空输入为空。

### AC-4

- `calculate_ma(periods=[5,20])` 产生 ma5/ma20 并等于独立 rolling mean；非法 freq/period 走明确错误或当前公开边界。

<a id="ac-fr-0401"></a>
## FR-0401 service 策略加载、Runtime 与 Runner

### AC-1

- StrategyLoader 在 builtin+user 同名时按 002-FR-0010 的用户优先级输出，list/get metadata schema 正确；坏文件只进入 skipped/失败计数。

### AC-2

- scan_and_cache 后新实例 load_from_cache 得到相同策略集合；clear/损坏 cache 不把旧脏策略当成功结果。

### AC-3

- copy_examples_to_directory 对首次复制/目标已存在/非法目标分别返回正确 copied/skipped 计数且不覆盖用户文件。

### AC-4

- BrokerRegistry 按 kind+portfolio_id 注册/get/list/list_by_kind/unregister；不存在返回 None，默认账户只指向已注册项。

### AC-5

- StrategyRuntimeManager 对 backtest create→complete→remove、paper/live deploy、start/stop、account/strategy block/unblock 的 row/status/risk event 符合 001-FR-230~250 与 002 runtime UI。

### AC-6

- BacktestRunner 拒绝 RiskStrategy；BaseStrategy 一日回调顺序为 init/on_start/on_day_open/on_bar/on_day_close/on_stop，异常时 on_stop/资源清理仍可观察。

<a id="ac-fr-0402"></a>
## FR-0402 service Broker 与交易规则

### AC-1

- AbstractBroker submit/cancel/query 把内部 broker 输出转换为 BrokerPort DTO；wait timeout 与 awake result 可确定性断言，未知 status 不误报成功。

### AC-2

- up_limit 以上买单、down_limit 以下卖单、停牌/volume=0、取整后 0 股、资金不足被拒且无成交/持仓变化。

### AC-3

- 买入向下取整至 100 股；清仓/零股卖出例外；当日买入 avail=0，下一交易日结算后可卖。

### AC-4

- 回测订单全成或拒绝；paper 在成交量限制下可部分成交并经历 submitted/partial/filled 或 cancelled/rejected 合法状态。

### AC-5

- 固定买卖 fixture 的 cash、佣金、印花税、market value、total 与加权成本由独立公式计算且匹配 broker 输出。

### AC-6

- 手工/风控/策略订单的 portfolio_id 与 qtoid 归属正确；一个 portfolio 的交易不修改另一 portfolio。

<a id="ac-fr-0403"></a>
## FR-0403 service BarsFeed 与 LiveQuote

### AC-1

- fake history store+live quote 下，BarsFeed.get_bars 返回标准列并按 end/count/frame 取历史；形成中 bar 仅在允许时追加且不重复最后一根历史 bar。

### AC-2

- get_price_limits/current_price/price_for_match/close_adjust_factor 对正常、空、缺 symbol 输出明确 tuple/float/None/frame，未笼统吞掉编程错误。

### AC-3

- LiveQuote 解析固定 websocket payload 后 all_quotes/all_limits/minute/daily cache 值正确；损坏 JSON/缺字段不污染已有 cache。

### AC-4

- subscribe(symbols) 与 unsubscribe(symbols) 更新下游订阅；stream 产出 MarketEvent；snapshot 对已知/未知 symbol 返回约定 QuoteSnapshot map。

### AC-5

- start/stop 重复调用无重复 worker；stop 后 stream 可结束，测试无遗留线程/async task。

### AC-6

- 本 FR 不要求 callback subscriber 或 tick→bar 聚合 API。

<a id="ac-fr-0404"></a>
## FR-0404 service 辅助能力

### AC-1

- backtest log record/list/load/delete 保持时间、level、message、extra；文件写失败只降级一次并仍可从 DB/内存读取约定记录。

### AC-2

- GridSearch 对参数网格执行全部且仅全部笛卡尔组合，结果每行含参数与指标；save_logs 的路径在 tmp_path 且内容可重读。

### AC-3

- InitWizardService 对必填步骤失败停留、可选步骤跳过、gateway test 成功/鉴权失败/连接失败、complete/reset/progress/redirect 都有确定性输出，HTTP 全 mock。

### AC-4

- metrics 对固定 returns/trades fixture 的年化、最大回撤、Sharpe、Sortino、Calmar、胜率、盈亏比、次数在约定容差内匹配独立计算；空输入边界明确。

### AC-5

- trade_lightning add/update/remove/clear/list 保持 entry 字段；非法 amount/price_ref/duplicate 或 missing entry 走明确错误/False；cached price reference 对固定行情值正确。

### AC-6

- triple_barrier 的 up/down/expire 与同日双触障结果逐项匹配 001-FR-360 F-TB-1~5，阈值单位为百分点、收益为小数。

<a id="ac-fr-0501"></a>
## FR-0501 web/components/analysis

### AC-1

- KlineChart.render 输出可序列化节点，含唯一 chart id、传入 OHLCV 数据和 update script；空数据仍输出稳定容器且不抛错。

### AC-2

- freq_buttons/day-week-month 与 ma_buttons/periods 输出 action target 和 current/selected 状态，两个 chart_id 不串扰。

### AC-3

- StockList.render 对两条股票输出代码/名称与唯一 selected 状态；空列表输出明确空状态；toolbar 显示给定 sector name。

### AC-4

- StockList 测试不调用不存在的 filter/sort/search 方法；过滤/搜索在 API/service/page 对应 FR 验证。

### AC-5

- equity/drawdown/heatmap ChartSpec 含正确 chart type、series/labels/render_target，validate 函数正常/缺 target 分别 True/False；不要求 Python spec 本身生成 SVG/canvas。

<a id="ac-fr-0502"></a>
## FR-0502 web 通用组件与布局

### AC-1

- header 对 active nav、unread=0/>0、recent alert、anonymous/authenticated user 分支输出相应节点与 ARIA/target。

### AC-2

- sidebar 对折叠/active/disabled 与多级菜单输出符合 002-FR-0150；HTMX fragment 导航属性只在允许时出现。

### AC-3

- toast success/error/warning/info 的 level、icon、ARIA role、自动关闭秒数符合 002-FR-0170/NFR-0040；error 为白底红边/字而非红底。

### AC-4

- RuntimeParams 的 principal/slippage/tax/commission/min commission 对合法边界通过，越界抛 RuntimeParamsError；asset label 已知/未知有稳定输出。

### AC-5

- MainLayout 普通请求输出 header+sidebar+main，HTMX fragment 只输出目标区域；theme/button/modal/spacing helper 满足 002-NFR-0020/0040。

<a id="ac-fr-0503"></a>
## FR-0503 web/pages 路由与页面输出

### AC-1

- 自动 route inventory 将 002 interfaces §2 每个 in-scope method/path 映射到已注册 route 或显式 compatibility redirect；缺失项使测试失败并列出 method/path。

### AC-2

- strategy/accounts/trade/history 各选至少一个列表、详情、成功动作、非法输入和下游失败场景，response 字段/按钮/状态/确认语义匹配对应 002 FR 与 001 schema。

### AC-3

- system calendar/stocks/market/tasks/integrity/gateway 各使用固定 service fixture；查询/分页/过滤/手动运行/保存/测试的输入映射与页面或 fragment 输出可断言。

### AC-4

- init-wizard 未初始化首步、必填失败停留、可选 skip、恢复失败步骤、progress、complete 与 force reconfigure 分别匹配 002-FR-0460。

### AC-5

- 对同一 page，普通请求返回完整 layout，HTMX 请求返回 fragment/正确 target；单区域 service 抛错时该区域有 retry 占位而其他区域仍存在。

### AC-6

- page/app tests 的 DB/PID/config 全在 tmp_path；禁止通过真实 dev stub、真实用户 DB 或真实数据目录让断言通过。

<a id="ac-fr-0504"></a>
## FR-0504 web/auth、API 与 middleware

### AC-1

- 未初始化 GET `/` → 303 到 wizard；已初始化未登录 → 303 到 `/login`（允许内部 `/auth/login` compatibility redirect，但用户可观察目标符合 002 interfaces）；已登录 → dashboard。

### AC-2

- 正确凭证登录建立 session 并按安全 `next` redirect；错误凭证无 session 且显示错误；POST logout 清 session；改密覆盖旧密码错、两次不一致、成功。

### AC-3

- 注册、forgot/reset、多用户 admin route 不作为 002 产品成功路径；若保留可执行代码，有 characterization test 且不得从登录 UI 暴露注册入口。

### AC-4

- 逐个 broker/analysis API 至少覆盖有效输入→2xx+schema、非法输入→4xx ErrorEnvelope、下游不可用→约定 5xx/503、空结果→约定空 schema/404。

### AC-5

- Init/Auth/Feature middleware 对 public/protected、A/B 降级、HTMX/full page 和 exception handler 输出对应 redirect/status/ErrorEnvelope；错误 details 不含 password/token/api key。

### AC-6

- BrokerRegistryMiddleware 把指定 registry 注入 request scope；并发两个 app/client 的 registry 不串扰。

<a id="ac-fr-0505"></a>
## FR-0505 web 跨切面与 service 合同

### AC-1

- web/services 的每个公开纯函数/DTO 至少有对应 002 FR/AC 正常与非法/边界断言；当前已覆盖行为不因本任务删测。

### AC-2

- ErrorEnvelope 固定 `ok=false` 并保留 code/message/details/retry/request id；PushEvent 五类 payload 的必填字段 validator 对缺字段返回 False。

### AC-3

- degradation 对 gateway 未配置/离线/在线产生 A/B/None，entrance availability 与 tooltip/banner 颜色符合 002-FR-0180。

### AC-4

- localStorage 只允许 002 interfaces §6 key；password/session/token/api_key 等敏感 key 被拒；损坏 JSON/读取异常返回默认值且不阻塞。

### AC-5

- accessibility/responsive/error degradation/long task/partial refresh/visual helper 的阈值和结构逐项匹配 002-NFR-0010~0070。

<a id="ac-fr-0601"></a>
## FR-0601 CI 单元测试与双重覆盖率门禁

### AC-1

- `.github/workflows/unit-coverage.yml` 或等价独立 job 在 push/PR 的 main 与 releases/** 触发，Python 版本满足 `>=3.13,<4.0`。

### AC-2

- job 安装 test dependency group，并设置隔离 HOME/XDG_CONFIG_HOME/data/config；不依赖开发者 `.sesskey` 或外部 dev stub。

### AC-3

- job 运行 FR-0101 规范命令；注入一个 failing test 时 job 失败，整体 coverage=94.99% 时失败。

### AC-4

- job 随后执行 FR-0102 检查器；synthetic/fixture 79% 非豁免文件使 job 失败，合法未过期 waiver 才能放行该文件。

### AC-5

- 主 pytest 与逐文件 gate 步骤没有 `continue-on-error: true`；现有 louke-ci 可并存但不替代 unit coverage gate。

<a id="ac-fr-0602"></a>
## FR-0602 覆盖率 Artifact 与可选增量检查

### AC-1

- CI 产物包含 `coverage.json` 与 `htmlcov/index.html`，artifact 名稳定、`retention-days: 30`。

### AC-2

- 主测试失败但报告已生成时，artifact 步骤可通过 `if: always()` 执行；job 最终状态仍为失败。

### AC-3

- 若启用 diff-cover，使用本次 coverage XML、明确 compare branch 与 95 阈值，且标记为非阻断；禁用时不影响主门禁。

<a id="ac-fr-0701"></a>
## FR-0701 notify 通道与遗留市场 helper

### AC-1

- compose 对 plain/html/attachment 分别生成正确 Subject/content type/attachment bytes；缺正文或 msg 与 subject/body 同时提供时抛 TypeError/AssertionError 的明确输入错误。

### AC-2

- send_mail/mail_notify 用 fake aiosmtplib 捕获 From/To/Cc/Bcc/subject/body/host/port/username，不发网络；SMTP connect failure 的 retry 次数可控且最终失败可观察。

### AC-3

- DingTalk string 构造 text payload，title/text dict 构造 markdown payload；token 缺失抛 ValueError；固定 time+secret 的 timestamp/sign 与独立 HMAC 结果一致。

### AC-4

- DingTalk HTTP 2xx+errcode0 返回成功；HTTP 非 2xx、业务 errcode、timeout 分别记录/返回失败且不报告成功，日志不含 secret/access token/password。

### AC-5

- `notify/__init__.py` 对沪深北代表代码输出 hson/xt/jq 目标格式；普通与 300/688 涨跌停、9:30~15:00 时间差匹配独立规则 fixture。

<a id="ac-fr-0702"></a>
## FR-0702 内置策略

### AC-1

- DualMAStrategy.default_config 精确为 fast=5/slow=20；反射 on_bar 只有 self+tm，并通过 get_bars 拉取日线而非接收 quote/frame_type 参数。

### AC-2

- T-1 fast≤slow、T fast>slow 且空仓 → 一次买入；T-1 fast≥slow、T fast<slow 且有仓 → 一次卖出；窗口不足/无交叉不下单。

### AC-3

- Pullback 默认 m=7/k=0.5/n=1；达到 m 后在 n 分钟内回落超过 k 且 avail>0 → 一次 `sell_host_position(..., reason="drawback")`。

### AC-4

- Pullback 在 n 分钟窗口外回落、无有效 price、avail=0 或同日已触发 → 不卖；新交易日清空触发状态。

### AC-5

- Cost stop 在 cost=10/k=-5 时 price=9.50 和 9.49 触发、9.51 不触发；只卖 avail，reason=`cost_stop`，无成本/价格/avail 不卖且不重复。

### AC-6

- 以上策略输出只断言 broker 边界和公开日志/订单，不断言私有 helper 调用次数；当前代码若不满足 AC-1/AC-3，测试以 implementation-defect 失败。

<a id="ac-fr-0703"></a>
## FR-0703 config 与 app bootstrap

### AC-1

- config 默认值、环境覆盖、branding、normalize_data_home 与 app config override 在合法/空/非法输入下输出明确；monkeypatch teardown 后恢复原环境。

### AC-2

- dev stub start/stop/重复 start 在 fake process/server 边界幂等；禁用或非法配置不访问真实端口、不读取仓库 `.sesskey`。

### AC-3

- `create_app(app_config_dir=tmp_path, enforce_single_instance=False)` 在未初始化和已初始化 fixture 均返回 app；所有 sqlite/pid/runtime/backtest-log 路径位于 tmp_path。

### AC-4

- 未初始化 root 走 wizard，已初始化 root 走 login/dashboard；runtime bootstrap 单点失败被记录并降级，不让 app factory 无响应。

### AC-5

- route inventory 含 002 interfaces 所需 mount/route，middleware 顺序含 init/feature/registry/auth 与 exception handler；两个 app fixture 状态不串扰。

### AC-6

- 在 tmp_path 中启用 enforce_single_instance：首次写 PID，模拟存活重复 PID 抛明确错误，stale PID 可恢复；不接触真实用户 PID。

<a id="ac-nfr-0010"></a>
## NFR-0010 发布覆盖率与豁免

### AC-1

- 发布证据中的 unit pytest 为 0 failed/0 errors，且同次 `coverage.json.totals.percent_covered >= 95`。

### AC-2

- 检查器报告每个 `quantide/**/*.py`、`num_statements>0` 文件 ≥80%，或列出唯一合法未过期 waiver；未列入 coverage JSON 的生产文件使检查失败。

### AC-3

- 空/0-statement 文件不进入检查；含 executable import/re-export 的文件进入检查，未设置永久豁免。

### AC-4

- CI 主门禁阈值为 overall 95 / per-file 80，步骤无 continue-on-error，coverage source 为完整 quantide。

<a id="ac-nfr-0020"></a>
## NFR-0020 隔离、确定性与资源清理

### AC-1

- 完整 suite 在无网络、空临时 HOME/config/data 环境通过；断开/未启动真实 qmt-gateway、SMTP、Tushare 不改变结果。

### AC-2

- 完整 suite 连续运行两次，测试计数与 coverage totals 相同；代表性用例单独运行结果相同。

### AC-3

- suite 无 ResourceWarning/unclosed database、pending async task、存活 worker/scheduler；仓库工作区无测试残留文件。

### AC-4

- 时间/并发测试使用 injected clock/event/condition；无为等待生产异步行为而使用超过必要范围的固定 sleep。

<a id="ac-nfr-0030"></a>
## NFR-0030 有意义覆盖与反作弊

### AC-1

- 每个从 <80% 提升的生产文件至少有正常路径和失败/边界路径，且含 assert/raises/response/schema/state/persistence/boundary-call 中至少一种实质断言。

### AC-2

- 新增测试不存在仅 import、仅实例化、仅断言常量存在却声称完成该模块行为覆盖的文件。

### AC-3

- mock 不替换被测主体；expected value 不调用被测实现；network/time/storage/downstream mock 的输入输出在断言中可观察。

### AC-4

- diff 审查确认未扩大 omit/exclude、未批量 pragma:no cover、未降低阈值、未仅为百分比删除有效生产代码。

### AC-5

- marker/dead code 的删除或保留附上上游引用与消费方搜索证据，并经过独立代码评审。

## No Acceptance

- 所有 US-* 用户故事由对应 FR-* 验收，不设独立 AC 节。
