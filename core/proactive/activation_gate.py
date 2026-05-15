"""
激活门控系统

核心功能：
- 激活度累积和触发机制
- 支持session和topic两种模式
- 冷却机制管理
"""

import os
from typing import Any, Dict, Optional

from loguru import logger


class ActivationGate:
    """激活门控系统"""

    def __init__(self):
        """初始化激活门控"""
        # 配置常量（与memoryos-agent一致）
        self.ACTIVATION_INCREMENT = float(os.environ.get("PROACTIVE_ACTIVATION_INCREMENT", "0.55"))
        self.ACTIVATION_THRESHOLD = float(os.environ.get("PROACTIVE_ACTIVATION_THRESHOLD", "1.0"))
        self.COOLING_TURNS = int(os.environ.get("PROACTIVE_COOLING_TURNS", "10"))

        # 按LLM判定强度动态分配增量（memoryos-agent最新设计：全部为1.0）
        self.ACTIVATION_INCREMENT_BY_STRENGTH = {
            "strong": 1.0,
            "medium": 1.0,
            "weak": 1.0,
        }

    def apply_activation_gate(
        self,
        memory,
        decision: dict,
        candidates: list
    ) -> dict:
        """
        在LLM决策should_callback=true之后，用激活度进度条决定是否真正触发

        支持两种持久化存储(对调用方透明):
          · session-level (legacy): target.session_id 存在 → 写 mid_term.sessions.proactive_meta
          · topic-level (独立管线): target.topic_id 存在、session_id=None → 写 topic_store

        每次LLM判yes → target的activation += INCREMENT
        activation >= THRESHOLD → 放行（真正触发）并保持满值
        activation < THRESHOLD → 拦截（改为no），前端显示进度条

        Args:
            memory: 记忆管理器
            decision: LLM决策结果
            candidates: 候选话题列表

        Returns:
            修改后的decision dict
        """
        if not decision.get("should_callback") or not candidates:
            return decision

        t_idx = decision.get("target_memory_index")
        if not isinstance(t_idx, int) or t_idx < 0 or t_idx >= len(candidates):
            return decision

        target = candidates[t_idx]
        target_sid = target.get("session_id")
        target_meta = target.get("proactive_meta") or {}
        target_tid = target_meta.get("topic_id") or target.get("topic_id")

        # 选持久化后端:优先session(legacy),否则topic(独立管线)
        if target_sid:
            return self._apply_gate_session(memory, decision, target_sid)
        if target_tid:
            return self._apply_gate_topic(memory, decision, target_tid)

        # 既无sid也无tid,无法持久化 — 直接放行(不拦)
        return decision

    def _apply_gate_session(self, memory, decision: dict, target_sid: str) -> dict:
        """Legacy:session-level activation,持久化在mid_term.sessions.proactive_meta"""
        mid_term = getattr(memory, "mid_term_memory", None)
        if mid_term is None:
            return decision

        session = mid_term.sessions.get(target_sid)
        if not session:
            return decision

        meta = session.get("proactive_meta") or {}
        current_activation = float(meta.get("proactive_activation", 0.0))
        strength = decision.get("match_strength", "medium")
        increment = self.ACTIVATION_INCREMENT_BY_STRENGTH.get(strength, self.ACTIVATION_INCREMENT)
        new_activation = current_activation + increment
        label = f"session {target_sid}"

        if new_activation >= self.ACTIVATION_THRESHOLD:
            meta["proactive_activation"] = self.ACTIVATION_THRESHOLD
            decision["activation_fired"] = True
            decision["activation_before"] = current_activation
            decision["activation_after"] = self.ACTIVATION_THRESHOLD
            logger.info(f"[ActivationGate] {label}: {current_activation:.2f} + {increment:.2f} ({strength}) = {new_activation:.2f} >= {self.ACTIVATION_THRESHOLD} → FIRE")
        else:
            meta["proactive_activation"] = new_activation
            decision["should_callback"] = False
            decision["activation_pending"] = True
            decision["activation_before"] = current_activation
            decision["activation_after"] = new_activation
            decision["_original_thoughts"] = decision.get("thoughts", "")
            decision["thoughts"] = f"话题激活中 ({new_activation:.0%}, {strength})：{decision.get('thoughts', '')[:60]}"
            logger.debug(f"[ActivationGate] {label}: {current_activation:.2f} + {increment:.2f} ({strength}) = {new_activation:.2f} < {self.ACTIVATION_THRESHOLD} → PENDING")

        session["proactive_meta"] = meta
        try:
            mid_term._mark_dirty()
            mid_term._save_if_needed(force=False)
        except Exception as e:
            logger.error(f"[ActivationGate] mid-term save failed: {e}")

        return decision

    def _apply_gate_topic(self, memory, decision: dict, target_tid: str) -> dict:
        """独立管线:topic-level activation,持久化在topic_store"""
        topic_store = getattr(memory, "topic_store", None)
        if topic_store is None:
            return decision  # 无store可写,直接放行

        topic = topic_store.get_topic(target_tid)
        if not topic:
            return decision

        current_activation = float(topic.get("proactive_activation", 0.0) or 0.0)
        strength = decision.get("match_strength", "medium")
        increment = self.ACTIVATION_INCREMENT_BY_STRENGTH.get(strength, self.ACTIVATION_INCREMENT)
        new_activation = current_activation + increment
        label = f"topic {target_tid}"

        if new_activation >= self.ACTIVATION_THRESHOLD:
            # FIRE:
            #   1. activation重置为0(避免饱和后下次1.0+increment立刻再FIRE)
            #   2. callback_count++ → filter在下轮把本topic视为"已冷却"
            #   3. 记录last_callback_turn = 当前store turn → 用于"冷却N轮后自动结束"判定
            topic_store.set_activation(target_tid, 0.0)
            topic_store.mark_callback_used(target_tid)
            topic_store.set_last_callback_turn(target_tid, topic_store.current_turn())

            decision["activation_fired"] = True
            decision["activation_before"] = current_activation
            decision["activation_after"] = 0.0
            logger.info(f"[ActivationGate] {label}: {current_activation:.2f} + {increment:.2f} ({strength}) = {new_activation:.2f} >= {self.ACTIVATION_THRESHOLD} → FIRE (cb_count++ + reset)")
        else:
            topic_store.set_activation(target_tid, new_activation)
            decision["should_callback"] = False
            decision["activation_pending"] = True
            decision["activation_before"] = current_activation
            decision["activation_after"] = new_activation
            decision["_original_thoughts"] = decision.get("thoughts", "")
            decision["thoughts"] = f"话题激活中 ({new_activation:.0%}, {strength})：{decision.get('thoughts', '')[:60]}"
            logger.debug(f"[ActivationGate] {label}: {current_activation:.2f} + {increment:.2f} ({strength}) = {new_activation:.2f} < {self.ACTIVATION_THRESHOLD} → PENDING")

        return decision

    def get_threshold(self) -> float:
        """获取激活阈值"""
        return self.ACTIVATION_THRESHOLD

    def get_increment(self, strength: str = "medium") -> float:
        """获取增量值"""
        return self.ACTIVATION_INCREMENT_BY_STRENGTH.get(strength, self.ACTIVATION_INCREMENT)


# 全局单例
_activation_gate: Optional[ActivationGate] = None


def get_activation_gate() -> ActivationGate:
    """获取激活门控单例"""
    global _activation_gate
    if _activation_gate is None:
        _activation_gate = ActivationGate()
    return _activation_gate