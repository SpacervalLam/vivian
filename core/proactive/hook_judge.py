"""
Hook闭环判定系统 - HookJudge

核心功能：
1. 异步Hook闭环判定
2. 支持session-level和topic-level两种模式
3. closure_type门控分级
4. 线程池并发处理

灵感来源：memoryos-agent/core/proactive/proactive_process/services/hook_judge.py
"""

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, Dict, List, Optional

from loguru import logger


class HookJudge:
    """Hook闭环判定系统"""

    def __init__(self):
        """初始化HookJudge"""
        # 配置常量（与memoryos-agent一致）
        self.ASYNC_HOOK_CLOSURE_ENABLED = os.environ.get("PROACTIVE_ASYNC_HOOK_CLOSURE", "on").lower() != "off"
        self.ASYNC_HOOK_MAX_SESSIONS = int(os.environ.get("PROACTIVE_ASYNC_HOOK_MAX_SESSIONS", "8"))
        self.ASYNC_HOOK_MAX_HOOKS = int(os.environ.get("PROACTIVE_ASYNC_HOOK_MAX_HOOKS", "12"))
        self.ASYNC_HOOK_WORKERS = int(os.environ.get("PROACTIVE_ASYNC_HOOK_WORKERS", "8"))

        # 虚拟hook前缀：表示该item来自task_status=active而非真正的open_hooks
        self._VIRTUAL_TASK_HOOK_PREFIX = "【任务】"

        # closure_type门控分级
        self.HOOK_CLOSURE_STRONG_TYPES = {"meta_cancel", "action_complete", "explicit_relief"}
        self.HOOK_CLOSURE_WEAK_TYPES = {"implicit_relief"}

        # 线程池（单例）
        self._executor = ThreadPoolExecutor(
            max_workers=self.ASYNC_HOOK_WORKERS,
            thread_name_prefix="hook-closure"
        )

        # Host回调（由外部注入）
        self._session_getter: Optional[Callable[[str], Optional[dict]]] = None
        self._lock_getter: Optional[Callable[[str], object]] = None
        self._save_session_meta_cb: Optional[Callable[[str], None]] = None

    def configure(
        self,
        *,
        session_getter: Callable[[str], Optional[dict]],
        lock_getter: Callable[[str], object],
        save_session_meta: Callable[[str], None]
    ):
        """
        配置Host回调

        Args:
            session_getter: 用session_id查session字典的回调
            lock_getter: 查session的Lock的回调
            save_session_meta: 触发保存session meta的回调
        """
        self._session_getter = session_getter
        self._lock_getter = lock_getter
        self._save_session_meta_cb = save_session_meta
        logger.info("[HookJudge] 已配置Host回调")

    def snapshot_open_hook_items(self, memory) -> List[dict]:
        """
        遍历两个hook来源,把每个open_hook/active task展开成独立判断单元

        来源1(legacy session-level): memory.mid_term_memory.sessions[sid].proactive_meta
        来源2(独立管线topic-level): memory.topic_store.list_topics()(若存在)

        Returns:
            item结构列表:
              · container_kind: "session" | "topic"
              · container_id: sid或tid
              · session_id: legacy字段(session来源时=sid;topic来源时=None)
              · 其余: summary, user_need, hook, callback_count, is_task_hook
        """
        items = []

        # ---- 来源1:legacy session-level ----
        mid_term = getattr(memory, "mid_term_memory", None)
        if mid_term is not None:
            sess_count = 0
            for sid, sess_obj in mid_term.sessions.items():
                if sess_count >= self.ASYNC_HOOK_MAX_SESSIONS:
                    break

                meta = sess_obj.get("proactive_meta") or {}
                hooks = list(meta.get("open_hooks") or [])
                task_status = meta.get("task_status")
                task_desc = (meta.get("task_description") or "").strip()

                # 如果没有hooks但有活跃任务，创建虚拟task hook
                if not hooks and task_status == "active" and task_desc \
                        and meta.get("should_proactive") is not False:
                    hooks = [f"{self._VIRTUAL_TASK_HOOK_PREFIX}{task_desc}"]

                if not hooks:
                    continue

                sess_count += 1
                callback_count = int(meta.get("callback_count", 0) or 0)

                for hook in hooks:
                    items.append({
                        "container_kind": "session",
                        "container_id": sid,
                        "session_id": sid,
                        "summary": (sess_obj.get("summary") or "")[:80],
                        "user_need": (meta.get("user_need") or "")[:60],
                        "hook": hook,
                        "callback_count": callback_count,
                        "is_task_hook": hook.startswith(self._VIRTUAL_TASK_HOOK_PREFIX),
                    })

                    if len(items) >= self.ASYNC_HOOK_MAX_HOOKS:
                        return items

        # ---- 来源2:独立管线topic-level ----
        topic_store = getattr(memory, "topic_store", None)
        if topic_store is not None and len(items) < self.ASYNC_HOOK_MAX_HOOKS:
            topic_count = 0
            for topic in topic_store.list_topics():
                if topic_count >= self.ASYNC_HOOK_MAX_SESSIONS:
                    break

                if topic.get("should_proactive") is False:
                    continue

                hooks = list(topic.get("open_hooks") or [])
                task_status = topic.get("task_status")
                task_desc = (topic.get("task_description") or "").strip()

                if not hooks and task_status == "active" and task_desc:
                    hooks = [f"{self._VIRTUAL_TASK_HOOK_PREFIX}{task_desc}"]

                if not hooks:
                    continue

                topic_count += 1
                tid = topic.get("topic_id")
                callback_count = int(topic.get("callback_count", 0) or 0)

                for hook in hooks:
                    items.append({
                        "container_kind": "topic",
                        "container_id": tid,
                        "session_id": None,
                        "summary": (topic.get("summary") or "")[:80],
                        "user_need": (topic.get("user_need") or "")[:60],
                        "hook": hook,
                        "callback_count": callback_count,
                        "is_task_hook": hook.startswith(self._VIRTUAL_TASK_HOOK_PREFIX),
                    })

                    if len(items) >= self.ASYNC_HOOK_MAX_HOOKS:
                        return items

        return items

    async def judge_closures(self, memory, user_message: str, recent_dialogs: List[dict] = None):
        """
        异步判定所有open hooks的闭环状态

        Args:
            memory: 记忆管理器
            user_message: 用户最新消息
            recent_dialogs: 最近对话历史（最多4轮）
        """
        if not self.ASYNC_HOOK_CLOSURE_ENABLED:
            return

        # 获取所有待判定的hook items
        items = self.snapshot_open_hook_items(memory)
        if not items:
            return

        logger.debug(f"[HookJudge] 发现 {len(items)} 个待判定的hooks")

        # 构建情境上下文
        context = {
            "user_message": user_message,
            "recent_dialogs": recent_dialogs[:4] if recent_dialogs else [],
            "timestamp": int(__import__('time').time())
        }

        # 提交到线程池并发处理
        futures = []
        for item in items:
            future = self._executor.submit(
                self._judge_single_hook,
                memory,
                item,
                context
            )
            futures.append(future)

        # 等待完成并收集结果
        for future in as_completed(futures):
            try:
                result = future.result()
                if result:
                    await self._handle_closure_result(memory, result)
            except Exception as e:
                logger.error(f"[HookJudge] 判定失败: {e}")

    def _judge_single_hook(self, memory, item: dict, context: dict) -> Optional[dict]:
        """
        单hook判定（在工作线程中执行）

        Args:
            memory: 记忆管理器
            item: hook item
            context: 情境上下文

        Returns:
            判定结果，如果需要关闭hook则返回结果字典
        """
        hook = item.get("hook")
        if not hook:
            return None

        user_message = context.get("user_message", "")
        if not user_message:
            return None

        # 简单的规则匹配（实际应调用LLM）
        # 这里实现一个简化版的规则引擎
        closure_type = self._detect_closure_type(hook, user_message, item)

        if closure_type:
            return {
                "item": item,
                "closure_type": closure_type,
                "confidence": 0.8,
                "reason": f"检测到{closure_type}类型的闭环信号"
            }

        return None

    def _detect_closure_type(self, hook: str, user_message: str, item: dict = None) -> Optional[str]:
        """
        检测闭环类型

        Args:
            hook: hook文本
            user_message: 用户消息
            item: hook item（可选，用于获取is_task_hook等信息）

        Returns:
            闭环类型字符串，None表示未检测到闭环
        """
        message_lower = user_message.lower()
        hook_lower = hook.lower()

        # 去除虚拟任务前缀
        if hook_lower.startswith(self._VIRTUAL_TASK_HOOK_PREFIX.lower()):
            hook_lower = hook_lower[4:]  # 移除"【任务】"

        # 获取关键词共现来判断相关性
        hook_keywords = set(hook_lower.split()) if hook_lower else set()
        message_words = set(message_lower.split())
        has_overlap = bool(hook_keywords & message_words) if hook_keywords else True

        # 检测各种闭环类型
        # 1. explicit_relief: 明确表示问题已解决
        explicit_keywords = ["完成", "搞定", "解决", "好了", "结束", "做完", "搞定了", "成功", "可以了", "足够了", "够了"]
        for keyword in explicit_keywords:
            if keyword in message_lower:
                # 检查是否与hook相关
                if has_overlap or not hook_keywords:
                    return "explicit_relief"

        # 2. action_complete: 动作完成
        action_keywords = ["已", "已经", "刚刚", "刚", "终于", "做好", "做完", "弄好", "搞完"]
        for keyword in action_keywords:
            if keyword in message_lower:
                if has_overlap or not hook_keywords:
                    return "action_complete"

        # 3. meta_cancel: 明确取消
        cancel_keywords = ["取消", "不用", "算了", "别", "停止", "不做了", "不要了", "放弃", "终止", "算了"]
        for keyword in cancel_keywords:
            if keyword in message_lower:
                return "meta_cancel"

        # 4. implicit_relief: 隐含解决
        relief_keywords = ["谢谢", "感谢", "辛苦了", "麻烦了", "好的", "知道了", "明白", "懂了", "理解了"]
        for keyword in relief_keywords:
            if keyword in message_lower:
                return "implicit_relief"

        # 5. topic_shift: 话题转移（检测到用户明显在转移话题）
        shift_keywords = ["但是", "不过", "话说回来", "对了", "说起来", "另外", "顺便问", "突然想到", "换个话题"]
        for keyword in shift_keywords:
            if keyword in message_lower:
                # 如果hook是虚拟任务hook且用户转移话题，可能表示放弃
                if item.get("is_task_hook", False):
                    return "meta_cancel"

        # 6. affirmation: 肯定回应
        affirm_keywords = ["对", "是的", "没错", "正确", "正是", "很好", "不错", "👍", "ok", "okay"]
        for keyword in affirm_keywords:
            if keyword in message_lower:
                if has_overlap or not hook_keywords:
                    return "implicit_relief"

        return None

    async def _handle_closure_result(self, memory, result: dict):
        """
        处理闭环判定结果

        Args:
            memory: 记忆管理器
            result: 判定结果
        """
        item = result.get("item")
        closure_type = result.get("closure_type")

        if not item or not closure_type:
            return

        # 根据强度决定是否关闭hook
        if closure_type in self.HOOK_CLOSURE_STRONG_TYPES:
            # 强类型：直接关闭
            await self._close_hook(memory, item)
            logger.info(f"[HookJudge] 关闭hook (强类型 {closure_type}): {item.get('hook')}")
        elif closure_type in self.HOOK_CLOSURE_WEAK_TYPES:
            # 弱类型：谨慎处理，可以降低激活度
            await self._weaken_hook(memory, item)
            logger.debug(f"[HookJudge] 弱化hook (弱类型 {closure_type}): {item.get('hook')}")

    async def _close_hook(self, memory, item: dict):
        """
        关闭hook

        Args:
            memory: 记忆管理器
            item: hook item
        """
        container_kind = item.get("container_kind")
        container_id = item.get("container_id")
        hook = item.get("hook")

        if container_kind == "session":
            # session-level关闭
            mid_term = getattr(memory, "mid_term_memory", None)
            if mid_term is not None:
                session = mid_term.sessions.get(container_id)
                if session:
                    meta = session.get("proactive_meta") or {}
                    open_hooks = meta.get("open_hooks") or []
                    if hook in open_hooks:
                        open_hooks.remove(hook)
                        meta["open_hooks"] = open_hooks
                        session["proactive_meta"] = meta
                        mid_term._mark_dirty()

        elif container_kind == "topic":
            # topic-level关闭
            topic_store = getattr(memory, "topic_store", None)
            if topic_store is not None:
                topic_store.close_hook(container_id, hook)

    async def _weaken_hook(self, memory, item: dict):
        """
        弱化hook（降低激活度）

        Args:
            memory: 记忆管理器
            item: hook item
        """
        container_kind = item.get("container_kind")
        container_id = item.get("container_id")

        if container_kind == "topic":
            topic_store = getattr(memory, "topic_store", None)
            if topic_store is not None:
                current_activation = topic_store.get_activation(container_id)
                new_activation = max(0.0, current_activation - 0.3)
                topic_store.set_activation(container_id, new_activation)

    def shutdown(self):
        """关闭线程池"""
        self._executor.shutdown(wait=True)
        logger.info("[HookJudge] 线程池已关闭")


# 全局单例
_hook_judge: Optional[HookJudge] = None


def get_hook_judge() -> HookJudge:
    """获取HookJudge单例"""
    global _hook_judge
    if _hook_judge is None:
        _hook_judge = HookJudge()
    return _hook_judge