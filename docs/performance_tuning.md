# 性能优化与调优说明

本文记录 TQSync v1.3.60 的性能优化内容、实测数据与后续调优手段。

## 1. 优化项

| 模块 | 原实现 | 现实现 | 说明 |
| --- | --- | --- | --- |
| `db/database.py` | 每次查询 `aiosqlite.connect` 建连接 + 开线程 | 进程内复用一条长连接（WAL + `synchronous=NORMAL` + `busy_timeout`），读操作串行化到一把 `asyncio.Lock` | 单次 DB 操作从 5~7ms 降到 0.2~0.5ms |
| `db/database.py` | 绑定/设置/屏蔽词每次落库 | 进程内缓存，所有写方法主动失效 | 消息热路径不再访问数据库 |
| `core/file_transfer.py` | 每次下载新建 `ClientSession` + `TCPConnector` | 模块级共享连接池（懒加载、可重建），`temp` 目录只 `makedirs` 一次 | 每个文件省一次 TCP/TLS 握手 |
| `main.py` | Webhook 里对所有媒体 `shutil.copy`（阻塞事件循环） | 只复制真正要转发的那一个文件，且放到线程池执行 | 事件循环不再被大文件复制卡住 |
| `handlers/qq_handler.py` | `get_bot_id()` 失败后每条消息都重试（3 次 + 退避） | 失败负缓存 10 秒 + 启动预热，连接池上限调大 | 反回环判重不再拖慢热路径 |
| `api/admin_api.py` | 状态接口 `cpu_percent(interval=0.1)` 阻塞事件循环；日志接口全量 `readlines` | 阻塞调用移入线程池；日志改为从文件尾部按块回读 | WebUI 刷新不再造成循环停顿 |
| `handlers/command_handler.py`、`core/sync_engine.py` | `subprocess.run(git ...)` 在事件循环内执行 | `asyncio.to_thread` | 消除 30~100ms 的同步阻塞 |
| `core/sync_engine.py` | 并发工作者固定 3、队列固定 50 | `sync.worker_count` / `sync.queue_size` 可配置 | 大群可按需调优 |

**刻意没有采用的变化**：日志 sink 保持同步写。实测 loguru `enqueue=True` 只把
sink 写出搬到后台线程，格式化 + JSON serialize + 跨线程投递仍在调用线程，
单次 `logger.info` 从 ~0.06ms 涨到 ~0.45ms（4~7 倍），对"每条消息几次日志"的
机器人是净损失。进程强杀前的日志收口由 `utils.logger.shutdown_logger()` 负责。

## 2. 实测数据

`python scripts/bench_perf.py --ops 300`（Windows / Python 3.14，单次调用耗时）：

| 操作 | 优化前 | 优化后 | 提升 |
| --- | --- | --- | --- |
| `save_message_mapping` | 7.278 ms | 0.493 ms | ~15x |
| `get_tg_msg_id_by_qq` | 5.325 ms | 0.190 ms | ~28x |
| `get_binding_by_qq` | 4.799 ms | 0.002 ms | 缓存命中 |
| `check_blocked_word_in_text` | 5.126 ms | 0.002 ms | 缓存命中 |
| `get_setting` | 4.726 ms | <0.001 ms | 缓存命中 |
| `get_custom_prefix_by_uid` | 5.546 ms | 0.003 ms | 缓存命中 |

按一条 QQ 文本消息的既有调用链（屏蔽词检测 + 绑定查询 + 前缀查询 + 映射写入）估算：
事件循环中的数据库耗时约 **22.7ms → 0.5ms**。

其它实测：

- 50MB 本地文件复制 = 32ms 阻塞；现在放到线程池，且一条消息最多只复制实际使用的那一个文件。
- WebUI 日志接口读取 6.9MB 日志：40.6ms → 0.7ms。

## 3. 调优参数

`config.yaml`：

```yaml
sync:
  worker_count: 3   # 同步工作者并发数，高峰可调到 4~8
  queue_size: 50    # 待同步队列上限，满了会丢弃新任务
```

注意：`worker_count` 调大会同时占用更多 TG/QQ 连接与带宽；NapCat 侧也有频率限制，
一般 3~4 足够。

## 4. 复跑验证

```bash
python scripts/bench_perf.py            # 性能基准
python scripts/test_database.py         # 数据库层功能回归（45 项断言）
python scripts/test_webhook_hotpath.py  # Webhook 热路径行为（11 项断言）
python scripts/test_file_transfer_perf.py  # 下载连接复用 + 清理（10 项检查）
python scripts/test_logger_qq.py        # 日志落盘 + Bot ID 负缓存（33 项断言）
```

以上脚本都使用临时数据库 / 临时目录 / localhost 服务，不会访问真实 NapCat 或 Telegram。
