"""流式响应工具。"""

from __future__ import annotations

import json
import re
from typing import Any, AsyncIterator, Dict, Iterable, Iterator, List, Tuple

from fastapi.responses import StreamingResponse

STREAM_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


def sse_event(event: str, data: Dict[str, Any]) -> str:
    payload = json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n"


def sse_response(event_stream: AsyncIterator[str]) -> StreamingResponse:
    return StreamingResponse(
        event_stream,
        media_type="text/event-stream",
        headers=STREAM_HEADERS,
    )


def iter_langgraph_updates(chunk: Any) -> Iterator[Tuple[str, Dict[str, Any]]]:
    if not isinstance(chunk, dict):
        return

    for node_name, update in chunk.items():
        if isinstance(update, dict):
            yield node_name, update


def merge_langgraph_update(final_state: Dict[str, Any], update: Dict[str, Any]) -> Dict[str, Any]:
    final_state.update(update)
    return final_state


def chunk_text(text: str, max_chars: int = 88) -> List[str]:
    if not text:
        return []

    pieces = [part for part in re.split(r"(?<=[\n。！？；;])", text) if part]
    chunks: List[str] = []
    buffer = ""

    for piece in pieces:
        if len(piece) >= max_chars:
            if buffer:
                chunks.append(buffer)
                buffer = ""
            for index in range(0, len(piece), max_chars):
                chunks.append(piece[index:index + max_chars])
            continue

        if len(buffer) + len(piece) > max_chars and buffer:
            chunks.append(buffer)
            buffer = piece
        else:
            buffer += piece

    if buffer:
        chunks.append(buffer)

    return chunks
