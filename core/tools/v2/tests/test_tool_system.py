"""
工具系统 V2 单元测试
"""

import asyncio
import os
import tempfile
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from pydantic import BaseModel, Field

from core.tools.v2 import (
    Tool,
    build_tool,
    ToolResult,
    ToolUseContext,
    PermissionContext,
    PermissionMode,
    PermissionResult,
    PermissionBehavior,
    ValidationResult,
    ToolRegistry,
    register_tool,
    get_tool,
    list_tools,
    unregister_tool,
    ToolPool,
    assemble_tool_pool,
    ProgressTracker,
    ProgressBuilder,
    ProgressContext,
    ToolSearchEngine,
    DeferredToolLoader,
    ToolExecutor,
    ToolSystem,
    ToolExecutionConfig,
    get_tool_system,
    init_tool_system,
)
from core.tools.v2.builtin_tools import (
    create_file_read_tool,
    create_file_write_tool,
    create_bash_tool,
    create_glob_tool,
    get_all_builtin_tools,
    register_builtin_tools,
)


class TestInput(BaseModel):
    """测试输入"""
    value: str = Field(description="测试值")
    count: int = Field(default=1, description="计数")


class TestOutput(BaseModel):
    """测试输出"""
    result: str
    success: bool = True


class TestToolBuilding:
    """工具构建测试"""

    def test_build_tool_basic(self):
        """测试基本工具构建"""

        async def test_call(args: TestInput, context: ToolUseContext) -> ToolResult:
            return ToolResult(data={"result": args.value * args.count})

        tool = build_tool(
            name="test_tool",
            description="测试工具",
            input_schema=TestInput,
            call=test_call,
        )

        assert tool.name == "test_tool"
        assert tool.description == "测试工具"
        assert tool.is_enabled()

    def test_build_tool_with_options(self):
        """测试带选项的工具构建"""

        async def test_call(args: TestInput, context: ToolUseContext) -> ToolResult:
            return ToolResult(data={"result": args.value})

        tool = build_tool(
            name="test_tool",
            description="测试工具",
            input_schema=TestInput,
            call=test_call,
            aliases=["test", "tt"],
            search_hint="test hint",
            is_read_only=lambda input_data: True,
            is_destructive=lambda input_data: False,
        )

        assert "test" in tool.aliases
        assert "tt" in tool.aliases
        assert tool.search_hint == "test hint"
        assert tool.is_read_only(TestInput(value="test"))

    def test_tool_json_schema(self):
        """测试JSON Schema生成"""

        async def test_call(args: TestInput, context: ToolUseContext) -> ToolResult:
            return ToolResult(data={})

        tool = build_tool(
            name="test_tool",
            description="测试工具",
            input_schema=TestInput,
            call=test_call,
        )

        schema = tool.get_json_schema()
        assert schema["type"] == "object"
        assert "value" in schema["properties"]
        assert "count" in schema["properties"]

    @pytest.mark.asyncio
    async def test_tool_call(self):
        """测试工具调用"""

        async def test_call(args: TestInput, context: ToolUseContext) -> ToolResult:
            return ToolResult(data={"result": args.value * args.count})

        tool = build_tool(
            name="test_tool",
            description="测试工具",
            input_schema=TestInput,
            call=test_call,
        )

        context = ToolUseContext()
        result = await tool.call(
            args=TestInput(value="hello", count=3),
            context=context,
            can_use_tool=lambda *args: {"behavior": "allow"},
        )

        assert result.data["result"] == "hellohellohello"


class TestRegistry:
    """注册表测试"""

    def setup_method(self):
        """每个测试方法前的设置"""
        self.registry = ToolRegistry()

    def test_register_tool(self):
        """测试工具注册"""
        tool = create_file_read_tool()
        self.registry.register(tool, category="file")

        assert self.registry.has("read_file")
        assert self.registry.get("read_file") == tool

    def test_unregister_tool(self):
        """测试工具注销"""
        tool = create_file_read_tool()
        self.registry.register(tool)

        assert self.registry.has("read_file")
        assert self.registry.unregister("read_file")
        assert not self.registry.has("read_file")

    def test_list_tools(self):
        """测试列出工具"""
        tools = get_all_builtin_tools()
        for tool in tools:
            self.registry.register(tool)

        all_tools = self.registry.list_all()
        assert len(all_tools) >= 7

    def test_search_tools(self):
        """测试搜索工具"""
        tools = get_all_builtin_tools()
        for tool in tools:
            self.registry.register(tool)

        results = self.registry.search("file")
        assert len(results) >= 3


