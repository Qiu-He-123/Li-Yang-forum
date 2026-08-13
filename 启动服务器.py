"""启动服务器（中文名入口，供双击使用；bat 内部调用 ASCII 名 start_server.py）。"""

import pathlib
import runpy

runpy.run_path(str(pathlib.Path(__file__).with_name("start_server.py")), run_name="__main__")
