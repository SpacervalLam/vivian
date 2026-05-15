from loguru import logger
from PyQt5.QtCore import QPoint, QRect
from PyQt5.QtWidgets import QApplication

from core.tool_manager import BaseTool, tool


class WindowControlTools:
    """
    Window control tools class, containing a series of tools for controlling window position and size
    """

    def __init__(self, main_window):
        """
        Initialize window control tools

        Args:
            main_window: Main window instance
        """
        self.main_window = main_window

    def get_window_info_tool(self):
        """
        Get window info tool
        """

        @tool(
            name="get_window_info",
            description="Get current window position and size information",
        )
        def get_window_info() -> str:
            """
            Get current window position and size information

            Returns:
                Window info in JSON format
            """
            if self.main_window:
                pos = self.main_window.pos()
                size = self.main_window.size()
                return f'{{"x": {pos.x()}, "y": {pos.y()}, "width": {size.width()}, "height": {size.height()}}}'
            return '{"error": "No window reference"}'

        return get_window_info()

    def set_window_position_tool(self):
        """
        Set window position tool
        """

        @tool(
            name="set_window_position",
            description="Set window position with x and y coordinates",
        )
        def set_window_position(x: int, y: int) -> str:
            """
            Set window position

            Args:
                x: Window x-coordinate
                y: Window y-coordinate

            Returns:
                Operation result
            """
            if self.main_window:
                # Safety check: prevent window from moving off screen
                screen_geo = QApplication.primaryScreen().geometry()
                new_x = max(0, min(x, screen_geo.width() - 100))
                new_y = max(0, min(y, screen_geo.height() - 100))

                # Check if live2d_widget has smooth move functionality
                if hasattr(self.main_window, "live2d_widget") and hasattr(self.main_window.live2d_widget, "_smooth_move"):
                    logger.info(f"Smooth move window to ({new_x}, {new_y})")
                    self.main_window.live2d_widget._smooth_move(new_x, new_y)
                    return f"Successfully started smooth move to ({new_x}, {new_y})"
                else:
                    logger.info(f"Set window position to ({new_x}, {new_y})")
                    self.main_window.move(new_x, new_y)
                    return f"Successfully set window position to ({new_x}, {new_y})"
            return "Error: Cannot access window instance"

        return set_window_position()

    def set_window_size_tool(self):
        """
        Set window size tool
        """

        @tool(
            name="set_window_size",
            description="Adjust the size of Vivian's window. Standard ratio is usually 4:5 (e.g., 400x500). AI can use smaller window to express 'hiding' and larger window to express 'presence'.",
        )
        def set_window_size(width: int, height: int) -> str:
            """
            Adjust the size of Vivian's window

            Args:
                width: Window width (range: 200-1200)
                height: Window height (range: 250-1500)

            Returns:
                Operation result

            Spiritual usage suggestions:
            - Smaller window to express 'hiding' or 'shyness'
            - Larger window to express 'presence' or 'excitement'
            - Standard ratio is usually 4:5 (e.g., 400x500)
            """
            if self.main_window:
                # Get screen geometry to prevent window from going off screen
                screen_geo = QApplication.primaryScreen().geometry()
                
                # Get current window position
                current_pos = self.main_window.pos()
                
                # Limit to reasonable range to prevent AI from making window invisible or too large
                new_width = max(200, min(width, 1200))
                new_height = max(250, min(height, 1500))
                
                # Ensure window doesn't go off screen to the right or bottom
                max_available_width = screen_geo.width() - current_pos.x()
                max_available_height = screen_geo.height() - current_pos.y()
                
                # Keep at least 10px margin to avoid being completely off screen
                new_width = min(new_width, max_available_width - 10)
                new_height = min(new_height, max_available_height - 10)
                
                # Ensure minimum size is still respected
                new_width = max(200, new_width)
                new_height = max(250, new_height)

                logger.info(f"Set window size to {new_width}x{new_height}")

                # Check if live2d_widget has smooth resize functionality
                if hasattr(self.main_window, "live2d_widget") and hasattr(self.main_window.live2d_widget, "_smooth_resize"):
                    self.main_window.live2d_widget._smooth_resize(new_width, new_height)
                    return f"Successfully started smooth resize to {new_width}x{new_height}"
                else:
                    # Thread-safe resize using QMetaObject.invokeMethod
                    from PyQt5.QtCore import Q_ARG, QMetaObject, Qt

                    QMetaObject.invokeMethod(
                        self.main_window,
                        "resize",
                        Qt.QueuedConnection,
                        Q_ARG(int, new_width),
                        Q_ARG(int, new_height),
                    )

                    return f"Window size adjusted to: {new_width}x{new_height}"
            return "Adjustment failed, main window not found."

        return set_window_size()

    def get_watch_mode_tool(self):
        """
        Get eye follow status tool
        """

        @tool(name="get_watch_mode", description="Get current eye follow mode status")
        def get_watch_mode() -> str:
            """
            Get current eye follow mode status

            Returns:
                Eye follow status in JSON format
            """
            if self.main_window and hasattr(self.main_window, "live2d_widget"):
                is_enabled = self.main_window.live2d_widget.get_mouse_follow()
                return f'{{"enabled": {str(is_enabled).lower()}}}'
            return '{"error": "No window or widget reference"}'

        return get_watch_mode()

    def toggle_watch_mode_tool(self):
        """
        Toggle eye follow mode tool
        """

        @tool(
            name="toggle_watch_mode",
            description="Enable/disable eye follow mode. Enable to focus on user, disable to enter 'daze/wandering' mode.",
        )
        def toggle_watch_mode(active: bool) -> str:
            """
            Toggle eye follow mode

            Args:
                active: Whether to enable eye follow
                    - True: Enable, indicates focusing on user
                    - False: Disable, enters 'daze/wandering' mode

            Returns:
                Operation result

            Spiritual usage suggestions:
            - Enable: Shows attention to user, wants to interact
            - Disable: Enters daze mode, shows boredom, anger or independent thinking
            """
            if self.main_window and hasattr(self.main_window, "live2d_widget"):
                self.main_window.live2d_widget.set_mouse_follow(active)
                status = "enabled" if active else "disabled"
                return f"Successfully {status} eye follow mode"
            return "Error: Cannot access window or Live2D widget instance"

        return toggle_watch_mode()

    def perform_action_tool(self):
        """
        Perform action tool
        """

        @tool(
            name="perform_action",
            description="Let Vivian perform a specific action, parameter is action_name",
        )
        def perform_action(action_name: str) -> str:
            """
            Let Vivian perform a specific action

            Args:
                action_name: Action name, optional values: wave_hand, stretch_arms, nod_head, look_around, tilt_head, smile, blush, frown, surprised

            Returns:
                Execution result
            """
            if self.main_window and hasattr(self.main_window, "live2d_widget"):
                live2d_widget = self.main_window.live2d_widget
                if hasattr(live2d_widget, action_name):
                    getattr(live2d_widget, action_name)()
                    return f"Successfully performed action: {action_name}"
                return f"Error: Action {action_name} does not exist"
            return "Error: Cannot access window or Live2D widget instance"

        return perform_action()

    def set_expression_tool(self):
        """
        Set expression tool
        """

        @tool(
            name="set_expression",
            description="Set Vivian's expression, parameter is expression_name",
        )
        def set_expression(expression_name: str) -> str:
            """
            Set Vivian's expression

            Args:
                expression_name: Expression name, optional values: smile, angry, shy, panic, cry, eye_roll

            Returns:
                Execution result
            """
            if self.main_window and hasattr(self.main_window, "live2d_widget"):
                live2d_widget = self.main_window.live2d_widget
                live2d_widget.set_expression(expression_name)
                return f"Successfully set expression to: {expression_name}"
            return "Error: Cannot access window or Live2D widget instance"

        return set_expression()

    def play_action_sequence_tool(self):
        """
        Play action sequence tool
        """

        @tool(
            name="play_action_sequence",
            description="Play action sequence with actions (action list) and interval (action interval) parameters",
        )
        def play_action_sequence(actions: list, interval: float = 0.5) -> str:
            """
            Play action sequence

            Args:
                actions: List of action names
                interval: Interval between actions in seconds

            Returns:
                Execution result
            """
            if self.main_window and hasattr(self.main_window, "live2d_widget"):
                live2d_widget = self.main_window.live2d_widget
                if hasattr(live2d_widget, "play_action_sequence"):
                    live2d_widget.play_action_sequence(actions, interval)
                    return f"Successfully played action sequence: {actions}"
                return "Error: play_action_sequence method does not exist"
            return "Error: Cannot access window or Live2D widget instance"

        return play_action_sequence()

    def set_behavior_mode_tool(self):
        """
        Set behavior mode tool
        """

        @tool(
            name="set_behavior_mode",
            description="Set behavior mode with frequency parameter (frequency mode: high/medium/low)",
        )
        def set_behavior_mode(frequency: str) -> str:
            """
            Set behavior mode

            Args:
                frequency: Frequency mode, optional values: high, medium, low

            Returns:
                Execution result
            """
            if self.main_window and hasattr(self.main_window, "live2d_widget"):
                live2d_widget = self.main_window.live2d_widget
                if hasattr(live2d_widget, "set_random_behavior_mode"):
                    result = live2d_widget.set_random_behavior_mode(frequency)
                    return result
                return "Error: set_random_behavior_mode method does not exist"
            return "Error: Cannot access window or Live2D widget instance"

        return set_behavior_mode()

    def get_all_tools(self):
        """
        Get all window control tools

        Returns:
            List of window control tools
        """
        return [
            self.get_window_info_tool(),
            self.set_window_position_tool(),
            self.set_window_size_tool(),
            self.get_watch_mode_tool(),
            self.toggle_watch_mode_tool(),
            self.perform_action_tool(),
            self.set_expression_tool(),
            self.play_action_sequence_tool(),
            self.set_behavior_mode_tool(),
        ]