class TestPermission:
    """权限系统测试"""

    def test_permission_context_creation(self):
        """测试权限上下文创建"""
        context = PermissionContext(
            mode=PermissionMode.DEFAULT,
        )

        assert context.is_default_mode()
        assert not context.is_bypass_mode()
        assert not context.is_auto_mode()

    def test_permission_context_modes(self):
        """测试权限模式"""
        bypass_context = PermissionContext(mode=PermissionMode.BYPASS)
        assert bypass_context.is_bypass_mode()

        auto_context = PermissionContext(mode=PermissionMode.AUTO)
        assert auto_context.is_auto_mode()

    def test_permission_result(self):
        """测试权限结果"""
        allow = PermissionResult.allow()
        assert allow.is_allowed()
        assert not allow.is_denied()

        deny = PermissionResult.deny("Access denied")
        assert deny.is_denied()
        assert deny.message == "Access denied"

        ask = PermissionResult.ask("Please confirm")
        assert ask.requires_confirmation()


class TestProgress:
    """进度系统测试"""

    def setup_method(self):
        """每个测试方法前的设置"""
        self.tracker = ProgressTracker()

    def test_progress_tracker(self):
        """测试进度追踪"""
        events = []

        def callback(event):
            events.append(event)

        self.tracker.register_callback(callback)

        self.tracker.start("test-id", "test_tool")
        assert len(events) == 1
        assert events[0].tool_name == "test_tool"

        self.tracker.complete("test-id", "test_tool")
        assert len(events) == 2

    def test_progress_builder(self):
        """测试进度构建器"""
        bash_progress = ProgressBuilder.bash(
            command="ls -la",
            output="file1\nfile2",
            is_running=True,
        )

        assert bash_progress.command == "ls -la"
        assert bash_progress.type == "bash_progress"

        file_progress = ProgressBuilder.file_read(
            file_path="/test/file.txt",
            bytes_read=100,
            total_bytes=1000,
        )

        assert file_progress.file_path == "/test/file.txt"
        assert file_progress.percentage == 10.0


class TestToolPool:
    """工具池测试"""

    def test_tool_pool_creation(self):
        """测试工具池创建"""
        tools = get_all_builtin_tools()
        pool = ToolPool(tools=tools)

        assert len(pool) >= 7
        assert pool.has("read_file")

    def test_tool_pool_filter(self):
        """测试工具池过滤"""
        tools = get_all_builtin_tools()
        pool = ToolPool(tools=tools)

        filtered = pool.filter(lambda t: "file" in t.name.lower())
        assert len(filtered) >= 3

    def test_assemble_tool_pool(self):
        """测试组装工具池"""
        tools = get_all_builtin_tools()
        permission_context = PermissionContext(mode=PermissionMode.DEFAULT)

        pool = assemble_tool_pool(
            built_in_tools=tools,
            permission_context=permission_context,
        )

        assert len(pool) >= 7


class TestSearch:
    """搜索系统测试"""

    def test_search_engine(self):
        """测试搜索引擎"""
        tools = get_all_builtin_tools()
        engine = ToolSearchEngine(tools=tools)

        results = engine.search("file")
        assert len(results) >= 3

        results = engine.search("bash")
        assert len(results) >= 1

    def test_search_suggestions(self):
        """测试搜索建议"""
        tools = get_all_builtin_tools()
        engine = ToolSearchEngine(tools=tools)

        suggestions = engine.suggest("read")
        assert len(suggestions) >= 1
        assert "read_file" in suggestions

    def test_deferred_loader(self):
        """测试延迟加载器"""
        loader = DeferredToolLoader()

        call_count = 0

        def load_tool():
            nonlocal call_count
            call_count += 1
            return create_file_read_tool()

        loader.register_deferred("read_file", load_tool)

        assert loader.is_deferred("read_file")
        assert not loader.is_loaded("read_file")

        tool = loader.load("read_file")
        assert tool is not None
        assert tool.name == "read_file"
        assert call_count == 1

        assert loader.is_loaded("read_file")
        assert not loader.is_deferred("read_file")


