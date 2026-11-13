"""Kafka-backed EventBus -- drop-in replacement for saga_bench.event_bus.EventBus.

Each logical topic maps to a Kafka topic. Each subscriber gets messages via
a KafkaConsumer in a background thread using manual partition assignment
(no consumer groups, no rebalance delay).

This proves the EventBus abstraction maps cleanly to Kafka, the industry
standard for event-driven microservices.
"""
from __future__ import annotations

import json
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Callable, Dict, List

from kafka import KafkaProducer, KafkaConsumer, TopicPartition
from kafka.admin import KafkaAdminClient, NewTopic
from kafka.errors import TopicAlreadyExistsError

Subscriber = Callable[[dict], None]

KAFKA_BOOTSTRAP = "localhost:9092"


class _KafkaSubscription:
    """One subscriber's consumer thread with manual partition assignment."""

    def __init__(
        self,
        topic: str,
        callback: Subscriber,
        executor: ThreadPoolExecutor,
        bootstrap_servers: str,
    ) -> None:
        self.callback = callback
        self.executor = executor
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._futures: List[Future] = []
        self._topic = topic
        self._bootstrap = bootstrap_servers
        self._thread = threading.Thread(target=self._poll, daemon=True)
        self._thread.start()

    def wait_ready(self, timeout: float = 10.0) -> None:
        self._ready.wait(timeout)

    def _poll(self) -> None:
        consumer = KafkaConsumer(
            bootstrap_servers=self._bootstrap,
            enable_auto_commit=False,
            value_deserializer=lambda m: json.loads(m.decode("utf-8")),
        )
        tp = TopicPartition(self._topic, 0)
        consumer.assign([tp])
        consumer.seek_to_end(tp)
        consumer.position(tp)  # forces offset fetch to complete
        self._ready.set()

        while not self._stop.is_set():
            try:
                records = consumer.poll(timeout_ms=500)
                for _, messages in records.items():
                    for msg in messages:
                        fut = self.executor.submit(self.callback, msg.value)
                        self._futures.append(fut)
            except Exception:
                if self._stop.is_set():
                    return
        try:
            consumer.close(autocommit=False)
        except Exception:
            pass

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=3)

    @property
    def futures(self) -> List[Future]:
        return self._futures


class KafkaEventBus:
    def __init__(
        self,
        bootstrap_servers: str = KAFKA_BOOTSTRAP,
        max_workers: int = 32,
    ) -> None:
        self._bootstrap = bootstrap_servers
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._producer = KafkaProducer(
            bootstrap_servers=bootstrap_servers,
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        )
        self._admin = KafkaAdminClient(bootstrap_servers=bootstrap_servers)
        self._subscriptions: Dict[str, List[_KafkaSubscription]] = {}
        self._ensured_topics: set = set()
        self._lock = threading.Lock()

    def _ensure_topic(self, safe_topic: str) -> None:
        if safe_topic in self._ensured_topics:
            return
        try:
            self._admin.create_topics([NewTopic(safe_topic, num_partitions=1, replication_factor=1)])
        except TopicAlreadyExistsError:
            pass
        self._ensured_topics.add(safe_topic)

    def subscribe(self, topic: str, callback: Subscriber) -> None:
        import time
        safe_topic = topic.replace(":", "-").replace(".", "-")
        self._ensure_topic(safe_topic)
        sub = _KafkaSubscription(
            safe_topic, callback, self._executor, self._bootstrap,
        )
        sub.wait_ready(timeout=10.0)
        time.sleep(0.1)  # let poll loop start before returning
        with self._lock:
            self._subscriptions.setdefault(topic, []).append(sub)

    def publish(self, topic: str, payload: dict) -> List[Future]:
        safe_topic = topic.replace(":", "-").replace(".", "-")
        with self._lock:
            subs = list(self._subscriptions.get(topic, []))

        self._producer.send(safe_topic, value=payload)
        self._producer.flush()

        import time
        deadline = time.time() + 10.0
        futures: List[Future] = []
        expected = {id(s): len(s.futures) for s in subs}
        while time.time() < deadline:
            all_arrived = True
            for s in subs:
                if len(s.futures) <= expected[id(s)]:
                    all_arrived = False
                    break
            if all_arrived:
                break
            time.sleep(0.05)

        for s in subs:
            if len(s.futures) > expected[id(s)]:
                futures.append(s.futures[-1])

        return futures

    def shutdown(self, wait: bool = True) -> None:
        with self._lock:
            for topic_subs in self._subscriptions.values():
                for sub in topic_subs:
                    sub.stop()
        try:
            self._producer.close(timeout=2)
        except Exception:
            pass
        try:
            self._admin.close()
        except Exception:
            pass
        self._executor.shutdown(wait=wait)
