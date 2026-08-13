#!/usr/bin/env python3
from taskmanage.app import main

ver = "2026-08-13 20:45:45"
ts = 1786625145
if __name__ == "__main__":
    import os
    os.environ["TASKMANAGE_VERSION"] = ver
    os.environ["TASKMANAGE_BUILD_TS"] = str(ts)
    print(f"TaskManage 主程序启动 ver={ver}")
    main(ts)
