#!/usr/bin/env python3
from taskmanage.app import main

ver = "2026-10-25 18:47:37"
ts = 1792925257
if __name__ == "__main__":
    import os
    os.environ["TASKMANAGE_VERSION"] = ver
    os.environ["TASKMANAGE_BUILD_TS"] = str(ts)
    print(f"TaskManage 主程序启动 ver={ver}")
    main(ts)
