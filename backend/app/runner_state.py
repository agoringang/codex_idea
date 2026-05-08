from __future__ import annotations

from typing import Any, Iterable


INACTIVE_RUNNER_TERMS = (
    "出走取消",
    "競走除外",
    "発走除外",
    "取消",
    "除外",
)


def canonical_runner_status(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    compact = text.replace(" ", "").replace("\u3000", "")
    if "競走除外" in compact or "発走除外" in compact or "除外" in compact:
        return "除外"
    if "出走取消" in compact or "取消" in compact:
        return "取消"
    return None


def runner_status_from_tags(tags: Iterable[Any] | None) -> str | None:
    if not tags:
        return None
    for tag in tags:
        status = canonical_runner_status(tag)
        if status:
            return status
    return None


def runner_is_inactive_dict(runner: dict[str, Any]) -> bool:
    if bool(runner.get("scratched")):
        return True
    for key in ("runnerStatus", "runner_status", "status"):
        status = canonical_runner_status(runner.get(key))
        if status:
            return True
    tags = runner.get("tags")
    return runner_status_from_tags(tags if isinstance(tags, list) else None) is not None


def runner_is_inactive_model(runner: Any) -> bool:
    if bool(getattr(runner, "scratched", False)):
        return True
    status = canonical_runner_status(
        getattr(runner, "runner_status", None) or getattr(runner, "runnerStatus", None)
    )
    return status is not None
