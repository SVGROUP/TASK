#!/usr/bin/env python3
from taskmanage.app import main

ver = "2026-10-25 17:18:30"
ts = 1792919910
if __name__ == "__main__":
    import os
    os.environ["TASKMANAGE_VERSION"] = ver
    os.environ["TASKMANAGE_BUILD_TS"] = str(ts)
    print(f"TaskManage 主程序启动 ver={ver}")
    main(ts)
