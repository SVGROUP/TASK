#!/usr/bin/env python3
"""管理员建账号 / 改密 / 设 sendkey 命令行工具（日历 + 甘特图统一）。

用 --module 选择目标模块：
    --module calendar  → 日历用户（calendar.db 的 users/sessions，带 sendkey）
    --module gantt     → 甘特图用户（gantt.db 的 gantt_users/gantt_sessions，无 sendkey）
不加 --module 默认 calendar。

用法（在项目根目录执行）：
    python -m scripts.user_add [--module calendar|gantt] add <username>
    python -m scripts.user_add [--module ...] passwd <username>
    python -m scripts.user_add [--module ...] list
    # 仅 calendar 支持：
    python -m scripts.user_add --module calendar sendkey <username> <key>
    python -m scripts.user_add --module calendar clear-sendkey <username>

飞书通知已改为统一走 ATUS /sv/notify/send（与 PTKA 一致）。飞书密钥（hook_token + secret）
存在 calendar.db 的 app_settings（全局共享，非每用户，挂载持久化不丢），也可在日历页配置：
    python -m scripts.user_add --module calendar feishu-token <hook_token>
    python -m scripts.user_add --module calendar feishu-secret <secret>   # 传空串清除 secret
    python -m scripts.user_add --module calendar clear-feishu             # 清除 hook_token + secret
ATUS 地址 / 总开关 / 渠道在 config.yaml 的 notify 段配置（不支持环境变量）。

数据库路径与服务一致：
    calendar → 环境变量 CALENDAR_TODO_DB，否则 <data_dir>/calendar.db
    gantt    → 环境变量 GANTT_DB，否则 <data_dir>/gantt.db

不开放前台注册，账号由管理员用本脚本创建。
"""
from __future__ import annotations

import getpass
import sqlite3
import sys
from contextlib import closing
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from taskmanage.common.auth import hash_password  # noqa: E402
from taskmanage.common.db import resolve_db_path  # noqa: E402

PUBLIC_USERNAME = "__public__"


# ---------------------------------------------------------------------------
# 模块配置：两套表名 / DB 路径 / 是否带 sendkey
# ---------------------------------------------------------------------------
MODULES = {
    "calendar": {
        "db_file": "calendar.db",
        "env_var": "CALENDAR_TODO_DB",
        "users_table": "users",
        "sessions_table": "sessions",
        "has_sendkey": True,
        "has_public": True,
    },
    "gantt": {
        "db_file": "gantt.db",
        "env_var": "GANTT_DB",
        "users_table": "gantt_users",
        "sessions_table": "gantt_sessions",
        "has_sendkey": False,
        "has_public": False,
    },
}


def _db_path(cfg) -> str:
    return resolve_db_path(cfg["db_file"], env_var=cfg["env_var"])


