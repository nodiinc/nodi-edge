# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from dataclasses import dataclass, field
from queue import Queue, Empty
from typing import Any, Callable, Dict, List, Optional

import psutil

from nodi_libs import MqttClient, MqttTransportType, OtaManager, OtaConfig, OtaStatus

from nodi_edge import App, AppConfig
from nodi_edge.config import OTA_BACKUP_DIR, get_serial_number
from config import CLOUD_SERVER, TOPIC_FORMATS


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Types
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@dataclass
class CloudConfig:
    
    # MQTT connection
    host: str = CLOUD_SERVER.host
    port: int = CLOUD_SERVER.port
    username: Optional[str] = CLOUD_SERVER.username
    password: Optional[str] = CLOUD_SERVER.password
    keepalive: int = CLOUD_SERVER.keepalive
    transport: MqttTransportType = MqttTransportType.TCP

    # Topics
    request_topic: str = TOPIC_FORMATS.request
    response_topic: str = TOPIC_FORMATS.response
    result_topic: str = TOPIC_FORMATS.result
    report_topic: str = TOPIC_FORMATS.report

    # QoS
    subscribe_qos: int = 1
    publish_qos: int = 1
    retain: bool = True

    # Report settings
    report_enabled: bool = True
    report_interval_s: float = 60.0

    # Worker settings
    worker_queue_size: int = 100
    worker_count: int = 2

    # OTA settings
    ota_enabled: bool = True
    ota_backup_dir: str = OTA_BACKUP_DIR
    ota_services: List[str] = field(default_factory=lambda: ["ne-launcher", "ne-monitor"])

    # Connection monitoring (FSM-based reconnection)
    connection_check_cycles: int = 3        # Check connection every N execute cycles
    reconnect_timeout_s: float = CLOUD_SERVER.connection_timeout


