import json
from typing import Iterator, Dict, Any, Iterable, AsyncIterator
from itertools import chain

def parse_json_array_stream(line_iterator: Iterable[str]) -> Iterator[Dict[str, Any]]:
    """
    解析一个由文本行组成的、格式化的(pretty-printed)JSON数组流。

    这个函数是一个生成器，它会为在流中发现的每个第一层级的JSON对象
    产出(yield)一个完整的Python字典。它的设计目标是高内存效率，
    因为它会逐行处理流，而不是一次性加载所有内容。

    Args:
        line_iterator: 一个产生响应行的迭代器。例如，`requests.Response.iter_lines()`
                       解码后的结果。

    Yields:
        一个从流中解析出的JSON对象的字典。

    Raises:
        ValueError: 如果流看起来不像是以JSON数组开始，或者其格式错误
                    导致无法按对象进行解析。
    """
    # 状态变量
    buffer = []
    brace_level = 0
    in_array = False

    # 1. 寻找数组的起始符 '['，并忽略之前的所有行
    for line in line_iterator:
        stripped_line = line.strip()
        if not stripped_line:
            continue

        if stripped_line.startswith('['):
            in_array = True
            # 去掉起始的 '[' 字符，剩下的部分继续处理
            line = stripped_line[1:]
            # 使用 chain 连接剩余行，避免转换为列表（内存优化）
            line_iterator = chain([line], line_iterator)
            break
    
    if not in_array:
        raise ValueError("数据流不是以一个JSON数组 ( '[' ) 开始。")

    # 2. 遍历流，逐个字符地构建和解析对象
    in_string = False  # 是否在字符串内部
    escape_next = False  # 下一个字符是否被转义

    for line in line_iterator:
        for char in line:
            # 处理转义字符
            if escape_next:
                if brace_level > 0:
                    buffer.append(char)
                escape_next = False
                continue

            # 检查是否是转义符
            if char == '\\':
                if brace_level > 0:
                    buffer.append(char)
                escape_next = True
                continue

            # 检查字符串边界（只在对象内部时才处理）
            if char == '"' and brace_level > 0:
                in_string = not in_string
                buffer.append(char)
                continue

            # 只有在非字符串内部时，才处理括号
            if not in_string:
                # 当遇到 '{' 时，增加嵌套层级
                if char == '{':
                    # 如果是第一层级的对象，清空缓冲区，准备接收新对象
                    if brace_level == 0:
                        buffer = []
                    brace_level += 1

                # 只有在对象内部时 (brace_level > 0)，才将字符加入缓冲区
                if brace_level > 0:
                    buffer.append(char)

                # 当遇到 '}' 时，减少嵌套层级
                if char == '}':
                    brace_level -= 1
                    # 当层级回到0时，说明一个第一层级的对象已经完整
                    if brace_level == 0 and buffer:
                        obj_str = "".join(buffer)
                        try:
                            # 解析这个完整的对象字符串并产出结果
                            # 使用 strict=False 允许控制字符
                            yield json.loads(obj_str, strict=False)
                        except json.JSONDecodeError as e:
                            # 如果解析失败，抛出带上下文的异常
                            raise ValueError(f"解析JSON对象失败: {e}\n内容: {obj_str}") from e
                        finally:
                            # 重置缓冲区，为下一个对象做准备
                            buffer = []
                            in_string = False  # 重置字符串状态
            else:
                # 在字符串内部，直接添加字符
                if brace_level > 0:
                    buffer.append(char)

    # 3. 检查流结束后，是否还有未闭合的对象
    if brace_level != 0:
        print(f"警告: JSON流意外结束，括号层级为 {brace_level}，可能数据不完整。")