class TestExecutor:
    """执行器测试"""

    def setup_method(self):
        """每个测试方法前的设置"""
        self.config = ToolExecutionConfig(
            enable_progress=False,
            enable_permissions=False,
        )
        self.executor = ToolExecutor(self.config)

        for tool in get_all_builtin_tools():
            self.executor._registry.register(tool)

    @pytest.mark.asyncio
    async def test_execute_tool(self):
        """测试工具执行"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("Hello, World!")
            temp_path = f.name

        try:
            result = await self.executor.execute(
                tool_name="read_file",
                input_data={"file_path": temp_path},
            )

            assert result.success
            assert "Hello, World!" in result.result.get("content", "")
        finally:
            os.unlink(temp_path)

    @pytest.mark.asyncio
    async def test_execute_nonexistent_tool(self):
        """测试执行不存在的工具"""
        result = await self.executor.execute(
            tool_name="nonexistent_tool",
            input_data={},
        )

        assert not result.success
        assert "not found" in result.error

    @pytest.mark.asyncio
    async def test_execute_with_permission(self):
        """测试带权限的执行"""
        self.executor.config.enable_permissions = True

        permission_context = PermissionContext(
            mode=PermissionMode.BYPASS,
        )

        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("Test content")
            temp_path = f.name

        try:
            result = await self.executor.execute(
                tool_name="read_file",
                input_data={"file_path": temp_path},
                permission_context=permission_context,
            )

            assert result.success
        finally:
            os.unlink(temp_path)


class TestToolSystem:
    """工具系统测试"""

    def test_tool_system_initialization(self):
        """测试工具系统初始化"""
        system = init_tool_system()

        assert system is not None
        assert system.executor is not None
        assert system.registry is not None

    def test_tool_system_register(self):
        """测试工具系统注册"""
        system = ToolSystem()

        tool = create_file_read_tool()
        system.register_tool(tool)

        assert system.get_tool("read_file") == tool

    def test_tool_system_search(self):
        """测试工具系统搜索"""
        system = ToolSystem()

        for tool in get_all_builtin_tools():
            system.register_tool(tool)

        results = system.search_tools("file")
        assert len(results) >= 3


class TestBuiltinTools:
    """内置工具测试"""

    @pytest.mark.asyncio
    async def test_file_read_tool(self):
        """测试文件读取工具"""
        tool = create_file_read_tool()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("Line 1\nLine 2\nLine 3")
            temp_path = f.name

        try:
            context = ToolUseContext()
            result = await tool.call(
                args=TestInput.__class__.__bases__[0](file_path=temp_path),
                context=context,
                can_use_tool=lambda *args: {"behavior": "allow"},
            )

            assert "Line 1" in str(result.data)
        finally:
            os.unlink(temp_path)

    @pytest.mark.asyncio
    async def test_file_write_tool(self):
        """测试文件写入工具"""
        tool = create_file_write_tool()

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = os.path.join(temp_dir, "test.txt")

            context = ToolUseContext()
            result = await tool.call(
                args={"file_path": temp_path, "content": "Test content"},
                context=context,
                can_use_tool=lambda *args: {"behavior": "allow"},
            )

            assert result.data.get("success", False)
            assert os.path.exists(temp_path)

    @pytest.mark.asyncio
    async def test_bash_tool(self):
        """测试Bash工具"""
        tool = create_bash_tool()

        context = ToolUseContext()
        result = await tool.call(
            args={"command": "echo 'Hello'"},
            context=context,
            can_use_tool=lambda *args: {"behavior": "allow"},
        )

        assert result.data.get("exit_code") == 0
        assert "Hello" in result.data.get("stdout", "")

    @pytest.mark.asyncio
    async def test_glob_tool(self):
        """测试Glob工具"""
        tool = create_glob_tool()

        with tempfile.TemporaryDirectory() as temp_dir:
            test_file = os.path.join(temp_dir, "test.txt")
            with open(test_file, "w") as f:
                f.write("test")

            context = ToolUseContext()
            result = await tool.call(
                args={"pattern": "*.txt", "path": temp_dir},
                context=context,
                can_use_tool=lambda *args: {"behavior": "allow"},
            )

            assert result.data.get("count", 0) >= 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
