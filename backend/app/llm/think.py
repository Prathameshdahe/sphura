"""Strip `<think>…</think>` reasoning blocks that some open models emit inside `content`."""
from __future__ import annotations

_OPEN, _CLOSE = "<think>", "</think>"


def _partial_suffix(text: str, tag: str) -> int:
    """Length of the longest suffix of `text` that is a proper prefix of `tag`."""
    for k in range(min(len(tag) - 1, len(text)), 0, -1):
        if text.endswith(tag[:k]):
            return k
    return 0


class ThinkFilter:
    def __init__(self) -> None:
        self._buf = ""
        self._inside = False

    def feed(self, text: str) -> str:
        self._buf += text
        out: list[str] = []
        while self._buf:
            if self._inside:
                i = self._buf.find(_CLOSE)
                if i < 0:
                    self._buf = self._buf[-(len(_CLOSE) - 1):]
                    break
                self._buf = self._buf[i + len(_CLOSE):].lstrip("\n")
                self._inside = False
            else:
                i = self._buf.find(_OPEN)
                if i < 0:
                    keep = _partial_suffix(self._buf, _OPEN)
                    out.append(self._buf[: len(self._buf) - keep])
                    self._buf = self._buf[len(self._buf) - keep:]
                    break
                out.append(self._buf[:i])
                self._buf = self._buf[i + len(_OPEN):]
                self._inside = True
        return "".join(out)

    def flush(self) -> str:
        rest = "" if self._inside else self._buf
        self._buf = ""
        return rest
