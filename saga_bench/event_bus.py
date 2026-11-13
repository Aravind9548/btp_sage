"""In-process publish/subscribe event bus.

Models a message broker (e.g. an SNS topic or Kafka topic) without any
network hop: subscribers are plain Python callables, and "concurrent
delivery" is a thread pool instead of separate consumer processes.
"""
from __future__ import annotations

import threading
from collections import defaultdict
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Callable, DefaultDict, List

Subscriber = Callable[[dict], None]


class EventBus:
    def __init__(self, max_workers: int = 32) -> None:
        self._subscribers: DefaultDict[str, List[Subscriber]] = defaultdict(list)
        self._lock = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=max_workers)

    def subscribe(self, topic: str, callback: Subscriber) -> None:
        with self._lock:
            self._subscribers[topic].append(callback)

    def unsubscribe(self, topic: str, callback: Subscriber) -> None:
        with self._lock:
            subs = self._subscribers.get(topic, [])
            if callback in subs:
                subs.remove(callback)

    def publish(self, topic: str, payload: dict) -> List[Future]:
        """Dispatch payload to every subscriber of topic on the thread pool.

        Returns the list of futures so callers that need to wait for
        delivery (tests, deterministic replay) can do so; callers that want
        fire-and-forget semantics (the choreography paths) can ignore them.
        """
        with self._lock:
            subs = list(self._subscribers.get(topic, []))
        return [self._executor.submit(callback, payload) for callback in subs]

    def shutdown(self, wait: bool = True) -> None:
        self._executor.shutdown(wait=wait)
