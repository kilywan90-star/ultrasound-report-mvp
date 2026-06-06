"""PACS 配置管理 API — 界面适配按钮的后端"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from pacs_adapter import (
    PacsConfig, PacsAdapter, load_pacs_config, save_pacs_config,
)

router = APIRouter(prefix="/api/pacs-config", tags=["PACS配置"])


class PacsConfigRequest(BaseModel):
    host: str = "127.0.0.1"
    port: int = 1433
    database: str = "PACS"
    username: str = "sa"
    password: str = ""
    patient_view: str = "V_UltrasoundWorklist"
    report_table: str = "T_UltrasoundReport"
    custom_sql: str = ""


@router.get("/")
async def get_pacs_config():
    """获取当前 PACS 配置"""
    config = load_pacs_config()
    return JSONResponse({
        "success": True,
        "config": config.model_dump(),
    })


@router.post("/save")
async def save_pacs_config_endpoint(req: PacsConfigRequest):
    """保存 PACS 连接配置"""
    config = PacsConfig(**req.model_dump())
    save_pacs_config(config)
    return JSONResponse({
        "success": True,
        "message": "PACS 配置已保存",
    })


@router.post("/test")
async def test_pacs_connection(req: PacsConfigRequest):
    """测试 PACS SQL Server 连接并读取视图"""
    config = PacsConfig(**req.model_dump())
    adapter = PacsAdapter(config)
    result = adapter.test_connection()
    adapter.close()
    return JSONResponse(result)


@router.get("/patients")
async def fetch_pacs_patients(
    limit: int = 100,
    exam_type: str = None,
    date_from: str = None,
    status: str = None,
):
    """从 PACS 视图获取患者列表 (实时查询)"""
    config = load_pacs_config()
    adapter = PacsAdapter(config)
    if not adapter.connect():
        adapter.close()
        return JSONResponse({
            "success": False,
            "error": "无法连接 PACS SQL Server，请检查配置",
            "patients": [],
        })

    patients = adapter.fetch_patients(
        limit=limit,
        exam_type=exam_type,
        date_from=date_from,
        status=status,
    )
    adapter.close()

    return JSONResponse({
        "success": True,
        "count": len(patients),
        "patients": patients,
    })
