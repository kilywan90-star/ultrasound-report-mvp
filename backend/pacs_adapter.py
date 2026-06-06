#!/usr/bin/env python3
"""
PACS SQL Server 适配器 — 双向数据通道

读取 PACS 视图获取患者列表 → 写入报告回 PACS

支持两种模式:
  1. SQL Server 直连 (pymssql)
  2. REST API 代理 (通过中间件)

配置通过环境变量或界面配置保存到 ultrasound.db
"""

import json, logging, re
from datetime import datetime
from pathlib import Path
from typing import Optional

try:
    import pymssql
    HAS_PYMSSQL = True
except ImportError:
    HAS_PYMSSQL = False

from pydantic import BaseModel, Field

_log = logging.getLogger(__name__)

# ── 配置模型 ──

class PacsConfig(BaseModel):
    """PACS SQL Server 连接配置"""
    host: str = Field(default="127.0.0.1", description="SQL Server 主机")
    port: int = Field(default=1433, description="SQL Server 端口")
    database: str = Field(default="PACS", description="数据库名")
    username: str = Field(default="sa", description="用户名")
    password: str = Field(default="", description="密码")
    # 视图名 (可从 PACS 管理员获取)
    patient_view: str = Field(default="V_UltrasoundWorklist", description="患者列表视图名")
    report_table: str = Field(default="T_UltrasoundReport", description="报告写入表名")
    # 额外查询
    custom_sql: str = Field(default="", description="自定义SQL(可选, 优先于视图名)")


# ── SQL Server 连接 ──

class PacsAdapter:
    """PACS SQL Server 适配器"""

    def __init__(self, config: PacsConfig):
        self.config = config
        self._conn = None

    def connect(self) -> bool:
        """尝试连接 SQL Server"""
        if not HAS_PYMSSQL:
            _log.error("pymssql not installed")
            return False
        try:
            self._conn = pymssql.connect(
                server=self.config.host,
                port=str(self.config.port),
                database=self.config.database,
                user=self.config.username,
                password=self.config.password,
                timeout=10,
                login_timeout=5,
            )
            _log.info(f"PACS connected: {self.config.host}:{self.config.port}/{self.config.database}")
            return True
        except Exception as e:
            _log.error(f"PACS connection failed: {e}")
            self._conn = None
            return False

    def test_connection(self) -> dict:
        """测试连接并返回基本信息"""
        if not self.connect():
            return {"success": False, "error": "无法连接到 SQL Server"}
        try:
            cur = self._conn.cursor()
            # 测试视图是否存在
            view = self.config.patient_view
            cur.execute(f"SELECT COUNT(*) FROM {view}")
            count = cur.fetchone()[0]
            cur.close()
            return {
                "success": True,
                "database": self.config.database,
                "view": view,
                "row_count": count,
                "server": f"{self.config.host}:{self.config.port}",
            }
        except Exception as e:
            return {"success": False, "error": str(e), "view": view}

    def fetch_patients(self, limit: int = 100, exam_type: str = None,
                       date_from: str = None, status: str = None) -> list[dict]:
        """从 PACS 视图读取患者列表"""
        if not self._conn and not self.connect():
            return []

        view = self.config.patient_view
        sql = self.config.custom_sql.strip()
        if not sql:
            sql = f"SELECT * FROM {view} WHERE 1=1"
            if exam_type:
                sql += f" AND ExamType LIKE '%{exam_type}%'"
            if date_from:
                sql += f" AND ExamDate >= '{date_from}'"
            if status:
                sql += f" AND Status = '{status}'"
            sql += f" ORDER BY ExamDate DESC, ExamTime ASC"

        # 安全限制
        if "TOP" not in sql.upper() and "LIMIT" not in sql.upper():
            sql = sql.replace("SELECT", f"SELECT TOP {limit}", 1)

        try:
            cur = self._conn.cursor()
            cur.execute(sql)
            columns = [desc[0] for desc in cur.description]
            rows = []
            for row in cur.fetchall():
                d = {}
                for i, col in enumerate(columns):
                    val = row[i]
                    if isinstance(val, datetime):
                        val = val.isoformat()
                    d[col] = val
                rows.append(d)
            cur.close()
            _log.info(f"PACS fetch: {len(rows)} patients from {view}")
            return rows
        except Exception as e:
            _log.error(f"PACS fetch error: {e}")
            return []

    def send_report(self, report: dict) -> dict:
        """将报告写回 PACS"""
        if not self._conn and not self.connect():
            return {"success": False, "error": "PACS not connected"}

        table = self.config.report_table
        try:
            cur = self._conn.cursor()
            cols = []
            vals = []
            params = []
            for k, v in report.items():
                if v is not None:
                    cols.append(k)
                    vals.append("%s")
                    params.append(v)

            sql = f"INSERT INTO {table} ({','.join(cols)}) VALUES ({','.join(vals)})"
            cur.execute(sql, tuple(params))
            self._conn.commit()
            cur.close()
            return {"success": True, "message": "报告已写入PACS"}
        except Exception as e:
            _log.error(f"PACS report send error: {e}")
            return {"success": False, "error": str(e)}

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None


# ── 配置持久化 ──

def _config_db_path() -> Path:
    return Path(__file__).parent / "pacs_config.json"

def load_pacs_config() -> PacsConfig:
    path = _config_db_path()
    if path.exists():
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
        return PacsConfig(**data)
    return PacsConfig()

def save_pacs_config(config: PacsConfig):
    path = _config_db_path()
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(config.model_dump(), f, ensure_ascii=False, indent=2)
