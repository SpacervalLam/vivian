import math
import os
import random
import sys
import time

class _Suppressor:
    def __init__(self):
        self._old_stdout = sys.stdout
        self._old_stderr = sys.stderr
        self._devnull = open(os.devnull, 'w')
    def __enter__(self):
        sys.stdout = sys.stderr = self._devnull
        return self
    def __exit__(self, *args):
        sys.stdout = self._old_stdout
        sys.stderr = self._old_stderr
        self._devnull.close()

with _Suppressor():
    import live2d.v3 as live2d

import psutil
from loguru import logger
from OpenGL.GL import (GL_COLOR_BUFFER_BIT, GL_DEPTH_BUFFER_BIT, GL_DEPTH_TEST,
                       GL_BLEND, GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA,
                       glClear, glClearColor, glViewport, glEnable, glBlendFunc)
from PyQt5.QtCore import QMetaObject, QPoint, Qt, QThread, QTimer, pyqtSignal
from PyQt5.QtGui import QCursor
from PyQt5.QtWidgets import QMessageBox, QOpenGLWidget

from utils.config import BASE_DIR, LIVE2D_RENDER_CONFIG, MODEL_PATH


class BehaviorWorker(QThread):
    """行为决策工作线程"""

    result_ready = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, brain, cpu, mem, last_action, timeout_sec=2.0):
        """
        初始化
        
        Args:
            brain: Brain实例
            cpu: CPU使用率
            mem: 内存使用率
            last_action: 上一个动作
            timeout_sec: 超时时间（秒）
        """
        super().__init__()
        self.brain = brain
        self.cpu = cpu
        self.mem = mem
        self.last_action = last_action
        self.timeout_sec = timeout_sec

    def run(self):
        """运行模型推理"""
        try:
            logger.debug(
                f"BehaviorWorker开始运行，CPU: {self.cpu}%, 内存: {self.mem}%, 上一个动作: {self.last_action}"
            )

            # 使用本地模型生成行为决策
            decision = self.brain.get_behavior_decision(
                self.cpu, self.mem, self.last_action
            )

            logger.debug(f"BehaviorWorker获取到决策: {repr(decision)}")

            if not isinstance(decision, dict):
                self.error.emit(f"Invalid decision format: {repr(decision)}")
                return

            self.result_ready.emit(decision)
        except Exception as e:
            logger.error(f"BehaviorWorker异常: {type(e).__name__}: {repr(e)}")
            import traceback

            logger.error(f"异常堆栈: {traceback.format_exc()}")
            self.error.emit(f"{type(e).__name__}: {str(e)}")


