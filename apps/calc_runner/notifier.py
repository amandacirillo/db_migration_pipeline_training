"""Notifies whoever is waiting on this order's calculations that they finished (or failed).

Mirrors report-transformation-service's `util.sendStatusMessage(...)` call to an SNS status
topic - fire-and-forget, best-effort notification, not a Step Functions task-token callback (see
stepfunctions_training for that pattern instead). `publish` is injected so tests can assert on
exactly what would have been published without any real SNS/AWS dependency.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, Optional

Publisher = Callable[[Dict[str, Any]], None]


def notify_completed(order_id: str, publish: Publisher, error: Optional[str] = None) -> Dict[str, Any]:
    message = {
        'orderId': order_id,
        'status': 'FAILED' if error else 'SUCCESS',
        'error': error,
    }
    publish(message)
    return message
