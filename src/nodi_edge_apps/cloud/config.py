# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CloudServerConfig:
    host: str = "43.202.161.226"
    port: int = 1883
    username: str = "nodi"
    password: str = "PASS00371"
    keepalive: int = 30
    connection_timeout: float = 10.0

CLOUD_SERVER = CloudServerConfig()


@dataclass
class TopicFormats:
    report: str = "/ne/{sn}/report"
    request: str = "/ne/{sn}/request"
    response: str = "/ne/{sn}/response"
    result: str = "/ne/{sn}/result"

TOPIC_FORMATS = TopicFormats()
