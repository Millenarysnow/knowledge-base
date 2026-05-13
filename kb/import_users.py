from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from .config import dept_slug
from .db import connect, upsert_department, upsert_user
from .util import first_value, read_table

USER_DEPT = ["department", "dept", "dept_name", "部门", "部门名称"]
USER_NAME = ["username", "user", "账号", "用户名", "姓名"]
USER_PASSWORD = ["password", "密码", "初始密码"]
USER_ROLE = ["role", "角色"]
USER_TYPE = ["type", "类型"]


def import_users(cfg: Dict[str, Any], table_path: str) -> Dict[str, int]:
    rows = read_table(table_path)
    dept_count = 0
    user_count = 0
    with connect(cfg) as conn:
        for r in rows:
            typ = first_value(r, USER_TYPE).lower()
            dept = first_value(r, USER_DEPT)
            username = first_value(r, USER_NAME)
            password = first_value(r, USER_PASSWORD) or "kb123456"
            role = first_value(r, USER_ROLE) or "member"
            if not dept:
                continue
            if typ == "dept" or (dept and not username):
                upsert_department(conn, dept, dept_slug(dept))
                dept_count += 1
            else:
                upsert_department(conn, dept, dept_slug(dept))
                upsert_user(conn, dept, username, password, role)
                user_count += 1
        conn.commit()
    return {"departments": dept_count, "users": user_count}
