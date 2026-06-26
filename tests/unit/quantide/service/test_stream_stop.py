"""#127: 验证 stop() 后 stream() 立即退出 (sentinel 机制)."""
import asyncio

import pytest

from quantide.service.livequote import LiveQuote


@pytest.fixture
def fresh_live_quote():
    """每次测试创建全新 LiveQuote 实例 (绕过 singleton)."""
    LiveQuote._instance = None
    lq = LiveQuote()
    yield lq
    # cleanup
    lq._streaming = False
    lq._stream_queue = None
    lq._stream_loop = None
    LiveQuote._instance = None


@pytest.mark.asyncio
async def test_stop_unblocks_stream(fresh_live_quote):
    """stop() 注入 sentinel 后, stream() 应在无 tick 时立即退出."""
    lq = fresh_live_quote

    async def _consume():
        events = []
        async for event in lq.stream():
            events.append(event)
        return events

    # 启动 stream consumer
    task = asyncio.create_task(_consume())

    # 给 event loop 一轮时间让 stream() 注册到 msg_hub 并进入 await
    await asyncio.sleep(0.05)

    # stop() 应注入 sentinel, 唤醒阻塞的 queue.get()
    lq.stop()

    # consumer 应在短时间内退出 (不依赖下一个 tick)
    try:
        events = await asyncio.wait_for(task, timeout=1.0)
    except TimeoutError:
        pytest.fail("stream() did not exit after stop() — sentinel not injected")

    assert events == []  # 没有 tick 进入, 应为空