@dataclass
class TaskRequest:
    task_id: str
    command: str
    params: Dict[str, Any]
    timestamp: int


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Cloud App
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class CloudApp(App):

    def __init__(self,
                 app_id: str,
                 serial_number: str,
                 cloud_config: Optional[CloudConfig] = None,
                 app_config: Optional[AppConfig] = None):
        super().__init__(app_id, app_config=app_config)

        self._serial_number = serial_number
        self._cloud_config = cloud_config or CloudConfig()

        # MQTT client
        self._mqtt_client: Optional[MqttClient] = None

        # Topics (resolved with serial number)
        self._request_topic = self._cloud_config.request_topic.format(sn=serial_number)
        self._response_topic = self._cloud_config.response_topic.format(sn=serial_number)
        self._result_topic = self._cloud_config.result_topic.format(sn=serial_number)
        self._report_topic = self._cloud_config.report_topic.format(sn=serial_number)

        # Worker queue for non-blocking command processing
        self._task_queue: Queue[Optional[TaskRequest]] = Queue(
            maxsize=self._cloud_config.worker_queue_size)
        self._workers: List[threading.Thread] = []
        self._worker_stop_event = threading.Event()

        # Command handlers
        self._handlers: Dict[str, Callable[[Dict[str, Any]], Dict[str, Any]]] = {}

        # OTA manager
        self._ota_manager: Optional[OtaManager] = None

        # Report data getter (set by user)
        self._report_data_getter: Optional[Callable[[], Dict[str, Any]]] = None

        # Report timing
        self._last_report_time: float = 0.0
        self._report_cycle_count: int = 0

        # Connection monitoring
        self._connection_check_count: int = 0
        self._was_connected: bool = False

        # Register built-in handlers
        self._register_builtin_handlers()

    # ────────────────────────────────────────────────────────────
    # App Lifecycle
    # ────────────────────────────────────────────────────────────

    def on_prepare(self) -> None:
        # Create MQTT client
        client_id = f"ne-cloud-{self._serial_number}"
        self._mqtt_client = MqttClient(client_id=client_id,
                                       host=self._cloud_config.host,
                                       port=self._cloud_config.port,
                                       keepalive=self._cloud_config.keepalive,
                                       transport=self._cloud_config.transport)

        # Setup authentication
        if self._cloud_config.username:
            self._mqtt_client.setup_auth(username=self._cloud_config.username,
                                         password=self._cloud_config.password)

        # Setup callbacks
        self._mqtt_client.set_on_connect(self._on_mqtt_connect)
        self._mqtt_client.set_on_disconnect(self._on_mqtt_disconnect)
        self._mqtt_client.set_on_message(self._on_mqtt_message)

        # Create OTA manager
        if self._cloud_config.ota_enabled:
            from pathlib import Path
            ota_config = OtaConfig(backup_dir=Path(self._cloud_config.ota_backup_dir))
            self._ota_manager = OtaManager(config=ota_config,
                                           on_status_change=self._on_ota_status_change)

    def on_configure(self) -> None:
        pass

    def on_connect(self) -> None:
        # Start workers (if not already running)
        if not self._workers:
            self._worker_stop_event.clear()
            for i in range(self._cloud_config.worker_count):
                worker = threading.Thread(target=self._worker_loop,
                                          daemon=True,
                                          name=f"CloudWorker-{i}")
                worker.start()
                self._workers.append(worker)

        # Connect MQTT client
        result = self._mqtt_client.start(timeout=self._cloud_config.reconnect_timeout_s,
                                         retry=False)
        if not result.ok:
            # Connection failed - raise exception to trigger FSM RECOVER
            raise ConnectionError(f"mqtt connect failed: {result.message}")

        self._was_connected = True
        self._connection_check_count = 0
        self.logger.info(f"mqtt connected: {self._mqtt_client.endpoint}")

    def on_execute(self) -> None:
        # Check MQTT connection periodically
        self._connection_check_count += 1
        if self._connection_check_count >= self._cloud_config.connection_check_cycles:
            self._connection_check_count = 0
            if not self._mqtt_client.is_connected:
                # Connection lost - raise exception to trigger FSM RECOVER
                raise ConnectionError("mqtt connection lost")

        # Publish report periodically
        if self._cloud_config.report_enabled and self._mqtt_client.is_connected:
            self._report_cycle_count += 1
            cycles_per_report = int(self._cloud_config.report_interval_s /
                                    self._app_conf.execute_interval_s)
            if cycles_per_report < 1:
                cycles_per_report = 1

            if self._report_cycle_count >= cycles_per_report:
                self._publish_report()
                self._report_cycle_count = 0

    def on_recover(self) -> None:
        # Try quick reconnect using MqttClient's reconnect
        if self._was_connected and self._mqtt_client:
            self.logger.info("attempting quick reconnect...")
            result = self._mqtt_client.reconnect(timeout=self._cloud_config.reconnect_timeout_s)
            if result.ok:
                self.logger.info("quick reconnect successful")
                return  # Success - FSM will go back to EXECUTE

        # Quick reconnect failed - raise to trigger DISCONNECT → CONNECT cycle
        raise ConnectionError("quick reconnect failed, need full reconnect")

    def on_disconnect(self) -> None:
        # Stop MQTT client (workers stay alive for reconnect)
        if self._mqtt_client:
            self._mqtt_client.stop()
        self._was_connected = False
        self.logger.info("mqtt disconnected, will retry connection")

    def on_manage(self) -> None:
        # Publish connection status
        is_connected = self._mqtt_client.is_connected if self._mqtt_client else False
        self.databus.set_tags({
            f"{self.app_id}/_meta/state": self.current_state.name if self.current_state else "None",
            f"{self.app_id}/_meta/mqtt_connected": is_connected,
            f"{self.app_id}/_meta/exception_count": self.stats.exception_count
        })
        self.databus.apply()

    # ────────────────────────────────────────────────────────────
    # MQTT Callbacks
    # ────────────────────────────────────────────────────────────

    def _on_mqtt_connect(self, client, userdata, flags, reason_code, properties=None):
        if not reason_code.is_failure:
            self.logger.info(f"connected to cloud: {self._mqtt_client.endpoint}")
            # Subscribe to request topic
            self._mqtt_client.subscribe(self._request_topic,
                                        qos=self._cloud_config.subscribe_qos)
        else:
            self.logger.warning(f"connection failed: {reason_code}")

    def _on_mqtt_disconnect(self, client, userdata, flags, reason_code, properties=None):
        self.logger.warning(f"disconnected from cloud: {reason_code}")

    def _on_mqtt_message(self, client, userdata, message):
        try:
            payload = json.loads(message.payload.decode("utf-8"))
            self._handle_request(payload)
        except json.JSONDecodeError as exc:
            self.logger.error(f"invalid json: {exc}")
        except Exception as exc:
            self.logger.error(f"message handling error: {exc}")

    # ────────────────────────────────────────────────────────────
    # Request Handling
    # ────────────────────────────────────────────────────────────

    def _handle_request(self, payload: Dict[str, Any]) -> None:
        task_id = payload.get("task_id", "unknown")
        command = payload.get("command", "")
        params = payload.get("params", {})
        timestamp = payload.get("timestamp", int(time.time() * 1000))

        # Create task request
        task = TaskRequest(task_id=task_id,
                           command=command,
                           params=params,
                           timestamp=timestamp)

        # Send immediate response (accepted)
        self._publish_response(task_id=task_id,
                               status="accepted",
                               command=command)

        # Queue task for worker
        try:
            self._task_queue.put_nowait(task)
        except Exception:
            self._publish_result(task_id=task_id,
                                 status="error",
                                 command=command,
                                 error="queue_full")

    def _publish_response(self,
                          task_id: str,
                          status: str,
                          command: str,
                          data: Optional[Dict[str, Any]] = None,
                          error: Optional[str] = None) -> None:
        payload = {"task_id": task_id,
                   "status": status,
                   "command": command,
                   "timestamp": int(time.time() * 1000)}
        if data:
            payload["data"] = data
        if error:
            payload["error"] = error

        self._mqtt_client.publish(topic=self._response_topic,
                                  payload=json.dumps(payload),
                                  qos=self._cloud_config.publish_qos,
                                  retain=self._cloud_config.retain)

    def _publish_result(self,
                        task_id: str,
                        status: str,
                        command: str,
                        data: Optional[Dict[str, Any]] = None,
                        error: Optional[str] = None) -> None:
        payload = {"task_id": task_id,
                   "status": status,
                   "command": command,
                   "timestamp": int(time.time() * 1000)}
        if data:
            payload["data"] = data
        if error:
            payload["error"] = error

        self._mqtt_client.publish(topic=self._result_topic,
                                  payload=json.dumps(payload),
                                  qos=self._cloud_config.publish_qos,
                                  retain=self._cloud_config.retain)
        self.logger.info(f"task completed: {task_id} ({command}) -> {status}")

    # ────────────────────────────────────────────────────────────
    # Worker
    # ────────────────────────────────────────────────────────────

    def _worker_loop(self) -> None:
        while not self._worker_stop_event.is_set():
            try:
                task = self._task_queue.get(timeout=1.0)
                if task is None:
                    break
                self._process_task(task)
            except Empty:
                continue
            except Exception as exc:
                self.logger.error(f"worker error: {exc}")

    def _process_task(self, task: TaskRequest) -> None:
        handler = self._handlers.get(task.command)
        if not handler:
            self._publish_result(task_id=task.task_id,
                                 status="error",
                                 command=task.command,
                                 error=f"unknown command: {task.command}")
            return

        try:
            result = handler(task.params)
            self._publish_result(task_id=task.task_id,
                                 status="success",
                                 command=task.command,
                                 data=result)
        except Exception as exc:
            self._publish_result(task_id=task.task_id,
                                 status="error",
                                 command=task.command,
                                 error=str(exc))

    # ────────────────────────────────────────────────────────────
    # Command Registration
    # ────────────────────────────────────────────────────────────

    def register_handler(self,
                         command: str,
                         handler: Callable[[Dict[str, Any]], Dict[str, Any]]) -> None:
        self._handlers[command] = handler

    def unregister_handler(self, command: str) -> None:
        self._handlers.pop(command, None)

    # ────────────────────────────────────────────────────────────
    # Report
    # ────────────────────────────────────────────────────────────

    def set_report_data_getter(self,
                               getter: Callable[[], Dict[str, Any]]) -> None:
        self._report_data_getter = getter

    def _publish_report(self) -> None:
        if not self._report_data_getter:
            return

        try:
            data = self._report_data_getter()
            payload = {"serial_number": self._serial_number,
                       "timestamp": int(time.time() * 1000),
                       "data": data}

            self._mqtt_client.publish(topic=self._report_topic,
                                      payload=json.dumps(payload),
                                      qos=self._cloud_config.publish_qos,
                                      retain=self._cloud_config.retain)
        except Exception as exc:
            self.logger.error(f"report publish error: {exc}")

    # ────────────────────────────────────────────────────────────
    # Built-in Handlers
    # ────────────────────────────────────────────────────────────

    def _register_builtin_handlers(self) -> None:
        self.register_handler("ping", self._handle_ping)
        self.register_handler("shell", self._handle_shell)
        self.register_handler("reboot", self._handle_reboot)
        self.register_handler("service_restart", self._handle_service_restart)
        self.register_handler("ota_update", self._handle_ota_update)
        self.register_handler("ota_rollback", self._handle_ota_rollback)
        self.register_handler("ota_status", self._handle_ota_status)

    def _handle_ping(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return {"pong": True, "timestamp": int(time.time() * 1000)}

    def _handle_shell(self, params: Dict[str, Any]) -> Dict[str, Any]:
        command = params.get("command", "")
        timeout = params.get("timeout", 30)

        if not command:
            raise ValueError("command is required")

        try:
            result = subprocess.run(command,
                                    shell=True,
                                    capture_output=True,
                                    text=True,
                                    timeout=timeout)
            return {"stdout": result.stdout,
                    "stderr": result.stderr,
                    "returncode": result.returncode}
        except subprocess.TimeoutExpired:
            raise TimeoutError(f"command timeout after {timeout}s")

    def _handle_reboot(self, params: Dict[str, Any]) -> Dict[str, Any]:
        delay = params.get("delay", 5)
        # Schedule reboot
        threading.Timer(delay, lambda: os.system("sudo reboot")).start()
        return {"scheduled": True, "delay": delay}

    def _handle_service_restart(self, params: Dict[str, Any]) -> Dict[str, Any]:
        service = params.get("service", "")
        if not service:
            raise ValueError("service is required")

        result = subprocess.run(["sudo", "systemctl", "restart", service],
                                capture_output=True,
                                text=True,
                                timeout=30)
        return {"service": service,
                "success": result.returncode == 0,
                "stderr": result.stderr}

    def _handle_ota_update(self, params: Dict[str, Any]) -> Dict[str, Any]:
        if not self._ota_manager:
            raise RuntimeError("OTA not enabled")

        url = params.get("url", "")
        checksum = params.get("checksum", "")
        version = params.get("version", "")
        package_name = params.get("package_name", "nodi-edge")
        services = params.get("services", self._cloud_config.ota_services)

        if not url or not checksum or not version:
            raise ValueError("url, checksum, version are required")

        result = self._ota_manager.execute_update(url=url,
                                                  checksum=checksum,
                                                  version=version,
                                                  package_name=package_name,
                                                  services=services)
        return result.to_dict()

    def _handle_ota_rollback(self, params: Dict[str, Any]) -> Dict[str, Any]:
        if not self._ota_manager:
            raise RuntimeError("OTA not enabled")

        package_name = params.get("package_name", "nodi-edge")
        services = params.get("services", self._cloud_config.ota_services)

        result = self._ota_manager.rollback_to_previous(package_name=package_name,
                                                        services=services)
        return result.to_dict()

    def _handle_ota_status(self, params: Dict[str, Any]) -> Dict[str, Any]:
        if not self._ota_manager:
            raise RuntimeError("OTA not enabled")

        return self._ota_manager.get_status()

    def _on_ota_status_change(self, status: OtaStatus) -> None:
        self.logger.info(f"OTA status: {status.value}")
        # Publish OTA status to cloud
        if self._mqtt_client and self._mqtt_client.is_connected:
            payload = {"type": "ota_status",
                       "status": status.value,
                       "timestamp": int(time.time() * 1000)}
            self._mqtt_client.publish(topic=self._result_topic,
                                      payload=json.dumps(payload),
                                      qos=self._cloud_config.publish_qos)


if __name__ == "__main__":
    cloud_config = CloudConfig(report_interval_s=10.0)
    app_config = AppConfig(execute_interval_s=1.0,
                           retry_delay_s=5.0)
    app = CloudApp(app_id="ne-cloud",
                   serial_number=get_serial_number(),
                   cloud_config=cloud_config,
                   app_config=app_config)

    # Report data getter
    def get_report_data() -> Dict[str, Any]:
        return {"cpu_percent": psutil.cpu_percent(),
                "memory_percent": psutil.virtual_memory().percent}

    app.set_report_data_getter(get_report_data)

    app.start()
