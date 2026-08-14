"""Pub/Sub publish helper and push-subscription envelope decoding."""
from __future__ import annotations

import base64
import json
import os

from google.cloud import pubsub_v1

from pipeline.common.models import ShotEvent

_publisher = pubsub_v1.PublisherClient()
_project_id = os.environ.get("GCP_PROJECT_ID", "")


def topic_path(topic_name: str) -> str:
    return _publisher.topic_path(_project_id, topic_name)


def publish_shot_event(topic_name: str, event: ShotEvent) -> None:
    _publisher.publish(topic_path(topic_name), event.model_dump_json().encode("utf-8"))


def decode_push_envelope(body: dict) -> ShotEvent:
    """Cloud Run Pub/Sub push endpoints receive a wrapped, base64-encoded envelope."""
    data = base64.b64decode(body["message"]["data"])
    return ShotEvent(**json.loads(data))