def _ensure_app_settings(conn) -> None:
    """确保全局设置表存在（与 calendar.routes SCHEMA 一致）。"""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS app_settings (
            key        TEXT PRIMARY KEY,
            value      TEXT,
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    conn.commit()


def _ensure_tables(conn, cfg) -> None:
    ut, st = cfg["users_table"], cfg["sessions_table"]
    sendkey_col = (
        "sendkey       TEXT,\n            feishu_webhook TEXT,\n            "
        if cfg["has_sendkey"]
        else ""
    )
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {ut} (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            username      TEXT    NOT NULL UNIQUE,
            password_hash TEXT    NOT NULL,
            {sendkey_col}created_at    TEXT    NOT NULL DEFAULT (datetime('now')),
            updated_at    TEXT    NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {st} (
            token      TEXT    PRIMARY KEY,
            user_id    INTEGER NOT NULL,
            expires_at TEXT    NOT NULL,
            created_at TEXT    NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    if cfg["has_public"]:
        col = "id, username, password_hash, sendkey" if cfg["has_sendkey"] else "id, username, password_hash"
        val = "0, '__public__', '!', NULL" if cfg["has_sendkey"] else "0, '__public__', '!'"
        conn.execute(f"INSERT OR IGNORE INTO {ut} ({col}) VALUES ({val})")
    # 已存在的旧库补 feishu_webhook 列
    if cfg["has_sendkey"]:
        cols = {row[1] for row in conn.execute(f"PRAGMA table_info({ut})")}
        if "feishu_webhook" not in cols:
            conn.execute(f"ALTER TABLE {ut} ADD COLUMN feishu_webhook TEXT")
    conn.commit()


def _prompt_password() -> str:
    p1 = getpass.getpass("请输入新密码（至少6位）: ")
    if len(p1) < 6:
        print("密码太短（至少6位）", file=sys.stderr)
        sys.exit(1)
    p2 = getpass.getpass("再次输入确认: ")
    if p1 != p2:
        print("两次输入不一致", file=sys.stderr)
        sys.exit(1)
    return p1


def _id_filter(cfg) -> str:
    """calendar 有 id=0 占位账号，真实用户 id>0；gantt 无占位。"""
    return " AND id > 0" if cfg["has_public"] else ""


def cmd_add(conn, cfg, username: str) -> None:
    ut = cfg["users_table"]
    if username == PUBLIC_USERNAME:
        print("该用户名为系统保留，禁止使用", file=sys.stderr)
        sys.exit(1)
    if conn.execute(f"SELECT 1 FROM {ut} WHERE username = ?", (username,)).fetchone():
        print(f"用户已存在: {username}", file=sys.stderr)
        sys.exit(1)
    pw = _prompt_password()
    conn.execute(
        f"INSERT INTO {ut} (username, password_hash) VALUES (?, ?)",
        (username, hash_password(pw)),
    )
    conn.commit()
    print(f"已创建用户: {username}")


def cmd_passwd(conn, cfg, username: str) -> None:
    ut, st = cfg["users_table"], cfg["sessions_table"]
    row = conn.execute(
        f"SELECT id FROM {ut} WHERE username = ?{_id_filter(cfg)}", (username,)
    ).fetchone()
    if row is None:
        print(f"用户不存在: {username}", file=sys.stderr)
        sys.exit(1)
    pw = _prompt_password()
    conn.execute(
        f"UPDATE {ut} SET password_hash = ?, updated_at = datetime('now') WHERE username = ?",
        (hash_password(pw), username),
    )
    conn.execute(
        f"DELETE FROM {st} WHERE user_id = (SELECT id FROM {ut} WHERE username = ?)",
        (username,),
    )
    conn.commit()
    print(f"已重置密码: {username}")


def cmd_sendkey(conn, cfg, username: str, key: str) -> None:
    ut = cfg["users_table"]
    row = conn.execute(
        f"SELECT id FROM {ut} WHERE username = ?{_id_filter(cfg)}", (username,)
    ).fetchone()
    if row is None:
        print(f"用户不存在: {username}", file=sys.stderr)
        sys.exit(1)
    if not key.strip():
        print("sendkey 不能为空", file=sys.stderr)
        sys.exit(1)
    conn.execute(
        f"UPDATE {ut} SET sendkey = ?, updated_at = datetime('now') WHERE username = ?",
        (key.strip(), username),
    )
    conn.commit()
    print(f"已设置 sendkey: {username}")


def cmd_clear_sendkey(conn, cfg, username: str) -> None:
    ut = cfg["users_table"]
    row = conn.execute(
        f"SELECT id FROM {ut} WHERE username = ?{_id_filter(cfg)}", (username,)
    ).fetchone()
    if row is None:
        print(f"用户不存在: {username}", file=sys.stderr)
        sys.exit(1)
    conn.execute(
        f"UPDATE {ut} SET sendkey = NULL, updated_at = datetime('now') WHERE username = ?",
        (username,),
    )
    conn.commit()
    print(f"已清除 sendkey: {username}")


def cmd_feishu_token(conn, cfg, token: str) -> None:
    """设置全局飞书 hook_token（存 app_settings.notify_feishu_hook_token，全局共享）。"""
    tok = token.strip()
    if not tok:
        print("hook_token 不能为空（清除请用 clear-feishu）", file=sys.stderr)
        sys.exit(1)
    _ensure_app_settings(conn)
    conn.execute(
        "INSERT OR REPLACE INTO app_settings(key, value, updated_at) "
        "VALUES ('notify_feishu_hook_token', ?, datetime('now'))",
        (tok,),
    )
    conn.commit()
    print("已设置全局飞书 hook_token")


def cmd_feishu_secret(conn, cfg, secret: str) -> None:
    """设置 / 清除全局飞书加签 secret（存 app_settings.notify_feishu_secret）。

    传空串 → 清除 secret（未开签名校验时不需要）。
    """
    sec = secret.strip()
    _ensure_app_settings(conn)
    if not sec:
        conn.execute("DELETE FROM app_settings WHERE key = 'notify_feishu_secret'")
        conn.commit()
        print("已清除全局飞书 secret")
        return
    conn.execute(
        "INSERT OR REPLACE INTO app_settings(key, value, updated_at) "
        "VALUES ('notify_feishu_secret', ?, datetime('now'))",
        (sec,),
    )
    conn.commit()
    print("已设置全局飞书 secret")


def cmd_clear_feishu(conn, cfg) -> None:
    """清除全局飞书通知密钥（hook_token + secret），回退到 config.yaml 兜底值。"""
    _ensure_app_settings(conn)
    conn.execute(
        "DELETE FROM app_settings WHERE key IN ('notify_feishu_hook_token', 'notify_feishu_secret')"
    )
    conn.commit()
    print("已清除全局飞书通知密钥（hook_token + secret）")


def cmd_list(conn, cfg) -> None:
    ut = cfg["users_table"]
    if cfg["has_sendkey"]:
        rows = conn.execute(
            f"SELECT id, username, (sendkey IS NOT NULL AND sendkey != '') AS has_key, created_at "
            f"FROM {ut} WHERE 1=1{_id_filter(cfg)} ORDER BY id"
        ).fetchall()
        # 全局飞书通知密钥（非每用户，走 ATUS）
        _ensure_app_settings(conn)
        tok = conn.execute(
            "SELECT value FROM app_settings WHERE key = 'notify_feishu_hook_token'"
        ).fetchone()
        sec = conn.execute(
            "SELECT value FROM app_settings WHERE key = 'notify_feishu_secret'"
        ).fetchone()
        print(
            f"全局飞书通知：hook_token {'已配置' if (tok and tok[0]) else '未配置'}"
            f"，secret {'已配置' if (sec and sec[0]) else '未配置'}"
        )
        if not rows:
            print("(无真实用户)")
            return
        print(f"{'id':<5}{'username':<20}{'sendkey':<10}created_at")
        for r in rows:
            print(f"{r[0]:<5}{r[1]:<20}{('已配置' if r[2] else '未配置'):<10}{r[3]}")
    else:
        rows = conn.execute(
            f"SELECT id, username, created_at FROM {ut} WHERE 1=1{_id_filter(cfg)} ORDER BY id"
        ).fetchall()
        if not rows:
            print("(无用户)")
            return
        print(f"{'id':<5}{'username':<20}created_at")
        for r in rows:
            print(f"{r[0]:<5}{r[1]:<20}{r[2]}")


def main() -> None:
    args = sys.argv[1:]
    module = "calendar"
    if args and args[0] == "--module":
        if len(args) < 2 or args[1] not in MODULES:
            print(f"未知模块，仅支持: {', '.join(MODULES)}", file=sys.stderr)
            sys.exit(1)
        module = args[1]
        args = args[2:]

    if not args:
        print(__doc__)
        sys.exit(1)

    cfg = MODULES[module]
    action = args[0]

    if action in ("sendkey", "clear-sendkey", "feishu-token", "feishu-secret", "clear-feishu") and not cfg["has_sendkey"]:
        print(f"模块 {module} 不支持该命令", file=sys.stderr)
        sys.exit(1)

    with closing(sqlite3.connect(_db_path(cfg))) as conn:
        conn.row_factory = sqlite3.Row
        _ensure_tables(conn, cfg)
        if action == "add" and len(args) == 2:
            cmd_add(conn, cfg, args[1])
        elif action == "passwd" and len(args) == 2:
            cmd_passwd(conn, cfg, args[1])
        elif action == "sendkey" and len(args) == 3:
            cmd_sendkey(conn, cfg, args[1], args[2])
        elif action == "clear-sendkey" and len(args) == 2:
            cmd_clear_sendkey(conn, cfg, args[1])
        elif action == "feishu-token" and len(args) == 2:
            cmd_feishu_token(conn, cfg, args[1])
        elif action == "feishu-secret" and len(args) == 2:
            cmd_feishu_secret(conn, cfg, args[1])
        elif action == "clear-feishu" and len(args) == 1:
            cmd_clear_feishu(conn, cfg)
        elif action == "list" and len(args) == 1:
            cmd_list(conn, cfg)
        else:
            print(__doc__)
            sys.exit(1)


if __name__ == "__main__":
    main()
