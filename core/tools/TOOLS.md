# 可用工具列表

共 17 个工具：

## open_application
描述: 启动一个Windows应用程序
参数:
  - app_path (string) [可选]: 应用程序的完整路径，如 C:\Program Files\Notepad++\notepad++.exe

## close_application
描述: 关闭一个正在运行的应用程序
参数:
  - process_name (string) [可选]: 进程名称，如 notepad.exe

## open_folder
描述: 打开一个文件夹
参数:
  - path (string) [可选]: 文件夹路径

## open_url
描述: 在浏览器中打开网址
参数:
  - url (string) [可选]: 网址，如 https://www.example.com

## set_wallpaper
描述: 设置桌面壁纸
参数:
  - image_path (string) [可选]: 图片文件的完整路径

## take_screenshot
描述: 截取当前屏幕并保存
参数:
  - save_path (string) [可选]: 截图保存路径（可选），默认保存到桌面

## minimize_window
描述: 最小化当前窗口

## maximize_window
描述: 最大化当前窗口

## close_window
描述: 关闭当前窗口

## get_system_info
描述: 获取系统信息

## get_clipboard_text
描述: 获取剪贴板文本内容

## set_clipboard_text
描述: 设置剪贴板文本内容
参数:
  - text (string) [可选]: 要设置的文本内容

## search_files
描述: 在指定目录中搜索文件
参数:
  - directory (string) [可选]: 搜索的目录路径
  - pattern (string) [可选]: 文件名匹配模式，如 .pdf 或 report
  - max_results (integer) [可选]: 最大返回数量，默认为20

## copy_file
描述: 复制文件
参数:
  - source (string) [可选]: 源文件路径
  - destination (string) [可选]: 目标路径

## move_file
描述: 移动文件
参数:
  - source (string) [可选]: 源文件路径
  - destination (string) [可选]: 目标路径

## delete_file
描述: 删除文件或文件夹
参数:
  - file_path (string) [可选]: 要删除的文件或文件夹路径

## get_running_processes
描述: 获取当前运行中的进程列表
