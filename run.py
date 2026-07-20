#!/usr/bin/env python3
from taskmanage.app import main

ver = "2026-07-20 12:06:25"
ts = 1784549185
if __name__ == "__main__":
    import os
    os.environ["TASKMANAGE_VERSION"] = ver
    os.environ["TASKMANAGE_BUILD_TS"] = str(ts)
    print(f"TaskManage 主程序启动 ver={ver}")
    main(ts)
