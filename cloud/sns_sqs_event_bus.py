"""SNS/SQS-backed EventBus -- drop-in replacement for saga_bench.event_bus.EventBus.

Each logical topic maps to an SNS topic. Each subscriber gets its own SQS
queue subscribed to that SNS topic. A background polling thread per queue
delivers messages to the callback.

For the demo, this proves the EventBus abstraction maps cleanly to real AWS
messaging. Path B uses it for the CompensationNeeded fanout.
"""
from __future__ import annotations

import json
import threading
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Callable, Dict, List, Optional

from cloud.config import LOCALSTACK_ENDPOINT, AWS_REGION, get_client

Subscriber = Callable[[dict], None]


class _Subscription:
    """One subscriber's SQS queue + polling thread."""

    def __init__(
        self,
        sqs_client,
        queue_url: str,
        callback: Subscriber,
        executor: ThreadPoolExecutor,
    ) -> None:
        self.sqs = sqs_client
        self.queue_url = queue_url
        self.callback = callback
        self.executor = executor
        self._stop = threading.Event()
        self._futures: List[Future] = []
        self._thread = threading.Thread(target=self._poll, daemon=True)
        self._thread.start()

    def _poll(self) -> None:
        while not self._stop.is_set():
            try:
                resp = self.sqs.receive_message(
                    QueueUrl=self.queue_url,
                    MaxNumberOfMessages=10,
                    WaitTimeSeconds=1,
                )
            except Exception:
                if self._stop.is_set():
                    return
                continue

            for msg in resp.get("Messages", []):
                try:
                    body = json.loads(msg["Body"])
                    if "Message" in body:
                        payload = json.loads(body["Message"])
                    else:
                        payload = body
                except (json.JSONDecodeError, KeyError):
                    payload = {}

                fut = self.executor.submit(self.callback, payload)
                self._futures.append(fut)

                self.sqs.delete_message(
                    QueueUrl=self.queue_url,
                    ReceiptHandle=msg["ReceiptHandle"],
                )

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=3)

    @property
    def futures(self) -> List[Future]:
        return self._futures


class SnsSqsEventBus:
    def __init__(
        self,
        endpoint_url: str = LOCALSTACK_ENDPOINT,
        max_workers: int = 32,
    ) -> None:
        self._endpoint = endpoint_url
        self._sns = get_client("sns", endpoint_url)
        self._sqs = get_client("sqs", endpoint_url)
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._topic_arns: Dict[str, str] = {}
        self._subscriptions: Dict[str, List[_Subscription]] = {}
        self._lock = threading.Lock()

    def _ensure_topic(self, topic: str) -> str:
        if topic in self._topic_arns:
            return self._topic_arns[topic]
        safe_name = topic.replace(":", "-").replace(".", "-")[:256]
        resp = self._sns.create_topic(Name=safe_name)
        arn = resp["TopicArn"]
        self._topic_arns[topic] = arn
        return arn

    def subscribe(self, topic: str, callback: Subscriber) -> None:
        with self._lock:
            topic_arn = self._ensure_topic(topic)

            queue_name = f"saga-sub-{uuid.uuid4().hex[:8]}"
            queue_resp = self._sqs.create_queue(QueueName=queue_name)
            queue_url = queue_resp["QueueUrl"]

            queue_arn_resp = self._sqs.get_queue_attributes(
                QueueUrl=queue_url, AttributeNames=["QueueArn"]
            )
            queue_arn = queue_arn_resp["Attributes"]["QueueArn"]

            self._sqs.set_queue_attributes(
                QueueUrl=queue_url,
                Attributes={
                    "Policy": json.dumps({
                        "Version": "2012-10-17",
                        "Statement": [{
                            "Effect": "Allow",
                            "Principal": "*",
                            "Action": "sqs:SendMessage",
                            "Resource": queue_arn,
                            "Condition": {"ArnEquals": {"aws:SourceArn": topic_arn}},
                        }],
                    })
                },
            )

            self._sns.subscribe(
                TopicArn=topic_arn,
                Protocol="sqs",
                Endpoint=queue_arn,
            )

            sub = _Subscription(self._sqs, queue_url, callback, self._executor)
            self._subscriptions.setdefault(topic, []).append(sub)

    def publish(self, topic: str, payload: dict) -> List[Future]:
        with self._lock:
            topic_arn = self._ensure_topic(topic)
            subs = list(self._subscriptions.get(topic, []))

        self._sns.publish(
            TopicArn=topic_arn,
            Message=json.dumps(payload),
        )

        import time
        deadline = time.time() + 5.0
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
            time.sleep(0.01)

        for s in subs:
            if len(s.futures) > expected[id(s)]:
                futures.append(s.futures[-1])

        return futures

    def shutdown(self, wait: bool = True) -> None:
        with self._lock:
            for topic_subs in self._subscriptions.values():
                for sub in topic_subs:
                    sub.stop()
        self._executor.shutdown(wait=wait)
