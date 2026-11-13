#!/usr/bin/env python3
from taskmanage.app import main

ver = "2026-11-13 16:22:09"
ts = 1794558129
if __name__ == "__main__":
    import os
    os.environ["TASKMANAGE_VERSION"] = ver
    os.environ["TASKMANAGE_BUILD_TS"] = str(ts)
    print(f"TaskManage 主程序启动 ver={ver}")
    main(ts)
