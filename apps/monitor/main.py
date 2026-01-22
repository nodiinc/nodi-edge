#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import time
from datetime import datetime
from typing import Any, Dict, Optional, TypeVar

from nodi_libs import SystemInfo, Result

from nodi_edge import App, AppConfig


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Constants
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

MEASURE_DECIMAL: int = 3

T = TypeVar("T")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Monitor App
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class MonitorApp(App):

    def on_prepare(self) -> None:
        self._sysinfo = SystemInfo()
        self._static_published: bool = False
        self._speedtest_interval_cycles: int = 1200  # 1200 * 3s = 1 hour
        self._speedtest_cycle_count: int = 0
        self._app_start_time: float = time.time()

    def on_configure(self) -> None:
        pass

    def on_connect(self) -> None:
        self._static_published = False
        self._speedtest_cycle_count = 0
        self._sysinfo.measure_internet_speed()
        self.logger.info("speedtest started (on connect)")

    def on_execute(self) -> None:
        if not self._static_published:
            self._publish_static_info()
            self._static_published = True

        self._publish_dynamic_info()

        self._speedtest_cycle_count += 1
        if self._speedtest_cycle_count >= self._speedtest_interval_cycles:
            self._sysinfo.measure_internet_speed()
            self._speedtest_cycle_count = 0
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
            f"{self.app_id}/cpu/architecture": self._get_value(self._sysinfo.get_cpu_architecture()),
            f"{self.app_id}/cpu/core_count": self._get_value(self._sysinfo.get_cpu_core_count()),
            f"{self.app_id}/cpu/frequency_ghz": self._get_value(self._sysinfo.get_cpu_frequency_ghz()),
            f"{self.app_id}/cpu/model": self._get_value(self._sysinfo.get_cpu_model()),
            f"{self.app_id}/disk/total_gb": self._get_value(self._sysinfo.get_disk_total_gb()),
            f"{self.app_id}/memory/total_gb": self._get_value(self._sysinfo.get_memory_total_gb()),
            f"{self.app_id}/swap/total_gb": self._get_value(self._sysinfo.get_swap_total_gb()),
            f"{self.app_id}/system/libc_version": self._get_value(self._sysinfo.get_system_libc_version()),
            f"{self.app_id}/system/kernel_version": self._get_value(self._sysinfo.get_system_kernel_version()),
            f"{self.app_id}/system/os_type": self._get_value(self._sysinfo.get_system_os_type()),
            f"{self.app_id}/system/os_version": self._get_value(self._sysinfo.get_system_os_version()),
            f"{self.app_id}/system/python_version": self._get_value(self._sysinfo.get_system_python_version()),
            f"{self.app_id}/time/app_start_ts": datetime.fromtimestamp(self._app_start_time).isoformat(),
            f"{self.app_id}/time/system_boot_ts": self._get_value(self._sysinfo.get_time_system_boot_ts()),
            f"{self.app_id}/time/zone": self._get_value(self._sysinfo.get_time_zone()),
        }
        # Network interfaces
        nic_result = self._sysinfo.get_network_nic_all()
        if nic_result.ok and nic_result.value:
            static_tags[f"{self.app_id}/network/nic_all"] = ",".join(nic_result.value)

        self.databus.set_tags(static_tags)
        self.databus.apply()
        self.logger.info("static info published")

    def _publish_dynamic_info(self) -> None:
        dynamic_tags: Dict[str, Any] = {}

        # CPU
        cpu_result = self._sysinfo.get_cpu_usage_percent(self._app_conf.execute_interval_s)
        dynamic_tags[f"{self.app_id}/cpu/usage_percent"] = self._get_value(cpu_result)

        # Memory
        dynamic_tags[f"{self.app_id}/memory/usage_gb"] = self._get_value(self._sysinfo.get_memory_usage_gb())
        dynamic_tags[f"{self.app_id}/memory/usage_percent"] = self._get_value(self._sysinfo.get_memory_usage_percent())

        # Swap
        dynamic_tags[f"{self.app_id}/swap/usage_gb"] = self._get_value(self._sysinfo.get_swap_usage_gb())
        dynamic_tags[f"{self.app_id}/swap/usage_percent"] = self._get_value(self._sysinfo.get_swap_usage_percent())

        # Disk
        dynamic_tags[f"{self.app_id}/disk/usage_gb"] = self._get_value(self._sysinfo.get_disk_usage_gb())
        dynamic_tags[f"{self.app_id}/disk/usage_percent"] = self._get_value(self._sysinfo.get_disk_usage_percent())

        # Disk I/O speed
        disk_io_result = self._sysinfo.get_disk_io_speed()
        if disk_io_result.ok and disk_io_result.value:
            dynamic_tags[f"{self.app_id}/disk/read_mbps"] = disk_io_result.value["read_mbps"]
            dynamic_tags[f"{self.app_id}/disk/write_mbps"] = disk_io_result.value["write_mbps"]

        # System uptime
        dynamic_tags[f"{self.app_id}/time/system_uptime_hrs"] = self._get_value(
            self._sysinfo.get_time_system_uptime_hrs())

        # App uptime
        app_uptime_hrs = round((time.time() - self._app_start_time) / 3600, MEASURE_DECIMAL)
        dynamic_tags[f"{self.app_id}/time/app_uptime_hrs"] = app_uptime_hrs

        # CPU load average
        cpu_load_result = self._sysinfo.get_cpu_load_average()
        if cpu_load_result.ok and cpu_load_result.value:
            cpu_load = cpu_load_result.value
            dynamic_tags[f"{self.app_id}/cpu/load_avg_1min"] = cpu_load["load_avg_1min"]
            dynamic_tags[f"{self.app_id}/cpu/load_avg_5min"] = cpu_load["load_avg_5min"]
            dynamic_tags[f"{self.app_id}/cpu/load_avg_15min"] = cpu_load["load_avg_15min"]
            dynamic_tags[f"{self.app_id}/cpu/load_percent_1min"] = cpu_load["load_percent_1min"]
            dynamic_tags[f"{self.app_id}/cpu/load_percent_5min"] = cpu_load["load_percent_5min"]
            dynamic_tags[f"{self.app_id}/cpu/load_percent_15min"] = cpu_load["load_percent_15min"]

        # Process/Thread count
        dynamic_tags[f"{self.app_id}/process/process_count"] = self._get_value(self._sysinfo.get_process_count())
        dynamic_tags[f"{self.app_id}/process/thread_count"] = self._get_value(self._sysinfo.get_thread_count())

        # Network I/O speed
        net_io_result = self._sysinfo.get_network_io_speed()
        if net_io_result.ok and net_io_result.value:
            net_io = net_io_result.value
            dynamic_tags[f"{self.app_id}/network/send_mbps"] = net_io["send_mbps"]
            dynamic_tags[f"{self.app_id}/network/recv_mbps"] = net_io["recv_mbps"]
            dynamic_tags[f"{self.app_id}/network/send_pps"] = net_io["send_pps"]
            dynamic_tags[f"{self.app_id}/network/recv_pps"] = net_io["recv_pps"]

        # Battery
        battery_result = self._sysinfo.get_battery()
        if battery_result.ok and battery_result.value:
            battery = battery_result.value
            dynamic_tags[f"{self.app_id}/battery/percent"] = battery["percent"]
            dynamic_tags[f"{self.app_id}/battery/plugged"] = battery["plugged"]
            if battery["secs_left"]:
                dynamic_tags[f"{self.app_id}/battery/mins_left"] = round(battery["secs_left"] / 60)

        # Temperature
        temp_result = self._sysinfo.get_temperature_stats()
        if temp_result.ok and temp_result.value:
            for device, stats in temp_result.value.items():
                tag_key = f"{self.app_id}/temp/{device}_c"
                tag_value = f"{stats['mean']:.1f} ± {stats['std']:.1f}"
                dynamic_tags[tag_key] = tag_value

        # Internet speed (from periodic measurement)
        internet_result = self._sysinfo.get_internet_speed()
        if internet_result.ok and internet_result.value:
            internet = internet_result.value
            dynamic_tags[f"{self.app_id}/internet/download_mbps"] = internet["download_mbps"]
            dynamic_tags[f"{self.app_id}/internet/upload_mbps"] = internet["upload_mbps"]
            dynamic_tags[f"{self.app_id}/internet/measured_ts"] = internet["measured_ts"]

        self.databus.set_tags(dynamic_tags)
        self.databus.apply()


if __name__ == "__main__":
    app_config = AppConfig(execute_interval_s=3.0, manage_interval_s=1.0)
    app = MonitorApp("monitor", app_config=app_config)
    app.start()
