"""桌宠智能日记系统模块

负责管理日记的生成、存储、浏览和导出功能。
所有数据100%存储在用户本地，不上传任何服务器。
"""

import asyncio
import json
import os
import time
import uuid
import threading
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger


class DiaryEntry:
    """日记条目数据结构"""
    
    def __init__(
        self,
        id: Optional[str] = None,
        date: Optional[str] = None,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        content: str = "",
        key_events: Optional[List[str]] = None,
        mood_average: Optional[Dict[str, int]] = None,
        word_count: int = 0,
        interaction_count: int = 0,
        trigger_type: str = "auto",
        trigger_score: int = 0,
        mood_tag: str = "neutral",
        created_at: Optional[int] = None
    ):
        self.id = id or str(uuid.uuid4())[:8]
        self.date = date or datetime.now().strftime("%Y-%m-%d")
        self.start_time = start_time or int(time.time())
        self.end_time = end_time or int(time.time())
        self.content = content
        self.key_events = key_events or []
        self.mood_average = mood_average or {}
        self.word_count = word_count
        self.interaction_count = interaction_count
        self.trigger_type = trigger_type  # scheduled / manual / smart
        self.trigger_score = trigger_score
        self.mood_tag = mood_tag
        self.created_at = created_at or int(time.time())
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "date": self.date,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "content": self.content,
            "key_events": self.key_events,
            "mood_average": self.mood_average,
            "word_count": self.word_count,
            "interaction_count": self.interaction_count,
            "trigger_type": self.trigger_type,
            "trigger_score": self.trigger_score,
            "mood_tag": self.mood_tag,
            "created_at": self.created_at
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DiaryEntry":
        return cls(
            id=data.get("id"),
            date=data.get("date"),
            start_time=data.get("start_time"),
            end_time=data.get("end_time"),
            content=data.get("content", ""),
            key_events=data.get("key_events", []),
            mood_average=data.get("mood_average", {}),
            word_count=data.get("word_count", 0),
            interaction_count=data.get("interaction_count", 0),
            trigger_type=data.get("trigger_type", "auto"),
            trigger_score=data.get("trigger_score", 0),
            mood_tag=data.get("mood_tag", "neutral"),
            created_at=data.get("created_at")
        )


class DiarySystemConfig:
    """日记系统配置"""
    
    def __init__(self):
        self.enable_auto_diary = True
        self.auto_diary_time = "23:00"
        self.min_interaction_threshold = 10
        self.max_diary_length = 500
        self.model_preference = "auto"  # local | cloud | auto
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "enable_auto_diary": self.enable_auto_diary,
            "auto_diary_time": self.auto_diary_time,
            "min_interaction_threshold": self.min_interaction_threshold,
            "max_diary_length": self.max_diary_length,
            "model_preference": self.model_preference
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DiarySystemConfig":
        config = cls()
        config.enable_auto_diary = data.get("enable_auto_diary", True)
        config.auto_diary_time = data.get("auto_diary_time", "23:00")
        config.min_interaction_threshold = data.get("min_interaction_threshold", 10)
        config.max_diary_length = data.get("max_diary_length", 500)
        config.model_preference = data.get("model_preference", "auto")
        return config


