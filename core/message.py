"""消息处理模块

负责消息的解析、文本提取和会话指纹生成
"""
import asyncio
import base64
import hashlib
import logging
import re
from typing import List, TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from main import Message

logger = logging.getLogger(__name__)


def get_conversation_key(messages: List[dict], client_identifier: str = "") -> str:
    """
    生成对话指纹（使用前3条消息+客户端标识，确保唯一性）

    策略：
    1. 使用前3条消息生成指纹（而非仅第1条）
    2. 加入客户端标识（IP或request_id）避免不同用户冲突
    3. 保持Session复用能力（同一用户的后续消息仍能找到同一Session）

    Args:
        messages: 消息列表
        client_identifier: 客户端标识（如IP地址或request_id），用于区分不同用户
    """
    if not messages:
        return f"{client_identifier}:empty" if client_identifier else "empty"

    # 提取前3条消息的关键信息（角色+内容）
    message_fingerprints = []
    for msg in messages[:3]:  # 只取前3条
        role = msg.get("role", "")
        content = msg.get("content", "")

        # 统一处理内容格式（字符串或数组）
        if isinstance(content, list):
            # 多模态消息：只提取文本部分
            text = extract_text_from_content(content)
        else:
            text = str(content)

        # 标准化：去除首尾空白，转小写
        text = text.strip().lower()

        # 组合角色和内容
        message_fingerprints.append(f"{role}:{text}")

    # 使用前3条消息+客户端标识生成指纹
    conversation_prefix = "|".join(message_fingerprints)
    if client_identifier:
        conversation_prefix = f"{client_identifier}|{conversation_prefix}"

    return hashlib.md5(conversation_prefix.encode()).hexdigest()


def extract_text_from_content(content) -> str:
    """
    从消息 content 中提取文本内容
    统一处理字符串和多模态数组格式
    """
    if isinstance(content, str):
        return content
    elif isinstance(content, list):
        # 多模态消息：只提取文本部分
        return "".join([x.get("text", "") for x in content if x.get("type") == "text"])
    else:
        return str(content)


async def parse_last_message(messages: List['Message'], http_client: httpx.AsyncClient, request_id: str = ""):
    """解析最后一条消息，分离文本和文件（支持图片、PDF、文档等，base64 和 URL）"""
    if not messages:
        return "", []

    last_msg = messages[-1]
    content = last_msg.content

    text_content = ""
    images = [] # List of {"mime": str, "data": str_base64} - 兼容变量名，实际支持所有文件
    image_urls = []  # 需要下载的 URL - 兼容变量名，实际支持所有文件

    if isinstance(content, str):
        text_content = content
    elif isinstance(content, list):
        for part in content:
            if part.get("type") == "text":
                text_content += part.get("text", "")
            elif part.get("type") == "image_url":
                url = part.get("image_url", {}).get("url", "")
                # 解析 Data URI: data:mime/type;base64,xxxxxx (支持所有 MIME 类型)
                match = re.match(r"data:([^;]+);base64,(.+)", url)
                if match:
                    images.append({"mime": match.group(1), "data": match.group(2)})
                elif url.startswith(("http://", "https://")):
                    image_urls.append(url)
                else:
                    logger.warning(f"[FILE] [req_{request_id}] 不支持的文件格式: {url[:30]}...")

    # 并行下载所有 URL 文件（支持图片、PDF、文档等）
    if image_urls:
        async def download_url(url: str):
            try:
                resp = await http_client.get(url, timeout=30, follow_redirects=True)
                if resp.status_code == 404:
                    logger.warning(f"[FILE] [req_{request_id}] URL文件已失效(404)，已跳过: {url[:50]}...")
                    return None
                resp.raise_for_status()
                content_type = resp.headers.get("content-type", "application/octet-stream").split(";")[0]
                # 移除图片类型限制，支持所有文件类型
                b64 = base64.b64encode(resp.content).decode()
                logger.info(f"[FILE] [req_{request_id}] URL文件下载成功: {url[:50]}... ({len(resp.content)} bytes, {content_type})")
                return {"mime": content_type, "data": b64}
            except httpx.HTTPStatusError as e:
                status_code = e.response.status_code if e.response else "unknown"
                logger.warning(f"[FILE] [req_{request_id}] URL文件下载失败({status_code}): {url[:50]}... - {e}")
                return None
            except Exception as e:
                logger.warning(f"[FILE] [req_{request_id}] URL文件下载失败: {url[:50]}... - {e}")
                return None

        results = await asyncio.gather(*[download_url(u) for u in image_urls], return_exceptions=True)
        safe_results = []
        for result in results:
            if isinstance(result, Exception):
                logger.warning(f"[FILE] [req_{request_id}] URL文件下载异常: {type(result).__name__}: {str(result)[:120]}")
                continue
            safe_results.append(result)
        images.extend([r for r in safe_results if r])

    return text_content, images


def build_full_context_text(messages: List['Message']) -> str:
    """仅拼接历史文本，图片只处理当次请求的"""
    prompt = ""
    for msg in messages:
        role = "User" if msg.role in ["user", "system"] else "Assistant"
        content_str = extract_text_from_content(msg.content)

        # 为多模态消息添加图片标记
        if isinstance(msg.content, list):
            image_count = sum(1 for part in msg.content if part.get("type") == "image_url")
            if image_count > 0:
                content_str += "[图片]" * image_count

        prompt += f"{role}: {content_str}\n\n"
    return prompt
