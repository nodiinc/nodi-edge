#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Monitor app - system monitoring (CPU, memory, disk, network, etc.)."""
from __future__ import annotations

import platform
import time
from dataclasses import dataclass
from datetime import datetime
from threading import Thread
from typing import Any, Dict, List, Optional, Tuple, TypeVar, Generic

import psutil

from nodi_edge import App, AppConfig


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Types
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

T = TypeVar("T")


@dataclass(frozen=True)
class Result(Generic[T]):
    ok: bool
    value: Optional[T]
    error: Optional[str] = None

    @staticmethod
    def success(value: T) -> Result[T]:
        return Result(ok=True, value=value)

    @staticmethod
    def failure(error: str) -> Result[T]:
        return Result(ok=False, value=None, error=error)


# Type aliases
CpuLoadInfo = Dict[str, float]
DiskIoInfo = Dict[str, float]
NetworkIoInfo = Dict[str, float]
TemperatureInfo = Dict[str, Dict[str, Dict[str, Optional[float]]]]
TemperatureStats = Dict[str, Dict[str, float]]
BatteryInfo = Dict[str, Any]
SpeedtestInfo = Dict[str, Any]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Constants
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

KB: int = 1024
MB: int = 1024 ** 2
GB: int = 1024 ** 3
MEASURE_DECIMAL: int = 3
PERCENT_DECIMAL: int = 1


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Device Tool
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class DeviceTool:

    def __init__(self) -> None:
        self._cpu_usage_result: Optional[float] = None
        self._speedtest_result: Optional[SpeedtestInfo] = None
        self._prev_net_io: Optional[Tuple[int, int, int, int]] = None
        self._prev_net_time: Optional[float] = None
        self._prev_disk_io: Optional[Tuple[int, int]] = None
        self._prev_disk_time: Optional[float] = None
        self._temperature_stats: TemperatureStats = {}

    # ────────────────────────────────────────────────────────────
    # Static Info
    # ────────────────────────────────────────────────────────────

    def get_time_zone(self) -> Result[str]:
        try:
            _, non_dst_tm = time.tzname
            return Result.success(non_dst_tm)
        except Exception as exc:
            return Result.failure(str(exc))

    def get_system_os_type(self) -> Result[str]:
        try:
            return Result.success(platform.system())
        except Exception as exc:
            return Result.failure(str(exc))

    def get_system_os_version(self) -> Result[str]:
        try:
            info = platform.freedesktop_os_release()
            version = info.get("VERSION")
            if version is None:
                return Result.failure("VERSION not found in os-release")
            return Result.success(version)
        except Exception as exc:
            return Result.failure(str(exc))

    def get_system_kernel_version(self) -> Result[str]:
        try:
            return Result.success(platform.release())
        except Exception as exc:
            return Result.failure(str(exc))

    def get_cpu_architecture(self) -> Result[str]:
        try:
            return Result.success(platform.machine())
        except Exception as exc:
            return Result.failure(str(exc))

    def get_system_libc_version(self) -> Result[str]:
        try:
            info = platform.libc_ver()
            return Result.success("-".join(info))
        except Exception as exc:
            return Result.failure(str(exc))

    def get_system_python_version(self) -> Result[str]:
        try:
            return Result.success(platform.python_version())
        except Exception as exc:
            return Result.failure(str(exc))

    def get_cpu_model(self) -> Result[str]:
        # Try /proc/cpuinfo first (Linux)
        try:
            with open("/proc/cpuinfo", "r") as f:
                for line in f:
                    if line.startswith("model name"):
                        return Result.success(line.split(":")[1].strip())
        except Exception:
            pass
        # Fallback to platform.processor()
        try:
            result = platform.processor()
            if result:
                return Result.success(result)
        except Exception:
            pass
        return Result.failure("cpu model not available")

    def get_cpu_frequency_ghz(self) -> Result[float]:
        try:
            frequency = psutil.cpu_freq()
            if frequency is None:
                return Result.failure("cpu frequency not available")
            return Result.success(round(frequency.max / KB, MEASURE_DECIMAL))
        except Exception as exc:
            return Result.failure(str(exc))

    def get_cpu_core_count(self) -> Result[int]:
        try:
            count = psutil.cpu_count()
            if count is None:
                return Result.failure("cpu count not available")
            return Result.success(count)
        except Exception as exc:
            return Result.failure(str(exc))

    def get_memory_total_gb(self) -> Result[float]:
        try:
            memory = psutil.virtual_memory()
            return Result.success(round(memory.total / GB, MEASURE_DECIMAL))
        except Exception as exc:
            return Result.failure(str(exc))

    def get_swap_total_gb(self) -> Result[float]:
        try:
            swap = psutil.swap_memory()
            return Result.success(round(swap.total / GB, MEASURE_DECIMAL))
        except Exception as exc:
            return Result.failure(str(exc))

    def get_disk_total_gb(self) -> Result[float]:
        try:
            disk = psutil.disk_usage("/")
            return Result.success(round(disk.total / GB, MEASURE_DECIMAL))
        except Exception as exc:
            return Result.failure(str(exc))

    def get_time_system_boot_ts(self) -> Result[str]:
        try:
            boot_ts = psutil.boot_time()
            return Result.success(datetime.fromtimestamp(boot_ts).isoformat())
        except Exception as exc:
            return Result.failure(str(exc))

    def get_network_nic_all(self) -> Result[List[str]]:
        try:
            stats = psutil.net_if_stats()
            return Result.success([iface for iface, info in stats.items() if info.isup])
        except Exception as exc:
            return Result.failure(str(exc))

    # ────────────────────────────────────────────────────────────
    # Dynamic Info
    # ────────────────────────────────────────────────────────────

    def get_cpu_usage_percent(self, interval: float = 1.0) -> Result[float]:
        def _measure(interval: float) -> None:
            try:
                self._cpu_usage_result = psutil.cpu_percent(interval=interval)
            except Exception:
                self._cpu_usage_result = None
        thread = Thread(target=_measure, args=(interval,), daemon=True)
        thread.start()
        if self._cpu_usage_result is None:
            return Result.failure("measurement pending")
        return Result.success(self._cpu_usage_result)

    def get_memory_usage_gb(self) -> Result[float]:
        try:
            memory = psutil.virtual_memory()
            return Result.success(round(memory.used / GB, MEASURE_DECIMAL))
        except Exception as exc:
            return Result.failure(str(exc))

    def get_memory_usage_percent(self) -> Result[float]:
        try:
            memory = psutil.virtual_memory()
            return Result.success(round(memory.percent, PERCENT_DECIMAL))
        except Exception as exc:
            return Result.failure(str(exc))

    def get_swap_usage_gb(self) -> Result[float]:
        try:
            swap = psutil.swap_memory()
            return Result.success(round(swap.used / GB, MEASURE_DECIMAL))
        except Exception as exc:
            return Result.failure(str(exc))

    def get_swap_usage_percent(self) -> Result[float]:
        try:
            swap = psutil.swap_memory()
            return Result.success(round(swap.percent, PERCENT_DECIMAL))
        except Exception as exc:
            return Result.failure(str(exc))

    def get_disk_usage_gb(self) -> Result[float]:
        try:
            disk = psutil.disk_usage("/")
            return Result.success(round(disk.used / GB, MEASURE_DECIMAL))
        except Exception as exc:
            return Result.failure(str(exc))

    def get_disk_usage_percent(self) -> Result[float]:
        try:
            disk = psutil.disk_usage("/")
            return Result.success(round(disk.percent, PERCENT_DECIMAL))
        except Exception as exc:
            return Result.failure(str(exc))

    def get_sensors_temperature(self) -> Result[TemperatureInfo]:
        try:
            data = psutil.sensors_temperatures()
            if not data:
                return Result.failure("no temperature sensors available")
            results: TemperatureInfo = {}
            for board, contents in data.items():
                results[board] = {}
                for entry in contents:
                    label = entry.label if entry.label else "default"
                    results[board][label] = {
                        "curr": entry.current,
                        "high": entry.high,
                        "crit": entry.critical
                    }
            return Result.success(results)
        except Exception as exc:
            return Result.failure(str(exc))

    def get_time_system_uptime_hrs(self) -> Result[float]:
        try:
            boot_ts = psutil.boot_time()
            uptime_sec = time.time() - boot_ts
            return Result.success(round(uptime_sec / 3600, MEASURE_DECIMAL))
        except Exception as exc:
            return Result.failure(str(exc))

    def get_cpu_load_average(self) -> Result[CpuLoadInfo]:
        try:
            load1, load5, load15 = psutil.getloadavg()
            core_count = psutil.cpu_count() or 1
            return Result.success({
                "load_avg_1min": round(load1, MEASURE_DECIMAL),
                "load_avg_5min": round(load5, MEASURE_DECIMAL),
                "load_avg_15min": round(load15, MEASURE_DECIMAL),
                "load_percent_1min": round(load1 / core_count * 100, PERCENT_DECIMAL),
                "load_percent_5min": round(load5 / core_count * 100, PERCENT_DECIMAL),
                "load_percent_15min": round(load15 / core_count * 100, PERCENT_DECIMAL)
            })
        except Exception as exc:
            return Result.failure(str(exc))

    def get_process_count(self) -> Result[int]:
        try:
            return Result.success(len(psutil.pids()))
        except Exception as exc:
            return Result.failure(str(exc))

    def get_thread_count(self) -> Result[int]:
        try:
            total = 0
            for proc in psutil.process_iter(["num_threads"]):
                try:
                    total += proc.info["num_threads"] or 0
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            return Result.success(total)
        except Exception as exc:
            return Result.failure(str(exc))

    def get_network_io_speed(self) -> Result[NetworkIoInfo]:
        try:
            net_io = psutil.net_io_counters()
            current_time = time.time()
            current_data = (net_io.bytes_sent, net_io.bytes_recv,
                            net_io.packets_sent, net_io.packets_recv)
            if self._prev_net_io is None or self._prev_net_time is None:
                self._prev_net_io = current_data
                self._prev_net_time = current_time
                return Result.failure("first measurement, waiting for next cycle")
            elapsed = current_time - self._prev_net_time
            if elapsed <= 0:
                return Result.failure("elapsed time is zero or negative")
            prev_sent, prev_recv, prev_pkt_sent, prev_pkt_recv = self._prev_net_io
            send_mbps = (net_io.bytes_sent - prev_sent) / elapsed / MB * 8
            recv_mbps = (net_io.bytes_recv - prev_recv) / elapsed / MB * 8
            send_pps = (net_io.packets_sent - prev_pkt_sent) / elapsed
            recv_pps = (net_io.packets_recv - prev_pkt_recv) / elapsed
            self._prev_net_io = current_data
            self._prev_net_time = current_time
            return Result.success({
                "send_mbps": round(send_mbps, MEASURE_DECIMAL),
                "recv_mbps": round(recv_mbps, MEASURE_DECIMAL),
                "send_pps": round(send_pps, MEASURE_DECIMAL),
                "recv_pps": round(recv_pps, MEASURE_DECIMAL)
            })
        except Exception as exc:
            return Result.failure(str(exc))

    def get_disk_io_speed(self) -> Result[DiskIoInfo]:
        try:
            disk_io = psutil.disk_io_counters()
            if disk_io is None:
                return Result.failure("disk io counters not available")
            current_time = time.time()
            current_data = (disk_io.read_bytes, disk_io.write_bytes)
            if self._prev_disk_io is None or self._prev_disk_time is None:
                self._prev_disk_io = current_data
                self._prev_disk_time = current_time
                return Result.failure("first measurement, waiting for next cycle")
            elapsed = current_time - self._prev_disk_time
            if elapsed <= 0:
                return Result.failure("elapsed time is zero or negative")
            prev_read, prev_write = self._prev_disk_io
            read_mbps = (disk_io.read_bytes - prev_read) / elapsed / MB * 8
            write_mbps = (disk_io.write_bytes - prev_write) / elapsed / MB * 8
            self._prev_disk_io = current_data
            self._prev_disk_time = current_time
            return Result.success({
                "read_mbps": round(read_mbps, MEASURE_DECIMAL),
                "write_mbps": round(write_mbps, MEASURE_DECIMAL)
            })
        except Exception as exc:
            return Result.failure(str(exc))

    def get_battery(self) -> Result[BatteryInfo]:
        try:
            battery = psutil.sensors_battery()
            if battery is None:
                return Result.failure("battery not available")
            return Result.success({
                "percent": battery.percent,
                "plugged": battery.power_plugged,
                "secs_left": battery.secsleft if battery.secsleft > 0 else None
            })
        except Exception as exc:
            return Result.failure(str(exc))

    def measure_internet_speed(self) -> None:
        def _measure() -> None:
            try:
                import speedtest
                st = speedtest.Speedtest()
                st.get_best_server()
                download = st.download() / MB
                upload = st.upload() / MB
                self._speedtest_result = {
                    "download_mbps": round(download, MEASURE_DECIMAL),
                    "upload_mbps": round(upload, MEASURE_DECIMAL),
                    "measured_ts": datetime.now().isoformat()
                }
            except Exception:
                self._speedtest_result = None
        thread = Thread(target=_measure, daemon=True)
        thread.start()

    def get_internet_speed(self) -> Result[SpeedtestInfo]:
        if self._speedtest_result is None:
            return Result.failure("speedtest not completed")
        return Result.success(self._speedtest_result)

    def get_temperature_stats(self) -> Result[TemperatureStats]:
        sensors_result = self.get_sensors_temperature()
        if not sensors_result.ok:
            if self._temperature_stats:
                return Result.success(self._temperature_stats)
            return Result.failure(sensors_result.error or "no temperature data")
        sensors = sensors_result.value
        if sensors is None:
            return Result.failure("no sensor data")
        for device, components in sensors.items():
            temps = [comp["curr"] for comp in components.values() if comp["curr"] is not None]
            if temps:
                mean_temp = sum(temps) / len(temps)
                std_temp = (sum((t - mean_temp) ** 2 for t in temps) / len(temps)) ** 0.5
                self._temperature_stats[device] = {
                    "mean": round(mean_temp, MEASURE_DECIMAL),
                    "std": round(std_temp, MEASURE_DECIMAL)
                }
        return Result.success(self._temperature_stats)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Monitor App
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class MonitorApp(App):

    def on_prepare(self) -> None:
        self._device = DeviceTool()
        self._static_published: bool = False
        self._speedtest_interval_cycles: int = 1200  # 1200 * 3s = 1 hour
        self._cycle_count: int = 0
        self._app_start_time: float = time.time()

    def on_configure(self) -> None:
        pass

    def on_connect(self) -> None:
        self._static_published = False
        self._cycle_count = 0

    def on_execute(self) -> None:
        # Publish static info (once)
        if not self._static_published:
            self._publish_static_info()
            self._static_published = True

        # Publish dynamic info (every cycle)
        self._publish_dynamic_info()

        # Trigger speedtest periodically (every hour)
        self._cycle_count += 1
        if self._cycle_count % self._speedtest_interval_cycles == 1:
            self._device.measure_internet_speed()
            self.logger.info("speedtest started")

    def on_recover(self) -> None:
        pass

    def on_disconnect(self) -> None:
        pass

    def on_manage(self) -> None:
        self.databus.set_tags({
            f"{self.app_id}/_meta/state": self.current_state.name if self.current_state else "None",
            f"{self.app_id}/_meta/exception_count": self.stats.exception_count
        })
        self.databus.apply()

    # ────────────────────────────────────────────────────────────
    # Internal Methods
    # ────────────────────────────────────────────────────────────

    def _get_value(self, result: Result[T]) -> Optional[T]:
        return result.value if result.ok else None

    def _publish_static_info(self) -> None:
        static_tags: Dict[str, Any] = {
            f"{self.app_id}/cpu/architecture": self._get_value(self._device.get_cpu_architecture()),
            f"{self.app_id}/cpu/core_count": self._get_value(self._device.get_cpu_core_count()),
            f"{self.app_id}/cpu/frequency_ghz": self._get_value(self._device.get_cpu_frequency_ghz()),
            f"{self.app_id}/cpu/model": self._get_value(self._device.get_cpu_model()),
            f"{self.app_id}/disk/total_gb": self._get_value(self._device.get_disk_total_gb()),
            f"{self.app_id}/memory/total_gb": self._get_value(self._device.get_memory_total_gb()),
            f"{self.app_id}/swap/total_gb": self._get_value(self._device.get_swap_total_gb()),
            f"{self.app_id}/system/libc_version": self._get_value(self._device.get_system_libc_version()),
            f"{self.app_id}/system/kernel_version": self._get_value(self._device.get_system_kernel_version()),
            f"{self.app_id}/system/os_type": self._get_value(self._device.get_system_os_type()),
            f"{self.app_id}/system/os_version": self._get_value(self._device.get_system_os_version()),
            f"{self.app_id}/system/python_version": self._get_value(self._device.get_system_python_version()),
            f"{self.app_id}/time/system_boot_ts": self._get_value(self._device.get_time_system_boot_ts()),
            f"{self.app_id}/time/zone": self._get_value(self._device.get_time_zone()),
        }
        # Network interfaces
        nic_result = self._device.get_network_nic_all()
        if nic_result.ok and nic_result.value:
            static_tags[f"{self.app_id}/network/nic_all"] = ",".join(nic_result.value)

        self.databus.set_tags(static_tags)
        self.databus.apply()
        self.logger.info("static info published")

    def _publish_dynamic_info(self) -> None:
        dynamic_tags: Dict[str, Any] = {}

        # CPU
        cpu_result = self._device.get_cpu_usage_percent(self._app_conf.execute_interval_s)
        dynamic_tags[f"{self.app_id}/cpu/usage_percent"] = self._get_value(cpu_result)

        # Memory
        dynamic_tags[f"{self.app_id}/memory/usage_gb"] = self._get_value(self._device.get_memory_usage_gb())
        dynamic_tags[f"{self.app_id}/memory/usage_percent"] = self._get_value(self._device.get_memory_usage_percent())

        # Swap
        dynamic_tags[f"{self.app_id}/swap/usage_gb"] = self._get_value(self._device.get_swap_usage_gb())
        dynamic_tags[f"{self.app_id}/swap/usage_percent"] = self._get_value(self._device.get_swap_usage_percent())

        # Disk
        dynamic_tags[f"{self.app_id}/disk/usage_gb"] = self._get_value(self._device.get_disk_usage_gb())
        dynamic_tags[f"{self.app_id}/disk/usage_percent"] = self._get_value(self._device.get_disk_usage_percent())

        # Disk I/O speed
        disk_io_result = self._device.get_disk_io_speed()
        if disk_io_result.ok and disk_io_result.value:
            dynamic_tags[f"{self.app_id}/disk/read_mbps"] = disk_io_result.value["read_mbps"]
            dynamic_tags[f"{self.app_id}/disk/write_mbps"] = disk_io_result.value["write_mbps"]

        # System uptime
        dynamic_tags[f"{self.app_id}/time/system_uptime_hrs"] = self._get_value(
            self._device.get_time_system_uptime_hrs())

        # App uptime
        app_uptime_hrs = round((time.time() - self._app_start_time) / 3600, MEASURE_DECIMAL)
        dynamic_tags[f"{self.app_id}/time/app_uptime_hrs"] = app_uptime_hrs

        # CPU load average
        cpu_load_result = self._device.get_cpu_load_average()
        if cpu_load_result.ok and cpu_load_result.value:
            cpu_load = cpu_load_result.value
            dynamic_tags[f"{self.app_id}/cpu/load_avg_1min"] = cpu_load["load_avg_1min"]
            dynamic_tags[f"{self.app_id}/cpu/load_avg_5min"] = cpu_load["load_avg_5min"]
            dynamic_tags[f"{self.app_id}/cpu/load_avg_15min"] = cpu_load["load_avg_15min"]
            dynamic_tags[f"{self.app_id}/cpu/load_percent_1min"] = cpu_load["load_percent_1min"]
            dynamic_tags[f"{self.app_id}/cpu/load_percent_5min"] = cpu_load["load_percent_5min"]
            dynamic_tags[f"{self.app_id}/cpu/load_percent_15min"] = cpu_load["load_percent_15min"]

        # Process/Thread count
        dynamic_tags[f"{self.app_id}/process/process_count"] = self._get_value(self._device.get_process_count())
        dynamic_tags[f"{self.app_id}/process/thread_count"] = self._get_value(self._device.get_thread_count())

        # Network I/O speed
        net_io_result = self._device.get_network_io_speed()
        if net_io_result.ok and net_io_result.value:
            net_io = net_io_result.value
            dynamic_tags[f"{self.app_id}/network/send_mbps"] = net_io["send_mbps"]
            dynamic_tags[f"{self.app_id}/network/recv_mbps"] = net_io["recv_mbps"]
            dynamic_tags[f"{self.app_id}/network/send_pps"] = net_io["send_pps"]
            dynamic_tags[f"{self.app_id}/network/recv_pps"] = net_io["recv_pps"]

        # Battery
        battery_result = self._device.get_battery()
        if battery_result.ok and battery_result.value:
            battery = battery_result.value
            dynamic_tags[f"{self.app_id}/battery/percent"] = battery["percent"]
            dynamic_tags[f"{self.app_id}/battery/plugged"] = battery["plugged"]
            if battery["secs_left"]:
                dynamic_tags[f"{self.app_id}/battery/mins_left"] = round(battery["secs_left"] / 60)

        # Temperature
        temp_result = self._device.get_temperature_stats()
        if temp_result.ok and temp_result.value:
            for device, stats in temp_result.value.items():
                tag_key = f"{self.app_id}/temp/{device}_c"
                tag_value = f"{stats['mean']:.1f} ± {stats['std']:.1f}"
                dynamic_tags[tag_key] = tag_value

        # Internet speed (from periodic measurement)
        internet_result = self._device.get_internet_speed()
        if internet_result.ok and internet_result.value:
            internet = internet_result.value
            dynamic_tags[f"{self.app_id}/internet/download_mbps"] = internet["download_mbps"]
            dynamic_tags[f"{self.app_id}/internet/upload_mbps"] = internet["upload_mbps"]
            dynamic_tags[f"{self.app_id}/internet/measured_ts"] = internet["measured_ts"]

        self.databus.set_tags(dynamic_tags)
        self.databus.apply()


if __name__ == "__main__":
    app = MonitorApp("monitor", app_config=AppConfig(execute_interval_s=3.0))
    app.start()
