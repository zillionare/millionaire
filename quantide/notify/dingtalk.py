import asyncio
import base64
import hashlib
import hmac
import json
import time
import urllib.parse
from collections.abc import Awaitable
from typing import Any, cast

import httpx
from loguru import logger

from quantide.config.settings import get_dingtalk_access_token, get_dingtalk_secret


class DingTalkMessage:
    """
    钉钉的机器人消息推送类，封装了常用的消息类型以及加密算法

        需要在运行时配置中提供机器人的 access_token。
        如果配置了加签，需要同时提供机器人的 secret。
        如果配置了自定义关键词，需要同时提供 keyword，多个关键词用英文逗号分隔。
        其中 secret 和 keyword 可以不配置，access_token 必须配置。
    notify:
      dingtalk_access_token: xxxx
      dingtalk_secret: xxxx
    """

    url = "https://oapi.dingtalk.com/robot/send"

    @classmethod
    def _get_access_token(cls) -> str:
        """获取钉钉机器人的access_token"""
        token = get_dingtalk_access_token()
        if token:
            return token
        logger.error(
            "Dingtalk not configured, please add the following items:\n"
            "notify:\n"
            "  dingtalk_access_token: xxxx\n"
            "  dingtalk_secret: xxxx\n"
        )
        raise ValueError("dingtalk_access_token not found")

    @classmethod
    def _get_secret(cls) -> str | None:
        """获取钉钉机器人的secret"""
        return get_dingtalk_secret() or None

    @classmethod
    def _get_url(cls) -> str:
        """获取钉钉机器人的消息推送地址，将签名和时间戳拼接在url后面"""
        access_token = cls._get_access_token()
        url = f"{cls.url}?access_token={access_token}"
        secret = cls._get_secret()
        if secret:
            timestamp, sign = cls._get_sign(secret)
            url = f"{url}&timestamp={timestamp}&sign={sign}"
        return url

    @classmethod
    def _get_sign(cls, secret: str) -> tuple[str, str]:
        """获取签名发送给钉钉机器人"""
        timestamp = str(round(time.time() * 1000))
        secret_enc = secret.encode("utf-8")
        string_to_sign = f"{timestamp}\n{secret}"
        string_to_sign_enc = string_to_sign.encode("utf-8")
        hmac_code = hmac.new(secret_enc, string_to_sign_enc, digestmod=hashlib.sha256).digest()
        sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))
        return timestamp, sign

    @classmethod
    def _send(cls, msg: dict[str, Any]) -> str | None:
        """发送消息到钉钉机器人"""
        url = cls._get_url()
        response = httpx.post(url, json=msg, timeout=30)
        if response.status_code != 200:
            logger.error(
                "failed to send message, content: "
                f"{msg}"
                ", response from Dingtalk: "
                f"{response.content.decode()}"
            )
            return None
        rsp = json.loads(response.content)
        if rsp.get("errcode") != 0:
            logger.error(f"failed to send message, content: {msg}, response from Dingtalk: {rsp}")
            return None
        return response.content.decode()

    @classmethod
    async def _send_async(cls, msg: dict[str, Any]) -> str | None:
        """发送消息到钉钉机器人"""
        url = cls._get_url()
        async with httpx.AsyncClient() as client:
            r = await client.post(url, json=msg, timeout=30)
            if r.status_code != 200:
                logger.error(
                    "failed to send message, content: "
                    f"{msg}"
                    ", response from Dingtalk: "
                    f"{r.content.decode()}"
                )
                return None
            rsp = json.loads(r.content)
            if rsp.get("errcode") != 0:
                logger.error(
                    f"failed to send message, content: {msg}, response from Dingtalk: {rsp}"
                )
                return None
            return r.content.decode()


def ding(
    msg: str | dict[str, Any], sync: bool = False, at_all: bool = False
) -> Awaitable[str | None] | str | None:
    """发送消息到钉钉机器人

    支持发送纯文本消息和markdown格式的文本消息。如果要发送markdown格式的消息，请通过字典传入，
    必须包含包含"title"和"text"两个字段。更详细信息，
    请见[钉钉开放平台文档](https://open.dingtalk.com/document/orgapp-server/message-type)

    ???+ Important
        必须在异步线程(即运行asyncio loop的线程）中调用此方法，否则会抛出异常。
        此方法返回一个Awaitable，您可以等待它完成，也可以忽略返回值，
        此时它将作为一个后台任务执行，但完成的时间不确定。

    Args:
        msg: 待发送消息。

    Returns:
        发送消息的后台任务。您可以使用此返回句柄来取消任务。
    """
    if isinstance(msg, str):
        msg_ = {"text": {"content": msg}, "msgtype": "text", "at": {"isAtAll": at_all}}
    elif isinstance(msg, dict):
        msg_ = {
            "msgtype": "markdown",
            "markdown": {"title": msg["title"], "text": msg["text"]},
            "at": {"isAtAll": at_all},
        }

    logger.warning(msg)
    if sync:
        return cast(Awaitable[str | None] | str | None, DingTalkMessage._send(msg_))

    task = asyncio.create_task(DingTalkMessage._send_async(msg_))
    return task