async def parse_json_array_stream_async(line_iterator: AsyncIterator[str]) -> AsyncIterator[Dict[str, Any]]:
    """
    异步版本：解析一个由文本行组成的、格式化的(pretty-printed)JSON数组流。

    这个函数是一个异步生成器，它会为在流中发现的每个第一层级的JSON对象
    产出(yield)一个完整的Python字典。它的设计目标是高内存效率，
    因为它会逐行处理流，而不是一次性加载所有内容。

    Args:
        line_iterator: 一个产生响应行的异步迭代器。例如，`httpx.Response.aiter_lines()`

    Yields:
        一个从流中解析出的JSON对象的字典。

    Raises:
        ValueError: 如果流看起来不像是以JSON数组开始，或者其格式错误
                    导致无法按对象进行解析。
    """
    # 状态变量
    buffer = []
    brace_level = 0
    in_array = False

    # 1. 寻找数组的起始符 '['，并忽略之前的所有行
    in_string = False
    escape_next = False

    async for line in line_iterator:
        stripped_line = line.strip()
        if not stripped_line:
            continue

        if stripped_line.startswith('['):
            in_array = True
            # 去掉起始的 '[' 字符，剩下的部分继续处理
            line = stripped_line[1:]
            # 处理剩余部分（使用相同的字符串状态跟踪逻辑）
            for char in line:
                if escape_next:
                    if brace_level > 0:
                        buffer.append(char)
                    escape_next = False
                    continue

                if char == '\\':
                    if brace_level > 0:
                        buffer.append(char)
                    escape_next = True
                    continue

                if char == '"' and brace_level > 0:
                    in_string = not in_string
                    buffer.append(char)
                    continue

                if not in_string:
                    if char == '{':
                        if brace_level == 0:
                            buffer = []
                        brace_level += 1

                    if brace_level > 0:
                        buffer.append(char)

                    if char == '}':
                        brace_level -= 1
                        if brace_level == 0 and buffer:
                            obj_str = "".join(buffer)
                            try:
                                yield json.loads(obj_str, strict=False)
                            except json.JSONDecodeError as e:
                                raise ValueError(f"解析JSON对象失败: {e}\n内容: {obj_str}") from e
                            finally:
                                buffer = []
                                in_string = False
                else:
                    if brace_level > 0:
                        buffer.append(char)
            break

    if not in_array:
        raise ValueError("数据流不是以一个JSON数组 ( '[' ) 开始。")

    # 2. 遍历流，逐个字符地构建和解析对象（保持第一行处理后的状态）
    async for line in line_iterator:
        for char in line:
            # 处理转义字符
            if escape_next:
                if brace_level > 0:
                    buffer.append(char)
                escape_next = False
                continue

            # 检查是否是转义符
            if char == '\\':
                if brace_level > 0:
                    buffer.append(char)
                escape_next = True
                continue

            # 检查字符串边界（只在对象内部时才处理）
            if char == '"' and brace_level > 0:
                in_string = not in_string
                buffer.append(char)
                continue

            # 只有在非字符串内部时，才处理括号
            if not in_string:
                # 当遇到 '{' 时，增加嵌套层级
                if char == '{':
                    # 如果是第一层级的对象，清空缓冲区，准备接收新对象
                    if brace_level == 0:
                        buffer = []
                    brace_level += 1

                # 只有在对象内部时 (brace_level > 0)，才将字符加入缓冲区
                if brace_level > 0:
                    buffer.append(char)

                # 当遇到 '}' 时，减少嵌套层级
                if char == '}':
                    brace_level -= 1
                    # 当层级回到0时，说明一个第一层级的对象已经完整
                    if brace_level == 0 and buffer:
                        obj_str = "".join(buffer)
                        try:
                            # 解析这个完整的对象字符串并产出结果
                            # 使用 strict=False 允许控制字符
                            yield json.loads(obj_str, strict=False)
                        except json.JSONDecodeError as e:
                            # 如果解析失败，抛出带上下文的异常
                            raise ValueError(f"解析JSON对象失败: {e}\n内容: {obj_str}") from e
                        finally:
                            # 重置缓冲区，为下一个对象做准备
                            buffer = []
                            in_string = False  # 重置字符串状态
            else:
                # 在字符串内部，直接添加字符
                if brace_level > 0:
                    buffer.append(char)

    # 3. 检查流结束后，是否还有未闭合的对象
    if brace_level != 0:
        print(f"警告: JSON流意外结束，括号层级为 {brace_level}，可能数据不完整。")

