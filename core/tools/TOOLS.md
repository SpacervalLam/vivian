# Available Tools

Total: 35 tools

To view detailed description of a tool, call tool_list with tool_name parameter

- read_file: Read file contents. Supports reading large files with specified line range.
- edit_file: Edit file content. Use exact matching to replace specified text.
- write_file: Write file content. If file doesn't exist, create it. If it exists, overwrite it.
- bash: Execute Bash commands. Supports setting timeout and working directory.
- glob: Search files using Glob pattern. Supports recursive search.
- open_application: Launch Windows applications.
- search_files: Search for files in specified directory.
- close_application: Close a running application.
- open_folder: Open a folder.
- open_url: Open a URL in browser.
- set_wallpaper: Set desktop wallpaper. If no image path provided, automatically select a random wallpaper from system wallpaper folder.
- wallpaper_engine: Control Wallpaper Engine with command line. Supports: open (with wallpaper_path), pause, play (resume), stop, mute, unmute, next. Note: Wallpaper Engine must be running first.
- list_wallpapers: List all Wallpaper Engine wallpapers. Returns wallpaper list with wallpaper ID, name and file path. After using this tool, you can call wallpaper_engine tool with open operation to change wallpaper.
- take_screenshot: Take a screenshot of current screen and save it.
- minimize_window: Minimize current window.
- maximize_window: Maximize current window.
- close_window: Close current window.
- get_system_info: Get system information.
- get_clipboard_text: Get clipboard text content.
- set_clipboard_text: Set clipboard text content.
- get_running_processes: Get list of currently running processes.
- get_active_window: Get title of currently active window.
- copy_file: Copy a file.
- move_file: Move a file.
- delete_file: Delete a file or folder.
- create_file: Create a new file.
- list_files: List files in a directory.
- web_fetch: Get web page content. Used to retrieve content from specified URL.
- web_search: Search web content. Use search engine to find relevant information.
- grep: Search for matching content in files. Supports regular expressions and context display.
- tool_search: Search available tools. Search for matching tools based on function description.
- execute_code: Execute Python code.
- set_timer: Set timer reminder or timer to execute tools.
- cancel_timer: Cancel a timer task.
- list_timers: Get all timer tasks list.