class Live2DWidget(QOpenGLWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.model = None
        self.resize(800, 1000)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_model_angle)
        self.timer.start(16)

        self.is_mouse_follow_enabled = True
        self.is_avoid_mouse_enabled = False
        self.avoid_distance_threshold = 100
        self.avoid_speed = 50
        self.avoid_margin = 50
        
        self.last_cursor_pos = None
        self.target_angle_x = 0.0
        self.target_angle_y = 0.0
        self.current_angle_x = 0.0
        self.current_angle_y = 0.0
        self.angle_smooth_speed = LIVE2D_RENDER_CONFIG.get("smooth_speed", 0.1)

        self.last_wander_time = 0
        self.wander_interval = 3.0
        self.wander_target_x = 0.0
        self.wander_target_y = 0.0

        self.click_count = 0
        self.last_click_time = 0
        self.is_panicked = False

        self.target_mouth_open = 0.15
        self.current_mouth_open = 0.15
        self.mouth_smooth_speed = LIVE2D_RENDER_CONFIG.get("mouth_smooth_speed", 0.005)
        self.breath_timer = 0
        self.breath_interval = LIVE2D_RENDER_CONFIG.get("breath_interval", 150)
        self.min_open_value = 0.1
        self.max_open_value = 0.3

        self.target_arm_left = -5.0
        self.current_arm_left = -5.0
        self.target_arm_right = -5.0
        self.current_arm_right = -5.0

        self.eye_open = 1.0
        self.target_eye_open = 1.0
        self.eye_smooth_speed = LIVE2D_RENDER_CONFIG.get("eye_smooth_speed", 0.25)
        self.blink_timer = 0
        self.blink_interval = random.randint(
            LIVE2D_RENDER_CONFIG.get("blink_interval", 500) - 200,
            LIVE2D_RENDER_CONFIG.get("blink_interval", 500) + 300,
        )
        self.blink_duration = 8

        self.current_arm_left = -5.0
        self.current_arm_right = -5.0

        self.is_ctrl_mouse_pressed = False

        self._external_managers = {}

        self.model_area = {
            "x1": 0.35,  # 左上角相对坐标
            "y1": 0.05,
            "x2": 0.65,  # 右下角相对坐标
            "y2": 0.95,
        }

        self.interaction_areas = {
            "head": {
                # 原宽度: 0.65 - 0.35 = 0.3
                # 新宽度: 0.3 * 0.5 = 0.15
                # 中心位置: 0.5
                # 新x1: 0.5 - 0.15/2 = 0.425
                # 新x2: 0.5 + 0.15/2 = 0.575
                "x1": 0.425,
                "y1": 0.1,  # 左上角相对坐标
                "x2": 0.575,
                "y2": 0.35,  # 右下角相对坐标
            },
            "body": {
                # 原宽度: 0.7 - 0.3 = 0.4
                # 新宽度: 0.4 * 0.5 = 0.2
                # 中心位置: 0.5
                # 新x1: 0.5 - 0.2/2 = 0.4
                # 新x2: 0.5 + 0.2/2 = 0.6
                "x1": 0.4,
                "y1": 0.35,
                "x2": 0.6,
                "y2": 0.75,
            },
            "umbrella": {
                # 原宽度: 0.45 - 0.25 = 0.2
                # 新宽度: 0.2 * 0.5 = 0.1
                # 中心位置: (0.25 + 0.45) / 2 = 0.35
                # 新x1: 0.35 - 0.1/2 = 0.3
                # 新x2: 0.35 + 0.1/2 = 0.4
                "x1": 0.3,
                "y1": 0.1,
                "x2": 0.4,
                "y2": 0.6,
            },
        }

        self.click_history = []
        self.click_window = 0.6

        # --- 新增动态行为调度器 ---
        self.behavior_timer = QTimer(self)
        self.behavior_timer.timeout.connect(self._auto_behavior_tick)
        self.current_frequency = "medium"
        self.last_action = "idle"
        self.behavior_timer.start(3000)
        self.is_playing_action = False
        self.target_angle_z = 0.0
        self.current_angle_z = 0.0

        self.auto_think_timer = QTimer(self)
        self.auto_think_timer.timeout.connect(self._auto_think)
        from utils.config_manager import config_manager
        self.auto_think_enabled = config_manager.get("ai.enable_local_proactive", False)
        self.auto_think_timer.start(10000)

        self._behavior_worker = None

        self._cpu_ema = None
        self._mem_ema = None
        self._ema_alpha = 0.3
        self._last_freq_change_time = 0
        self._min_freq_change_interval = 10.0

        self.last_think_time = time.time()
        self.auto_think_interval = 10.0
       self.auto_think_priority = "medium"

        self.is_moving = False
        self.start_pos = None
        self.target_pos = None
        self.current_pos = None
        self.move_progress = 0.0
        self.move_duration = 1000
        self.move_timer = QTimer(self)
        self.move_timer.timeout.connect(self._smooth_move_step)
        self.move_start_time = 0

        self.is_resizing = False
        self.start_size = None
        self.target_size = None
        self.current_size = None
        self.resize_progress = 0.0
        self.resize_timer = None
        self.resize_start_time = 0

        self.is_asleep = False

    def set_managers(
        self,
        resource_loader=None,
        expression_manager=None,
        animation_manager=None,
        state_machine=None,
        sound_manager=None,
    ):
        self._external_managers["resource_loader"] = resource_loader
        self._external_managers["expression_manager"] = expression_manager
        self._external_managers["animation_manager"] = animation_manager
        self._external_managers["state_machine"] = state_machine
        self._external_managers["sound_manager"] = sound_manager

        if expression_manager:
            expression_manager.set_revert_callback(self._on_expression_reverted)
        
        if animation_manager:
            animation_manager.set_on_frame_callback(self._apply_motion_frame)

    def _on_expression_reverted(self, expression_name):
        pass
    
    def _apply_motion_frame(self, params: dict):
        """应用动作帧参数到模型"""
        if self.model:
            for param_id, value in params.items():
                self.model.SetParameterValue(param_id, value, 1.0)

    def set_asleep(self, asleep: bool):
        """设置睡眠状态"""
        self.is_asleep = asleep
        if asleep:
            logger.info("薇薇安进入了深度睡眠...")
        else:
            logger.info("薇薇安苏醒了！")

    def initializeGL(self):
        try:
            glEnable(GL_DEPTH_TEST)
            glEnable(GL_BLEND)
            try:
                glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
            except Exception:
                logger.warning("glBlendFunc不可用，跳过混合设置")
            
            live2d.glInit()
            live2d.init()

            self.model = live2d.LAppModel()

            self.model.LoadModelJson(MODEL_PATH)

            self.model.Resize(self.width(), self.height())

            logger.debug("Live2D模型初始化完成")

        except Exception as e:
            logger.error(f"Live2D模型加载失败: {e}")
            QMessageBox.critical(self, "加载模型失败", f"模型文件加载失败: {e}")
            return

    def resizeGL(self, width, height):
        glViewport(0, 0, width, height)
        if self.model:
            self.model.Resize(width, height)

    def paintGL(self):
        try:
            from OpenGL.error import GLError
            
            try:
                glClearColor(0, 0, 0, 0)
                glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
            except GLError:
                pass
            
            if self.model:
                try:
                    expression_manager = self._external_managers.get("expression_manager")
                    if expression_manager:
                        current_expr = expression_manager.get_current_expression()
                        if current_expr:
                            if current_expr == "shy":
                                self.model.SetParameterValue("Param149", 1.0, 1.0)
                                self.model.SetParameterValue("Param132", 0.0, 1.0)
                                self.model.SetParameterValue("Param135", 0.0, 1.0)
                                self.model.SetParameterValue("Param144", 0.0, 1.0)
                                self.model.SetParameterValue("Param140", 0.0, 1.0)
                                self.model.SetParameterValue("Param150", 0.0, 1.0)
                            elif current_expr == "panic":
                                self.model.SetParameterValue("Param132", 1.0, 1.0)
                                self.model.SetParameterValue("Param149", 0.0, 1.0)
                                self.model.SetParameterValue("Param135", 0.0, 1.0)
                                self.model.SetParameterValue("Param144", 0.0, 1.0)
                                self.model.SetParameterValue("Param140", 0.0, 1.0)
                                self.model.SetParameterValue("Param150", 0.0, 1.0)
                            elif current_expr == "eye_roll":
                                self.model.SetParameterValue("Param135", 1.0, 1.0)
                                self.model.SetParameterValue("Param132", 0.0, 1.0)
                                self.model.SetParameterValue("Param149", 0.0, 1.0)
                                self.model.SetParameterValue("Param144", 0.0, 1.0)
                                self.model.SetParameterValue("Param140", 0.0, 1.0)
                                self.model.SetParameterValue("Param150", 0.0, 1.0)
                            elif current_expr == "cry":
                                self.model.SetParameterValue("Param144", 1.0, 1.0)
                                self.model.SetParameterValue("Param132", 0.0, 1.0)
                                self.model.SetParameterValue("Param135", 0.0, 1.0)
                                self.model.SetParameterValue("Param149", 0.0, 1.0)
                                self.model.SetParameterValue("Param140", 0.0, 1.0)
                                self.model.SetParameterValue("Param150", 0.0, 1.0)

                            elif current_expr == "angry":
                                self.model.SetParameterValue("Param150", 1.0, 1.0)
                                self.model.SetParameterValue("Param132", 0.0, 1.0)
                                self.model.SetParameterValue("Param135", 0.0, 1.0)
                                self.model.SetParameterValue("Param144", 0.0, 1.0)
                                self.model.SetParameterValue("Param140", 0.0, 1.0)
                                self.model.SetParameterValue("Param149", 0.0, 1.0)
                            elif current_expr == "umbrella_close":
                                self.model.SetParameterValue("Param140", 1.0, 1.0)
                                self.model.SetParameterValue("Param132", 0.0, 1.0)
                                self.model.SetParameterValue("Param135", 0.0, 1.0)
                                self.model.SetParameterValue("Param144", 0.0, 1.0)
                                self.model.SetParameterValue("Param149", 0.0, 1.0)
                                self.model.SetParameterValue("Param150", 0.0, 1.0)
                            else:
                                self.model.SetParameterValue("Param132", 0.0, 1.0)
                                self.model.SetParameterValue("Param135", 0.0, 1.0)
                                self.model.SetParameterValue("Param144", 0.0, 1.0)
                                self.model.SetParameterValue("Param140", 0.0, 1.0)
                                self.model.SetParameterValue("Param149", 0.0, 1.0)
                                self.model.SetParameterValue("Param150", 0.0, 1.0)

                    self.model.SetParameterValue("ParamAngleX", self.current_angle_x, 1.0)
                    self.model.SetParameterValue("ParamAngleY", self.current_angle_y, 1.0)
                    
                    self.model.Update()

                    if hasattr(self, "current_eyeball_x"):
                        self.model.SetParameterValue(
                            "ParamEyeBallX", self.current_eyeball_x, 1.0
                        )
                        if hasattr(self, "current_eyeball_y"):
                            self.model.SetParameterValue(
                                "ParamEyeBallY", self.current_eyeball_y, 1.0
                            )
                        else:
                            eyeball_y = self.current_angle_y * 0.05
                            self.model.SetParameterValue("ParamEyeBallY", eyeball_y, 1.0)

                    self.model.SetParameterValue("ParamAngleZ", self.current_angle_z, 1.0)

                    body_angle_x = self.current_angle_x * 0.3
                    body_angle_y = self.current_angle_y * 0.25
                    body_angle_z = (self.current_angle_x * 0.2) + (self.current_angle_y * 0.1)

                    self.model.SetParameterValue("ParamBodyAngleX", body_angle_x, 1.0)
                    self.model.SetParameterValue("ParamBodyAngleY", body_angle_y, 1.0)
                    self.model.SetParameterValue("ParamBodyAngleZ", body_angle_z, 1.0)

                    sound_manager = self._external_managers.get("sound_manager")
                    if sound_manager and sound_manager.is_speaking():
                        self.target_mouth_open = 0.25
                    else:
                        self.current_mouth_open += (
                            self.target_mouth_open - self.current_mouth_open
                        ) * self.mouth_smooth_speed
                        self.current_mouth_open = max(
                            min(self.current_mouth_open, self.max_open_value),
                            self.min_open_value,
                        )

                    self.model.SetParameterValue(
                        "ParamMouthOpenY", self.current_mouth_open, 1.0
                    )

                    if self.is_asleep:
                        self.model.SetParameterValue("ParamEyeLOpen", 0.0, 1.0)
                        self.model.SetParameterValue("ParamEyeROpen", 0.0, 1.0)
                        self.model.SetParameterValue("ParamEyeBallX", 0.0, 1.0)
                        self.model.SetParameterValue("ParamEyeBallY", 0.0, 1.0)
                        self.model.SetParameterValue("ParamAngleY", -10.0, 1.0)
                    else:
                        self.model.SetParameterValue("ParamEyeLOpen", self.eye_open, 1.0)
                        self.model.SetParameterValue("ParamEyeROpen", self.eye_open, 1.0)

                    self.model.SetParameterValue(
                        "ParamShoulderLRotation", self.current_arm_left, 1.0
                    )
                    self.model.SetParameterValue(
                        "ParamShoulderRRotation", self.current_arm_right, 1.0
                    )

                    try:
                        self.model.Draw()
                    except Exception:
                        pass
                        
                    try:
                        self.update()
                    except Exception:
                        pass
                except Exception:
                    pass
        except Exception:
            pass

    def is_in_model_area(self, click_pos):
        """检查点击位置是否在模型区域内"""
        rel_x = click_pos.x() / self.width()
        rel_y = click_pos.y() / self.height()

        return (
            self.model_area["x1"] <= rel_x <= self.model_area["x2"]
            and self.model_area["y1"] <= rel_y <= self.model_area["y2"]
        )

    def detect_interaction_area(self, click_pos):
        """检测点击位置属于哪个交互区域"""
        if not self.is_in_model_area(click_pos):
            return None

        rel_x = click_pos.x() / self.width()
        rel_y = click_pos.y() / self.height()

        # 检查每个细分交互区域
        for area_name, area in self.interaction_areas.items():
            if area["x1"] <= rel_x <= area["x2"] and area["y1"] <= rel_y <= area["y2"]:
                return area_name

        # 在模型区域内但不在细分交互区域，返回'model'作为默认交互区域
        return "model"

    def _update_click_history(self):
        """更新点击历史"""
        current_time = time.time()
        self.click_history = [
            t for t in self.click_history if current_time - t <= self.click_window
        ]

    def handle_click(self, click_pos, click_count=1):
        """处理点击事件"""
        clicked_area = self.detect_interaction_area(click_pos)
        if not clicked_area:
            return

        current_time = time.time()

        # 更新点击历史
        self._update_click_history()
        self.click_history.append(current_time)

        # 计算时间窗口内的点击次数
        click_count_in_window = len(self.click_history)

        state_machine = self._external_managers.get("state_machine")
        expression_manager = self._external_managers.get("expression_manager")

        if click_count_in_window >= 3:
            if hasattr(self.parent(), "_show_input_window"):
                self.parent()._show_input_window()
                self.reset_click_count()
                return
            if expression_manager:
                expression_manager.set_expression("cry", duration_ms=5000)
            if state_machine:
                state_machine.notify_event(
                    "triple_click", {"click_count": click_count_in_window}
                )
        else:
            if clicked_area == "head":
                if expression_manager:
                    expression_manager.set_expression("shy", duration_ms=3000)
                if state_machine:
                    state_machine.notify_event(
                        "click_head", {"click_count": click_count_in_window}
                    )

            elif clicked_area == "body":
                if expression_manager:
                    expression_manager.set_expression("shy", duration_ms=3000)
                if state_machine:
                    state_machine.notify_event(
                        "click_body", {"click_count": click_count_in_window}
                    )
            elif clicked_area == "model":
                if expression_manager:
                    expression_manager.set_expression("shy", duration_ms=3000)
                if state_machine:
                    state_machine.notify_event(
                        "click", {"click_count": click_count_in_window}
                    )

    def reset_click_count(self):
        self.click_count = 0
        self.is_panicked = False
        self.click_history = []

    def _check_system_resources(self):
        """检查系统资源使用情况"""
        try:
            cpu_usage = psutil.cpu_percent()
            memory = psutil.virtual_memory()
            mem_usage = memory.percent
            return cpu_usage, mem_usage
        except Exception as e:
            logger.error(f"获取系统资源失败: {e}")
            return 0.0, 0.0

    def _auto_behavior_tick(self):
        """基于系统资源动态调整行为频率"""
        if self.is_asleep:
            return

        cpu, mem = self._check_system_resources()

        if self._cpu_ema is None:
            self._cpu_ema = cpu
            self._mem_ema = mem
        else:
            self._cpu_ema = (
                self._ema_alpha * cpu + (1 - self._ema_alpha) * self._cpu_ema
            )
            self._mem_ema = (
                self._ema_alpha * mem + (1 - self._ema_alpha) * self._mem_ema
            )

        now = time.time()
        if now - self._last_freq_change_time >= self._min_freq_change_interval:
            if self._cpu_ema < 30 and self._mem_ema < 50:
                new_interval = random.randint(1000, 2000)
                self.current_frequency = "high"
            elif self._cpu_ema > 70 or self._mem_ema > 80:
                new_interval = random.randint(10000, 20000)
                self.current_frequency = "low"
                if random.random() > 0.3:
                    self.behavior_timer.setInterval(new_interval)
                    self._last_freq_change_time = now
                    return
            else:
                new_interval = random.randint(3000, 5000)
                self.current_frequency = "medium"

            self.behavior_timer.setInterval(new_interval)
            self._last_freq_change_time = now

        self.trigger_random_behavior()

    def _auto_think(self):
        """定期调用本地模型生成自主行为"""
        if self.is_asleep:
            return

        from utils.config_manager import config_manager
        new_auto_think_enabled = config_manager.get("ai.enable_local_proactive", False)
        
        if not self.auto_think_enabled and new_auto_think_enabled:
            if not self.auto_think_timer.isActive():
                self.auto_think_timer.start(10000)
        elif self.auto_think_enabled and not new_auto_think_enabled:
            if self.auto_think_timer.isActive():
                self.auto_think_timer.stop()
        
        self.auto_think_enabled = new_auto_think_enabled
        
        if not self.auto_think_enabled:
            return

        cpu, mem = self._check_system_resources()
        self._adjust_think_frequency(cpu, mem)

        current_time = time.time()
        if (
            current_time - self.last_think_time < self.auto_think_interval * 0.8
        ):
            return

        skip_probability = (
            0.85
            if self.auto_think_priority == "low"
            else 0.75 if self.auto_think_priority == "medium" else 0.5
        )
        if random.random() > skip_probability:
            return

        self.last_think_time = current_time

        if self._behavior_worker is None or not self._behavior_worker.isRunning():
            if hasattr(self.parent(), "brain") and getattr(
                self.parent().brain, "local_model", None
            ):
                self._behavior_worker = BehaviorWorker(
                    self.parent().brain, cpu, mem, self.last_action, timeout_sec=2.0
                )
                self._behavior_worker.result_ready.connect(self._on_behavior_decision)
                self._behavior_worker.error.connect(
                    lambda e: logger.debug(f"行为Worker错误: {e}")
                )
                self._behavior_worker.start()

    def _adjust_think_frequency(self, cpu, mem):
        """根据系统资源调整自主行为生成频率"""
        if self._cpu_ema is None:
            self._cpu_ema = cpu
            self._mem_ema = mem
        else:
            self._cpu_ema = (
                self._ema_alpha * cpu + (1 - self._ema_alpha) * self._cpu_ema
            )
            self._mem_ema = (
                self._ema_alpha * mem + (1 - self._ema_alpha) * self._mem_ema
            )

        # 根据系统资源调整调用频率
        now = time.time()
        if now - self._last_freq_change_time >= self._min_freq_change_interval:
            if self._cpu_ema < 30 and self._mem_ema < 50:
                # 资源空闲，高频调用（频率再减半）
                new_interval = random.randint(6000, 10000)  # 从3-5秒调整为6-10秒
                self.auto_think_priority = "high"
            elif self._cpu_ema > 70 or self._mem_ema > 80:
                # 资源紧张，低频调用（频率再减半）
                new_interval = random.randint(30000, 60000)  # 从15-30秒调整为30-60秒
                self.auto_think_priority = "low"
            else:
                # 资源一般，中频调用（频率再减半）
                new_interval = random.randint(12000, 20000)  # 从6-10秒调整为12-20秒
                self.auto_think_priority = "medium"

            self.auto_think_timer.setInterval(new_interval)
            self.auto_think_interval = new_interval / 1000.0
            self._last_freq_change_time = now

    def _smooth_move(self, x, y):
        """平滑移动窗口到指定位置"""
        if hasattr(self.parent(), "pos") and hasattr(self.parent(), "move"):
            # 获取当前窗口位置
            current_pos = self.parent().pos()
            self.start_pos = (current_pos.x(), current_pos.y())
            self.target_pos = (x, y)
            self.current_pos = self.start_pos
            self.is_moving = True
            self.move_progress = 0.0
            self.move_start_time = time.time()

            # 启动移动定时器，每16ms执行一次移动步骤
            self.move_timer.start(16)
            logger.info(
                f"开始平滑移动窗口，从 ({self.start_pos[0]}, {self.start_pos[1]}) 到 ({x}, {y})"
            )

    def _smooth_move_step(self):
        """平滑移动的每一步逻辑"""
        if not self.is_moving or not self.start_pos or not self.target_pos:
            self.move_timer.stop()
            return

        elapsed_time = (time.time() - self.move_start_time) * 1000

        if elapsed_time >= self.move_duration:
            self.parent().move(self.target_pos[0], self.target_pos[1])
            self.is_moving = False
            self.move_timer.stop()
            logger.info(
                f"平滑移动窗口完成，到达目标位置 ({self.target_pos[0]}, {self.target_pos[1]})"
            )
            return

        self.move_progress = elapsed_time / self.move_duration

        t = self.move_progress
        eased_t = t * t * (3 - 2 * t)

        # 计算当前位置
        current_x = (
            self.start_pos[0] + (self.target_pos[0] - self.start_pos[0]) * eased_t
        )
        current_y = (
            self.start_pos[1] + (self.target_pos[1] - self.start_pos[1]) * eased_t
        )

        # 移动窗口
        self.parent().move(int(current_x), int(current_y))
        
    def _smooth_resize(self, width, height):
        """平滑调整窗口大小"""
        if hasattr(self.parent(), "size") and hasattr(self.parent(), "resize"):
            from PyQt5.QtWidgets import QApplication
            screen_geo = QApplication.primaryScreen().geometry()
            
            if hasattr(self.parent(), "pos"):
                current_pos = self.parent().pos()
                
                max_available_width = screen_geo.width() - current_pos.x()
                max_available_height = screen_geo.height() - current_pos.y()
                
                new_width = min(width, max_available_width - 10)
                new_height = min(height, max_available_height - 10)
                
                new_width = max(200, new_width)
                new_height = max(250, new_height)
            else:
                new_width = max(200, min(width, 1200))
                new_height = max(250, min(height, 1500))
            
            # 获取当前窗口大小
            current_size = self.parent().size()
            self.start_size = (current_size.width(), current_size.height())
            self.target_size = (new_width, new_height)
            self.current_size = self.start_size
            self.is_resizing = True
            self.resize_progress = 0.0
            self.resize_start_time = time.time()

            self.resize_timer = QTimer(self)
            self.resize_timer.timeout.connect(self._smooth_resize_step)
            self.resize_timer.start(16)
            logger.info(
                f"开始平滑调整窗口大小，从 {self.start_size[0]}x{self.start_size[1]} 到 {self.target_size[0]}x{self.target_size[1]}"
            )
    
    def _smooth_resize_step(self):
        """平滑调整窗口大小的每一步逻辑"""
        if not self.is_resizing or not self.start_size or not self.target_size:
            self.resize_timer.stop()
            return

        elapsed_time = (time.time() - self.resize_start_time) * 1000

        if elapsed_time >= self.move_duration:
            self.parent().resize(self.target_size[0], self.target_size[1])
            self.is_resizing = False
            self.resize_timer.stop()
            logger.info(
                f"平滑调整窗口大小完成，到达目标大小 {self.target_size[0]}x{self.target_size[1]}"
            )
            return

        self.resize_progress = elapsed_time / self.move_duration

        t = self.resize_progress
        eased_t = t * t * (3 - 2 * t)

        # 计算当前大小
        current_width = (
            self.start_size[0] + (self.target_size[0] - self.start_size[0]) * eased_t
        )
        current_height = (
            self.start_size[1] + (self.target_size[1] - self.start_size[1]) * eased_t
        )

        # 调整窗口大小
        self.parent().resize(int(current_width), int(current_height))

    def _on_behavior_decision(self, decision):
        """执行本地模型生成的行为决策"""
        if not decision:
            return

        logger.debug(f"正在解析决策数据: {decision}")

        if self.is_asleep:
            logger.debug("宠物正在睡觉，跳过行为决策执行")
            return

        action = None
        expression = None
        text = None
        intensity = 0.5  # Default intensity: 0.5
        speed = 1.0  # Default speed: 1.0
        tool_call = None
        tool_params = {}

        if "tool_call" in decision and decision["tool_call"]:
            tool_call = decision["tool_call"]
            tool_params = decision.get("tool_params", {})
            reason = decision.get("reason", "No reason provided")
            
            logger.debug(f"执行工具调用: {tool_call}, 参数: {tool_params}, 原因: {reason}")
            
            self._execute_tool_call(tool_call, tool_params)
            return
        
        elif "function_call" in decision:
            fc = decision["function_call"]
            function_name = fc.get("name")
            arguments = fc.get("arguments", {})

            if isinstance(arguments, str):
                try:
                    import json
                    arguments = json.loads(arguments)
                except json.JSONDecodeError:
                    logger.error(f"无法解析function_call的arguments: {arguments}")
                    arguments = {}

            if function_name == "perform_action":
                action = arguments.get("action_name")
                expression = arguments.get("expression_name")

        elif "tool" in decision:
            tool_name = decision["tool"]
            params = decision.get("params", {})
            reason = decision.get("reason", "No reason provided")

            logger.debug(f"执行工具调用: {tool_name}, 参数: {params}, 原因: {reason}")
            
            self._execute_tool_call(tool_name, params)
            return

        else:
            action = decision.get("action")
            expression = decision.get("expression")
            text = decision.get("text")
            params = decision.get("params", {})
            intensity = params.get("intensity", decision.get("intensity", 0.5))
            speed = params.get("speed", decision.get("speed", 1.0))

        if not action or action == "idle":
            if text and hasattr(self.parent(), "_show_message_bubble"):
                self.parent()._show_message_bubble(text, duration_ms=4000)
            return

        if action == "window_op":
            window_op_type = params.get("type", "reset")
            if window_op_type == "reset" and hasattr(self.parent(), "resize"):
                from ui.config_window import AIConfigWindow
                self.parent().resize(AIConfigWindow.WINDOW_WIDTH, AIConfigWindow.WINDOW_HEIGHT)
                logger.info(f"已重置窗口大小")
            elif window_op_type == "shrink" and hasattr(self.parent(), "resize"):
                current_width = self.parent().width()
                current_height = self.parent().height()
                new_width = int(current_width * 0.8)
                new_height = int(current_height * 0.8)
                self.parent().resize(new_width, new_height)
                logger.info(f"已将窗口缩小到 {new_width}x{new_height}")
            elif window_op_type == "expand" and hasattr(self.parent(), "resize"):
                current_width = self.parent().width()
                current_height = self.parent().height()
                new_width = int(current_width * 1.2)
                new_height = int(current_height * 1.2)
                self.parent().resize(new_width, new_height)
                logger.info(f"已将窗口放大到 {new_width}x{new_height}")
            elif window_op_type == "set_window_position" and hasattr(self.parent(), "move"):
                x = params.get("x", 100)
                y = params.get("y", 100)
                self._smooth_move(x, y)
            elif window_op_type == "set_window_size" and hasattr(self.parent(), "resize"):
                width = params.get("width", 400)
                height = params.get("height", 500)
                self.parent().resize(width, height)
                logger.info(f"已将窗口大小调整到 {width}x{height}")
        elif action == "toggle_follow":
            enabled = params.get("enabled", True)
            self.set_mouse_follow(enabled)
            status = "开启" if enabled else "关闭"
            logger.info(f"已{status}视线跟随模式")
        elif action == "set_behavior_mode":
            frequency = params.get("frequency", "medium")
            result = self.set_random_behavior_mode(frequency)
            logger.info(result)
        elif action == "play_sequence":
            actions = params.get("actions", [])
            interval = params.get("interval", 0.5)
            if actions:
                self.play_action_sequence(actions, interval)
        elif hasattr(self, action):
            try:
                getattr(self, action)(intensity=intensity, speed=speed)
            except TypeError:
                getattr(self, action)()
            self.last_action = action

        if expression and "expression_manager" in self._external_managers:
            self._external_managers["expression_manager"].set_expression(
                expression, duration_ms=3000
            )

        if text and hasattr(self.parent(), "_show_message_bubble"):
            self.parent()._show_message_bubble(text, duration_ms=4000)
    
    def _execute_tool_call(self, tool_name, params):
        """执行工具调用"""
        if tool_name == "get_window_info":
            if hasattr(self.parent(), "pos") and hasattr(self.parent(), "size"):
                pos = self.parent().pos()
                size = self.parent().size()
                logger.info(f"当前窗口信息: x={pos.x()}, y={pos.y()}, width={size.width()}, height={size.height()}")
        
        elif tool_name == "set_window_position" and hasattr(self.parent(), "move"):
            x = params.get("x", 100)
            y = params.get("y", 100)
            
            if hasattr(self.parent(), "pos"):
                current_pos = self.parent().pos()
                if current_pos.x() == x and current_pos.y() == y:
                    logger.debug(f"窗口已在目标位置 ({x}, {y})，跳过移动")
                    return
            
            self._smooth_move(x, y)
        
        elif tool_name == "set_window_size" and hasattr(self.parent(), "resize"):
            width = params.get("width", 400)
            height = params.get("height", 500)
            
            if hasattr(self.parent(), "size"):
                current_size = self.parent().size()
                if current_size.width() == width and current_size.height() == height:
                    logger.debug(f"窗口已为目标大小 {width}x{height}，跳过调整")
                    return
            
            self._smooth_resize(width, height)
        
        elif tool_name == "toggle_watch_mode":
            active = params.get("active", True)
            
            if self.get_mouse_follow() == active:
                logger.debug(f"视线跟随已{'开启' if active else '关闭'}，跳过切换")
                return
            
            self.set_mouse_follow(active)
            status = "开启" if active else "关闭"
            logger.info(f"已{status}视线跟随模式")
        
        elif tool_name == "get_watch_mode":
            current_state = self.get_mouse_follow()
            logger.info(f"当前视线跟随状态: {current_state}")
        
        elif tool_name == "perform_action":
            action_name = params.get("action_name", "idle")
            if hasattr(self, action_name):
                try:
                    intensity = params.get("intensity", 0.5)
                    speed = params.get("speed", 1.0)
                    getattr(self, action_name)(intensity=intensity, speed=speed)
                except TypeError:
                    getattr(self, action_name)()
                self.last_action = action_name
            else:
                logger.warning(f"未知动作: {action_name}")
        
        elif tool_name == "set_expression":
            expression_name = params.get("expression_name", "normal")
            if "expression_manager" in self._external_managers:
                self._external_managers["expression_manager"].set_expression(
                    expression_name, duration_ms=3000
                )
        
        elif tool_name == "play_action_sequence":
            actions = params.get("actions", [])
            interval = params.get("interval", 0.5)
            if actions:
                self.play_action_sequence(actions, interval)
        
        elif tool_name == "set_behavior_mode":
            frequency = params.get("frequency", "medium")
            
            if self.current_frequency == frequency:
                logger.debug(f"行为模式已为{frequency}，跳过设置")
                return
            
            result = self.set_random_behavior_mode(frequency)
            logger.info(result)
        
        elif tool_name == "speak":
            logger.debug(f"执行工具调用: {tool_name}, 参数: {params}")
            
            text = params.get("text", "")
            expression = params.get("expression", "normal")
            motion = params.get("motion", "idle")
            
            if not text:
                random_memory = ""
                if hasattr(self.parent(), "brain") and hasattr(self.parent().brain, "behavior_decider"):
                    random_memory = self.parent().brain.behavior_decider._get_random_memory()
                
                if random_memory:
                    text = f"{random_memory}"
                else:
                    text = "你好呀！有什么我可以帮你的吗？"
            
            if hasattr(self.parent(), "_show_message_bubble"):
                self.parent()._show_message_bubble(text, duration_ms=5000)
            else:
                logger.warning("父窗口没有_show_message_bubble方法")
            
            if expression and "expression_manager" in self._external_managers:
                self._external_managers["expression_manager"].set_expression(expression, duration_ms=3000)
            
            if motion and hasattr(self, motion):
                try:
                    getattr(self, motion)()
                    self.last_action = motion
                except TypeError:
                    getattr(self, motion)()
                    self.last_action = motion
            elif motion != "idle":
                logger.warning(f"未知动作: {motion}")
        
        else:
            logger.warning(f"未知工具: {tool_name}")

    def trigger_random_behavior(self):
        """触发随机行为"""
        if self.is_asleep:
            return

        if self.is_playing_action or not self.model:
            return

        # 根据当前频率选择不同的行为组合
        if self.current_frequency == "high":
            # 资源空闲时，选择更活跃的行为
            actions = [
                "wave_hand",
                "stretch_arms",
                "nod_head",
                "look_around",
                "tilt_head",
                "bounce_body",
            ]
        elif self.current_frequency == "medium":
            # 资源一般时，选择中等活跃度的行为
            actions = [
                "random_blink",
                "smile",
                "random_head_turn",
                "look_around",
                "tilt_head",
            ]
        else:
            actions = ["random_blink", "smile", "random_head_turn"]

        action = random.choice(actions)
        if hasattr(self, action):
            getattr(self, action)()
            self.last_action = action

    def random_blink(self):
        """随机眨眼"""
        if not self.model:
            return
        self.target_eye_open = 0.0

    def random_head_turn(self):
        """随机转头"""
        if not self.model:
            return
        self.target_angle_x = random.uniform(-15.0, 15.0)
        self.target_angle_y = random.uniform(-10.0, 10.0)

    def wave_hand(self, intensity=0.5, speed=1.0):
        """挥手动作"""
        if not self.model or self.is_playing_action:
            return
        self.is_playing_action = True

        def reset_wave():
            self.is_playing_action = False

        rotation = -15.0 * intensity
        duration = int(300 / speed)

        self.model.SetParameterValue("ParamShoulderLRotation", rotation, 1.0)
        self.model.SetParameterValue("ParamShoulderRRotation", rotation, 1.0)

        QTimer.singleShot(duration, reset_wave)

    def stretch_arms(self, intensity=0.5, speed=1.0):
        """伸展手臂"""
        if not self.model or self.is_playing_action:
            return
        self.is_playing_action = True

        def reset_stretch():
            self.is_playing_action = False

        shoulder_rotation = 10.0 * intensity
        head_angle = 15.0 * intensity
        duration = int(500 / speed)

        self.model.SetParameterValue("ParamShoulderLRotation", shoulder_rotation, 1.0)
        self.model.SetParameterValue("ParamShoulderRRotation", shoulder_rotation, 1.0)
        self.target_angle_y = head_angle

        QTimer.singleShot(duration, reset_stretch)

    def nod_head(self, intensity=0.5, speed=1.0):
        """点头动作"""
        if not self.model or self.is_playing_action:
            return
        self.is_playing_action = True

        def reset_nod():
            self.is_playing_action = False

        head_angle = 10.0 * intensity
        mid_duration = int(200 / speed)
        total_duration = int(400 / speed)

        self.target_angle_y = head_angle

        QTimer.singleShot(
            mid_duration, lambda: setattr(self, "target_angle_y", -head_angle)
        )
        QTimer.singleShot(total_duration, reset_nod)

    def shake_head(self, intensity=0.5, speed=1.0):
        """摇头动作"""
        if not self.model or self.is_playing_action:
            return
        self.is_playing_action = True

        def reset_shake():
            self.is_playing_action = False

        head_angle = 15.0 * intensity
        mid_duration = int(200 / speed)
        total_duration = int(400 / speed)

        self.target_angle_x = head_angle

        QTimer.singleShot(
            mid_duration, lambda: setattr(self, "target_angle_x", -head_angle)
        )
        QTimer.singleShot(total_duration, reset_shake)

    def look_around(self):
        """环顾四周"""
        if not self.model or self.is_playing_action:
            return
        self.is_playing_action = True

        def reset_look():
            self.is_playing_action = False

        self.target_angle_x = 20.0
        self.target_angle_y = 10.0

        QTimer.singleShot(300, lambda: setattr(self, "target_angle_x", -20.0))
        QTimer.singleShot(600, lambda: setattr(self, "target_angle_y", -10.0))
        QTimer.singleShot(900, lambda: setattr(self, "target_angle_x", 0.0))
        QTimer.singleShot(1200, reset_look)

    def bounce_body(self):
        """身体轻微弹跳"""
        if not self.model or self.is_playing_action:
            return
        self.is_playing_action = True

        def reset_bounce():
            self.is_playing_action = False

        # 模拟弹跳动作，通过快速改变身体Y轴角度实现
        self.model.SetParameterValue("ParamBodyAngleY", 5.0, 1.0)

        QTimer.singleShot(
            150, lambda: self.model.SetParameterValue("ParamBodyAngleY", -5.0, 1.0)
        )
        QTimer.singleShot(300, reset_bounce)

    def tilt_head(self):
        """歪头动作，表现好奇或困惑"""
        if not self.model:
            return
        # 歪头效果，通过改变Z轴角度实现
        self.target_angle_z = 5.0

        def reset_tilt():
            self.target_angle_z = 0.0

        # 1秒后恢复
        QTimer.singleShot(1000, reset_tilt)

    def smile(self):
        """微笑表情，表达开心"""
        if not self.model:
            return
        # 微笑效果，通过改变嘴巴参数实现
        self.target_mouth_open = self.max_open_value

    def frown(self):
        """皱眉表情，表达不满或困惑"""
        if not self.model:
            return
        # 皱眉效果，通过改变眼睛和眉毛参数实现
        self.model.SetParameterValue("ParamEyeLOpen", 0.5, 1.0)
        self.model.SetParameterValue("ParamEyeROpen", 0.5, 1.0)

    def surprised(self):
        """惊讶表情，表达惊讶"""
        if not self.model:
            return
        self.model.SetParameterValue("ParamEyeLOpen", 1.0, 1.0)
        self.model.SetParameterValue("ParamEyeROpen", 1.0, 1.0)
        self.target_mouth_open = self.max_open_value

    def blush(self):
        """脸红表情"""
        if not self.model:
            return
        try:
            self.model.SetParameterValue("ParamCheek", 1.0, 1.0)
        except Exception:
            logger.debug("当前模型不支持腮红效果")

    def play_action_sequence(self, actions, interval=0.5):
        """播放动作序列"""
        if not self.model or self.is_playing_action:
            return
        self.is_playing_action = True

        def execute_action(index):
            if index >= len(actions):
                self.is_playing_action = False
                return

            action = actions[index]
            if hasattr(self, action):
                getattr(self, action)()

            # 执行下一个动作
            QTimer.singleShot(int(interval * 1000), lambda: execute_action(index + 1))

        execute_action(0)

    def set_random_behavior_mode(self, frequency):
        """设置随机行为模式

        Args:
            frequency: 频率模式，可选值：high/medium/low
        """
        frequency_map = {
            "high": (1000, 2000),
            "medium": (3000, 5000),
            "low": (10000, 20000),
        }

        if frequency in frequency_map:
            min_interval, max_interval = frequency_map[frequency]
            new_interval = random.randint(min_interval, max_interval)
            self.behavior_timer.setInterval(new_interval)
            self.current_frequency = frequency
            return f"已设置行为模式为 {frequency}"
        return f"无效的行为模式: {frequency}"

    def update_model_angle(self):
        if not self.model:
            return
        
        # 检查并执行鼠标躲避
        self._check_and_avoid_mouse()

        current_time = time.time()

        # 初始化必要的属性
        if not hasattr(self, "target_eyeball_x"):
            self.target_eyeball_x = 0.0
            self.current_eyeball_x = 0.0
        if not hasattr(self, "target_eyeball_y"):
            self.target_eyeball_y = 0.0
            self.current_eyeball_y = 0.0
        if not hasattr(self, "last_wander_time"):
            self.last_wander_time = current_time
            self.wander_interval = random.uniform(2.0, 5.0)
            self.wander_target_x = random.uniform(-0.3, 0.3)
            self.wander_target_y = random.uniform(-0.2, 0.2)

        if self.is_mouse_follow_enabled:
            # 【模式 A】跟随鼠标
            cursor_pos = QCursor.pos()
            window_pos = self.mapFromGlobal(cursor_pos)
            self.last_cursor_pos = window_pos

            window_width = self.width()
            window_height = self.height()

            # 计算目标角度（-30到30度之间）
            target_angle_x = round((window_pos.x() / window_width) * 60.0 - 30.0, 1)
            target_angle_y = round(-(window_pos.y() / window_height) * 60.0 + 30.0, 1)

            # 计算眼球位置（-0.8到0.8之间）
            target_eyeball_x = round(
                ((window_pos.x() / window_width) * 2.0 - 1.0) * 0.8, 2
            )
            target_eyeball_y = round(
                ((window_pos.y() / window_height) * 2.0 - 1.0) * 0.6, 2
            )
        else:
            # 【模式 B】发呆/随机游走
            # 如果距离上次变换时间超过了间隔，重新生成一个目标点
            if current_time - self.last_wander_time > self.wander_interval:
                # 限制在中心区域的小范围内游走（-0.3到0.3，对应角度-9到9度）
                self.wander_target_x = random.uniform(-0.3, 0.3)
                self.wander_target_y = random.uniform(-0.2, 0.2)

                # 随机化下一次变换的时间，让律动更自然
                self.wander_interval = random.uniform(2.0, 5.0)
                self.last_wander_time = current_time

            # 给发呆点增加一点点极细微的“呼吸感”抖动（使用正弦函数）
            micro_vibration = math.sin(current_time * 1.5) * 0.05

            # 计算目标角度（-9到9度之间，加上微振动）
            target_angle_x = (self.wander_target_x + micro_vibration) * 30
            target_angle_y = (self.wander_target_y + micro_vibration * 0.5) * 30

            # 计算眼球位置（比头部转动幅度稍大，更有灵气）
            target_eyeball_x = (self.wander_target_x + micro_vibration) * 1.2
            target_eyeball_y = (self.wander_target_y + micro_vibration * 0.5) * 1.2

        smoothing_factor = 0.08

        self.target_angle_x = target_angle_x
        self.target_angle_y = target_angle_y
        self.target_eyeball_x = target_eyeball_x
        self.target_eyeball_y = target_eyeball_y

        if not hasattr(self, "target_arm_left"):
            self.target_arm_left = -5.0
        if not hasattr(self, "target_arm_right"):
            self.target_arm_right = -5.0

        arm_rotation_factor = 0.25
        self.target_arm_left = -target_angle_x * arm_rotation_factor
        self.target_arm_right = target_angle_x * arm_rotation_factor

        if self.is_ctrl_mouse_pressed:
            self.target_eye_open = 0.0
            self.target_arm_left = -20.0
            self.target_arm_right = -20.0
            self.target_mouth_open = self.min_open_value

        self.current_angle_x += (
            self.target_angle_x - self.current_angle_x
        ) * smoothing_factor
        self.current_angle_y += (
            self.target_angle_y - self.current_angle_y
        ) * smoothing_factor
        self.current_eyeball_x += (self.target_eyeball_x - self.current_eyeball_x) * (
            smoothing_factor * 1.5
        )
        self.current_eyeball_y += (self.target_eyeball_y - self.current_eyeball_y) * (
            smoothing_factor * 1.5
        )
        self.current_arm_left += (self.target_arm_left - self.current_arm_left) * (
            smoothing_factor * 0.9
        )
        self.current_arm_right += (self.target_arm_right - self.current_arm_right) * (
            smoothing_factor * 0.9
        )

        self.current_angle_x = max(min(self.current_angle_x, 25.0), -25.0)
        self.current_angle_y = max(min(self.current_angle_y, 20.0), -20.0)
        self.current_eyeball_x = max(min(self.current_eyeball_x, 0.8), -0.8)
        self.current_eyeball_y = max(min(self.current_eyeball_y, 0.5), -0.5)
        self.current_arm_left = max(min(self.current_arm_left, 5.0), -25.0)
        self.current_arm_right = max(min(self.current_arm_right, 5.0), -25.0)

        self.current_mouth_open += (
            self.target_mouth_open - self.current_mouth_open
        ) * self.mouth_smooth_speed
        self.current_mouth_open = max(
            min(self.current_mouth_open, self.max_open_value), self.min_open_value
        )

        if not self.is_ctrl_mouse_pressed:
            self.blink_timer += 1
            if self.blink_timer >= self.blink_interval:
                self.blink_timer = 0
                self.target_eye_open = 0.0
                self.blink_interval = random.randint(
                    LIVE2D_RENDER_CONFIG.get("blink_interval", 500) - 300,
                    LIVE2D_RENDER_CONFIG.get("blink_interval", 500) + 300,
                )

            if self.target_eye_open == 0.0 and self.eye_open < 0.1:
                if self.blink_timer < self.blink_duration:
                    self.target_eye_open = 0.0
                else:
                    self.target_eye_open = 1.0

            self.breath_timer += 1
            if self.breath_timer >= self.breath_interval:
                self.breath_timer = 0
                change_amount = random.uniform(-0.1, 0.1)
                self.target_mouth_open += change_amount
                self.target_mouth_open = max(
                    min(self.target_mouth_open, self.max_open_value),
                    self.min_open_value,
                )
                self.breath_interval = random.randint(
                    LIVE2D_RENDER_CONFIG.get("breath_interval", 150) - 30,
                    LIVE2D_RENDER_CONFIG.get("breath_interval", 150) + 90,
                )

        # 平滑更新Z轴旋转
        self.current_angle_z += (
            self.target_angle_z - self.current_angle_z
        ) * smoothing_factor
        self.current_angle_z = max(min(self.current_angle_z, 10.0), -10.0)

        # 平滑更新眼睛开合度
        self.eye_open += (self.target_eye_open - self.eye_open) * self.eye_smooth_speed
        self.eye_open = max(min(self.eye_open, 1.0), 0.0)

    def set_expression(self, expression_name, duration_ms=None):
        expression_manager = self._external_managers.get("expression_manager")
        if expression_manager:
            expression_manager.set_expression(expression_name, duration_ms=duration_ms)

    def play_motion(self, motion_name, priority=50, interruptible=True):
        animation_manager = self._external_managers.get("animation_manager")
        if animation_manager:
            return animation_manager.play_motion(motion_name, priority, interruptible)
        return None

    def stop_motion(self):
        animation_manager = self._external_managers.get("animation_manager")
        if animation_manager:
            animation_manager.stop_motion()

    def get_model(self):
        return self.model

    def set_ctrl_mouse_pressed(self, pressed: bool):
        self.is_ctrl_mouse_pressed = pressed

    def get_mouse_follow(self):
        """获取鼠标跟随状态"""
        return self.is_mouse_follow_enabled

    def set_mouse_follow(self, enabled: bool):
        """设置鼠标跟随状态"""
        self.is_mouse_follow_enabled = enabled
        logger.info(f"鼠标跟随状态已设置为: {enabled}")
    
    def get_avoid_mouse(self):
        """获取智能躲避模式状态"""
        return self.is_avoid_mouse_enabled
    
    def set_avoid_mouse(self, enabled: bool):
        """设置智能躲避模式"""
        self.is_avoid_mouse_enabled = enabled
        logger.info(f"智能躲避模式已{'开启' if enabled else '关闭'}")
    
    def _check_and_avoid_mouse(self):
        """检查鼠标位置并执行躲避"""
        if not self.is_avoid_mouse_enabled or not self.parent():
            return
        
        cursor_pos = QCursor.pos()
        window_pos = self.parent().pos()
        window_size = self.parent().size()
        
        # 计算窗口中心位置
        window_center_x = window_pos.x() + window_size.width() // 2
        window_center_y = window_pos.y() + window_size.height() // 2
        
        # 计算鼠标与窗口中心的距离
        dx = cursor_pos.x() - window_center_x
        dy = cursor_pos.y() - window_center_y
        distance = (dx ** 2 + dy ** 2) ** 0.5
        
        # 如果鼠标在躲避范围内，执行躲避
        if distance < self.avoid_distance_threshold:
            # 计算躲避方向（与鼠标方向相反）
            if distance > 0:
                avoid_dx = -dx / distance
                avoid_dy = -dy / distance
                
                # 计算新位置
                new_x = window_pos.x() + avoid_dx * self.avoid_speed
                new_y = window_pos.y() + avoid_dy * self.avoid_speed
                
                # 限制在屏幕范围内
                screen_geometry = QApplication.desktop().availableGeometry()
                max_x = screen_geometry.width() - window_size.width() - self.avoid_margin
                max_y = screen_geometry.height() - window_size.height() - self.avoid_margin
                
                new_x = max(self.avoid_margin, min(new_x, max_x))
                new_y = max(self.avoid_margin, min(new_y, max_y))
                
                # 移动窗口
                self.parent().move(int(new_x), int(new_y))
                
                logger.debug(f"躲避鼠标！距离: {distance:.1f}px, 移动到: ({int(new_x)}, {int(new_y)})")

    def wheelEvent(self, event):
        """处理鼠标滚轮事件"""
        from PyQt5.QtCore import Qt

        if event.modifiers() & Qt.ControlModifier:
            current_width = self.width()
            current_height = self.height()

            scale_factor = 1.05 if event.angleDelta().y() > 0 else 0.95

            new_width = int(current_width * scale_factor)
            new_height = int(current_height * scale_factor)

            min_size = 100
            max_size = 10000

            new_width = max(min(new_width, max_size), min_size)
            new_height = max(min(new_height, max_size), min_size)

            self.parent().resize(new_width, new_height)

            if self.model:
                self.model.Resize(new_width, new_height)

        super().wheelEvent(event)