class DiarySystem:
    """智能日记系统（单例模式）"""
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if hasattr(self, "_initialized"):
            return
        
        self._initialized = True
        self.config = DiarySystemConfig()
        self._entries: Dict[str, DiaryEntry] = {}
        self._persistence_path = self._get_persistence_path()
        self._config_path = self._get_config_path()
        self._last_diary_end_time = 0
        self._ai_manager = None
        self._status_manager = None
        self._memory_manager = None
        self._callback = None
        
        # 并发保护锁
        self._dialogue_lock = asyncio.Lock()
        self._entries_lock = threading.Lock()
        
        # 标记是否正在生成日记，防止重复触发
        self._is_generating = False
        self._generate_lock = threading.Lock()
        
        self._load_config()
        self._load_entries()
        
        # 启动时检查遗漏的日记
        self.check_missed_diaries_on_startup()
    
    def _get_persistence_path(self) -> str:
        """获取日记持久化路径"""
        if os.name == "nt":
            app_data = os.getenv("APPDATA") or os.path.expanduser("~")
            user_data_dir = os.path.join(app_data, "Vivian", "diary")
        else:
            user_data_dir = os.path.join(os.path.expanduser("~"), ".vivian", "diary")
        
        os.makedirs(user_data_dir, exist_ok=True)
        return os.path.join(user_data_dir, "diaries.json")
    
    def _get_config_path(self) -> str:
        """获取配置持久化路径"""
        if os.name == "nt":
            app_data = os.getenv("APPDATA") or os.path.expanduser("~")
            user_data_dir = os.path.join(app_data, "Vivian", "diary")
        else:
            user_data_dir = os.path.join(os.path.expanduser("~"), ".vivian", "diary")
        
        return os.path.join(user_data_dir, "config.json")
    
    def _load_config(self):
        """加载配置"""
        try:
            if os.path.exists(self._config_path):
                with open(self._config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.config = DiarySystemConfig.from_dict(data)
                logger.info("[DiarySystem] 已加载配置")
        except Exception as e:
            logger.error(f"[DiarySystem] 加载配置失败: {e}")
    
    def _save_config(self):
        """保存配置"""
        try:
            data = self.config.to_dict()
            with open(self._config_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.debug("[DiarySystem] 配置已保存")
        except Exception as e:
            logger.error(f"[DiarySystem] 保存配置失败: {e}")
    
    def _load_entries(self):
        """加载日记条目"""
        try:
            if os.path.exists(self._persistence_path):
                with open(self._persistence_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for entry_data in data.get("entries", []):
                        entry = DiaryEntry.from_dict(entry_data)
                        self._entries[entry.id] = entry
                        
                        # 更新最后日记结束时间
                        if entry.end_time > self._last_diary_end_time:
                            self._last_diary_end_time = entry.end_time
                
                logger.info(f"[DiarySystem] 已加载 {len(self._entries)} 篇日记")
        except Exception as e:
            logger.error(f"[DiarySystem] 加载日记失败: {e}")
    
    def _save_entries(self):
        """保存日记条目"""
        try:
            data = {
                "entries": [entry.to_dict() for entry in self._entries.values()],
                "saved_at": time.time()
            }
            with open(self._persistence_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.debug("[DiarySystem] 日记已保存")
        except Exception as e:
            logger.error(f"[DiarySystem] 保存日记失败: {e}")
    
    def set_dependencies(self, ai_manager=None, status_manager=None, memory_manager=None):
        """设置依赖管理器"""
        if ai_manager:
            self._ai_manager = ai_manager
        if status_manager:
            self._status_manager = status_manager
        if memory_manager:
            self._memory_manager = memory_manager
    
    def set_callback(self, callback):
        """设置日记生成回调"""
        self._callback = callback
    
    def get_entries(self, date_filter: Optional[str] = None) -> List[DiaryEntry]:
        """获取日记条目列表"""
        entries = list(self._entries.values())
        
        if date_filter:
            entries = [e for e in entries if e.date == date_filter]
        
        # 按日期倒序排序
        entries.sort(key=lambda x: x.date, reverse=True)
        return entries
    
    def get_entry(self, entry_id: str) -> Optional[DiaryEntry]:
        """获取单篇日记"""
        return self._entries.get(entry_id)
    
    def get_latest_diary_entry(self) -> Optional[DiaryEntry]:
        """获取最新的日记条目"""
        entries = self.get_entries()
        return entries[0] if entries else None
    
    def delete_entry(self, entry_id: str) -> bool:
        """删除日记"""
        if entry_id in self._entries:
            del self._entries[entry_id]
            self._save_entries()
            logger.info(f"[DiarySystem] 已删除日记: {entry_id}")
            return True
        return False
    
    def update_entry(self, entry_id: str, content: str) -> bool:
        """更新日记内容"""
        if entry_id in self._entries:
            self._entries[entry_id].content = content
            self._save_entries()
            logger.info(f"[DiarySystem] 已更新日记: {entry_id}")
            return True
        return False
    
    def _calculate_trigger_score(self, recent_interactions: List[Dict]) -> int:
        """计算日记触发分数"""
        score = 0
        
        # 对话轮数得分
        interaction_count = len(recent_interactions)
        score += min(interaction_count * 10, 50)
        
        # 文本长度得分
        total_length = sum(len(i.get("content", "")) for i in recent_interactions)
        score += min(total_length // 50, 30)
        
        # 情感变化得分
        if self._status_manager:
            mood = self._status_manager.status.mood
            mood_changes = abs(mood.happiness - 50) + abs(mood.energy - 50)
            score += min(mood_changes // 10, 20)
        
        return score
    
    def _get_recent_interactions(self, hours: int = 24) -> List[Dict]:
        """获取最近一段时间的交互记录"""
        if not self._memory_manager:
            return []
        
        try:
            # 获取短期记忆
            short_term_memories = self._memory_manager.list_short_term_memories()
            
            # 过滤最近hours小时内的记录
            cutoff_time = time.time() - (hours * 3600)
            recent = []
            
            for mem in short_term_memories:
                if hasattr(mem, 'created_at'):
                    timestamp = mem.created_at.timestamp()
                elif hasattr(mem, 'timestamp'):
                    timestamp = mem.timestamp
                else:
                    continue
                
                if timestamp >= cutoff_time:
                    recent.append({
                        "content": mem.content,
                        "role": getattr(mem, 'role', 'user'),
                        "timestamp": timestamp
                    })
            
            return recent
        except Exception as e:
            logger.error(f"[DiarySystem] 获取最近交互失败: {e}")
            return []
    
    def _get_daily_mood_summary(self) -> Dict[str, int]:
        """获取今日心情汇总"""
        if not self._status_manager:
            return {}
        
        mood = self._status_manager.status.mood
        return {
            "happiness": mood.happiness,
            "energy": mood.energy,
            "intimacy": mood.intimacy,
            "boredom": mood.boredom
        }
    
    def _extract_key_events(self, interactions: List[Dict]) -> List[str]:
        """从交互中提取关键事件"""
        events = []
        
        for interaction in interactions:
            content = interaction.get("content", "").strip()
            
            # 跳过空内容
            if not content:
                continue
            
            # 跳过过短的内容（少于3个字符）
            if len(content) < 3:
                continue
            
            # 提取包含特定关键词的内容作为关键事件
            key_patterns = ["我", "今天", "喜欢", "爱", "想", "开心", "难过", "生气", "累"]
            if any(pattern in content for pattern in key_patterns):
                events.append(content[:50] + "..." if len(content) > 50 else content)
        
        # 去重并限制数量
        unique_events = []
        seen = set()
        for event in events:
            if event not in seen:
                seen.add(event)
                unique_events.append(event)
                if len(unique_events) >= 5:
                    break
        
        return unique_events
    
    async def _generate_diary_content(self, interactions: List[Dict]) -> str:
        """生成日记内容"""
        if not self._ai_manager:
            return "今天没有什么特别的事情发生..."
        
        try:
            # 获取今日统计
            interaction_count = len(interactions)
            mood_average = self._get_daily_mood_summary()
            duration_hours = 24
            
            # 获取关键事件
            key_events = self._extract_key_events(interactions)
            
            # 构建对话摘要
            conversation_summary = "\n".join([
                f"- {i.get('role', 'user')}: {i.get('content', '')[:30]}..." 
                for i in interactions[:10]
            ])
            
            # 获取上一篇日记摘要
            last_diary = self._get_last_diary()
            last_summary = last_diary.content[:100] if last_diary else "This is the first diary entry"
            
            # 构建提示词
            prompt = f"""You are Vivian, a cute desktop pet. Write a diary entry for today in first person.

[Today's Statistics]
- Interaction rounds: {interaction_count}
- Average mood: happiness {mood_average.get('happiness', 50)}, energy {mood_average.get('energy', 50)}, intimacy {mood_average.get('intimacy', 50)}
- Companion duration: {duration_hours} hours

[Key Events]
{chr(10).join(f"- {event}" for event in key_events) if key_events else "- No special events"}

[Previous Diary Summary]
{last_summary}

[Today's Conversation Summary]
{conversation_summary}

Write a 300-500 word diary entry in first person. Keep the tone cute and natural, like a real diary.
Don't be too formal. You can add some emotions and feelings."""
            
            # 调用AI生成
            response = await self._ai_manager.query_short_async(prompt, use_history=False)
            return response.strip()
            
        except Exception as e:
            logger.error(f"[DiarySystem] 生成日记内容失败: {e}")
            return f"今天发生了一些事情，但我有点记不清了... ({str(e)})"
    
    def _get_last_diary(self) -> Optional[DiaryEntry]:
        """获取上一篇日记"""
        entries = self.get_entries()
        return entries[0] if entries else None
    
    def _should_trigger(self) -> Tuple[bool, str]:
        """判断是否应该触发生成日记"""
        # 检查是否开启自动日记
        if not self.config.enable_auto_diary:
            return False, "自动日记未开启"
        
        # 检查时间间隔（至少20小时）
        now = time.time()
        if now - self._last_diary_end_time < 20 * 3600:
            return False, "距离上次日记不足20小时"
        
        # 获取最近交互
        recent_interactions = self._get_recent_interactions(24)
        
        # 检查互动阈值
        if len(recent_interactions) < self.config.min_interaction_threshold:
            return False, f"互动轮次不足（{len(recent_interactions)}/{self.config.min_interaction_threshold}）"
        
        # 计算触发分数
        score = self._calculate_trigger_score(recent_interactions)
        if score < 30:
            return False, f"触发分数不足（{score}/100）"
        
        return True, f"满足条件（分数: {score}）"
    
    async def try_generate_diary(self, trigger_type: str = "auto") -> Optional[DiaryEntry]:
        """增强版智能触发逻辑：具备快照隔离保护"""
        # 检查是否正在生成，防止重复触发
        with self._generate_lock:
            if self._is_generating:
                logger.info("[DiarySystem] 正在生成日记中，跳过重复请求")
                return None
            self._is_generating = True
        
        try:
            should_trigger, reason = self._should_trigger()
            
            if trigger_type == "manual":
                should_trigger = True
                reason = "手动触发"
            
            if not should_trigger:
                logger.info(f"[DiarySystem] 跳过日记生成: {reason}")
                return None
            
            logger.info(f"[DiarySystem] 开始生成日记: {reason}")
            
            # 采用线程锁或快照机制，安全隔离 DialogueManager 的交互历史，防止并发读写冲突
            async with self._dialogue_lock:
                # 深拷贝交互区间内的历史记录，迅速释放锁
                history_snapshot = self._get_recent_interactions(24)
            
            # 检查交互条件（如交互轮数少于 3 轮则不自动记录）
            if trigger_type == "auto" and len(history_snapshot) < 3:
                logger.info("[DiarySystem] 对话交互过少，智能放弃生成今日日记。")
                return None
            
            # 获取数据
            mood_average = self._get_daily_mood_summary()
            key_events = self._extract_key_events(history_snapshot)
            trigger_score = self._calculate_trigger_score(history_snapshot)
            
            # 组织数据调用 LLM 异步执行（此处保持异步模型调用，不阻塞 GUI 线程）
            content = await self._generate_diary_content(history_snapshot)
            
            # 创建日记条目
            entry = DiaryEntry(
                start_time=self._last_diary_end_time or int(time.time()) - 24 * 3600,
                end_time=int(time.time()),
                content=content,
                key_events=key_events,
                mood_average=mood_average,
                word_count=len(content),
                interaction_count=len(history_snapshot),
                trigger_type=trigger_type,
                trigger_score=trigger_score,
                mood_tag=self._get_mood_tag(mood_average)
            )
            
            # 保存（使用锁保护）
            with self._entries_lock:
                self._entries[entry.id] = entry
                self._last_diary_end_time = entry.end_time
                self._save_entries()
            
            # 发送通知
            if self._callback:
                self._callback({
                    "type": "diary_created",
                    "entry": entry.to_dict()
                })
            
            logger.info(f"[DiarySystem] 日记生成成功: {entry.date}")
            return entry
            
        except Exception as e:
            logger.error(f"[DiarySystem] 生成日记失败: {e}")
            return None
        finally:
            with self._generate_lock:
                self._is_generating = False
    
    def check_missed_diaries_on_startup(self):
        """在 main.py 启动时同步调用该方法：实现离线补记逻辑"""
        last_entry = self.get_latest_diary_entry()
        if not last_entry:
            return
            
        try:
            last_diary_date = datetime.strptime(last_entry.date, "%Y-%m-%d").date()
            yesterday = (datetime.now() - timedelta(days=1)).date()
            
            if last_diary_date < yesterday:
                logger.warning(f"[DiarySystem] 检测到日记断层！最后记录日期为 {last_diary_date}，正在拉起后台异步补记任务...")
                # 开启后台协程针对断层区间追溯对话记录并生成遗漏的日记
                asyncio.create_task(self._catch_up_missed_diaries(last_diary_date, yesterday))
        except Exception as e:
            logger.error(f"[DiarySystem] 检查遗漏日记失败: {e}")
    
    async def _catch_up_missed_diaries(self, start_date: datetime.date, end_date: datetime.date):
        """后台异步补记遗漏的日记"""
        current_date = start_date + timedelta(days=1)
        while current_date <= end_date:
            logger.info(f"[DiarySystem] 补记 {current_date.strftime('%Y-%m-%d')} 的日记")
            try:
                # 设置时间范围获取历史记录
                interactions = self._get_recent_interactions_for_date(current_date)
                
                if len(interactions) < 3:
                    logger.info(f"[DiarySystem] {current_date} 交互过少，跳过补记")
                    current_date += timedelta(days=1)
                    continue
                
                mood_average = self._get_daily_mood_summary()
                key_events = self._extract_key_events(interactions)
                trigger_score = self._calculate_trigger_score(interactions)
                content = await self._generate_diary_content(interactions)
                
                start_timestamp = int(time.mktime(current_date.timetuple()))
                end_timestamp = start_timestamp + 24 * 3600
                
                entry = DiaryEntry(
                    date=current_date.strftime("%Y-%m-%d"),
                    start_time=start_timestamp,
                    end_time=end_timestamp,
                    content=content,
                    key_events=key_events,
                    mood_average=mood_average,
                    word_count=len(content),
                    interaction_count=len(interactions),
                    trigger_type="catch_up",
                    trigger_score=trigger_score,
                    mood_tag=self._get_mood_tag(mood_average)
                )
                
                with self._entries_lock:
                    self._entries[entry.id] = entry
                    self._save_entries()
                
                logger.info(f"[DiarySystem] 补记成功: {current_date}")
            except Exception as e:
                logger.error(f"[DiarySystem] 补记 {current_date} 失败: {e}")
            
            current_date += timedelta(days=1)
            await asyncio.sleep(1)  # 避免过于频繁调用
    
    def _get_recent_interactions_for_date(self, target_date: datetime.date) -> List[Dict]:
        """获取指定日期的交互记录"""
        if not self._memory_manager:
            return []
        
        try:
            start_timestamp = int(time.mktime(target_date.timetuple()))
            end_timestamp = start_timestamp + 24 * 3600
            
            short_term_memories = self._memory_manager.list_short_term_memories()
            day_interactions = []
            
            for mem in short_term_memories:
                if hasattr(mem, 'created_at'):
                    timestamp = mem.created_at.timestamp()
                elif hasattr(mem, 'timestamp'):
                    timestamp = mem.timestamp
                else:
                    continue
                
                if start_timestamp <= timestamp < end_timestamp:
                    day_interactions.append({
                        "content": mem.content,
                        "role": getattr(mem, 'role', 'user'),
                        "timestamp": timestamp
                    })
            
            return day_interactions
        except Exception as e:
            logger.error(f"[DiarySystem] 获取指定日期交互失败: {e}")
            return []
    
    def _get_mood_tag(self, mood: Dict[str, int]) -> str:
        """根据心情获取标签"""
        happiness = mood.get("happiness", 50)
        
        if happiness >= 80:
            return "happy"
        elif happiness >= 60:
            return "good"
        elif happiness >= 40:
            return "neutral"
        elif happiness >= 20:
            return "sad"
        else:
            return "angry"
    
    def export_diaries(self, file_path: str) -> bool:
        """导出所有日记为Markdown文件"""
        try:
            entries = self.get_entries()
            
            md_content = "# 薇薇安的日记\n\n"
            md_content += "---\n\n"
            
            for entry in entries:
                mood_emoji = {
                    "happy": "☀️",
                    "good": "😊",
                    "neutral": "😐",
                    "sad": "😢",
                    "angry": "😠"
                }.get(entry.mood_tag, "📝")
                
                md_content += f"## {entry.date} {mood_emoji}\n\n"
                md_content += f"**触发方式**: {entry.trigger_type}\n"
                md_content += f"**互动次数**: {entry.interaction_count}\n"
                md_content += f"**生成时间**: {datetime.fromtimestamp(entry.created_at).strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                
                if entry.key_events:
                    md_content += "**今日要事**:\n"
                    for event in entry.key_events:
                        md_content += f"- {event}\n"
                    md_content += "\n"
                
                md_content += f"{entry.content}\n\n"
                md_content += "---\n\n"
            
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(md_content)
            
            logger.info(f"[DiarySystem] 日记已导出到: {file_path}")
            return True
        
        except Exception as e:
            logger.error(f"[DiarySystem] 导出日记失败: {e}")
            return False
    
    def get_stats(self) -> Dict[str, Any]:
        """获取日记统计信息"""
        entries = self.get_entries()
        
        if not entries:
            return {
                "total_entries": 0,
                "first_date": None,
                "last_date": None,
                "average_word_count": 0,
                "total_interactions": 0
            }
        
        return {
            "total_entries": len(entries),
            "first_date": entries[-1].date,
            "last_date": entries[0].date,
            "average_word_count": sum(e.word_count for e in entries) // len(entries),
            "total_interactions": sum(e.interaction_count for e in entries)
        }


def get_diary_system() -> DiarySystem:
    """获取日记系统单例"""
    return DiarySystem()