# 超声语音报告系统

AI驱动的超声报告生成系统。医生口述超声所见，系统自动匹配最合适的报告模板并填充变量，大幅减少录入时间。

## 项目结构

```
ultrasound-app/
├── backend/                    # FastAPI 后端服务
│   ├── main.py                 # 入口 + 匹配引擎 + API
│   └── reports/                # 确认的报告存档
├── frontend/
│   └── index.html              # 极简Web界面（单页HTML）
├── start.bat                   # 一键启动脚本
└── README.md                   # 本文件
```

## 启动方式

### 方式一：一键启动（Windows）

双击 `start.bat`，自动安装依赖 + 启动后端。

### 方式二：手动启动

```bash
# 1. 安装依赖
pip install fastapi uvicorn pydantic python-multipart

# 2. 启动后端
cd backend
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# 3. 用浏览器打开前端
#    直接双击 frontend/index.html
```

## 访问地址

| 服务 | 地址 |
|:----|:----|
| API 服务 | http://localhost:8000 |
| API 文档 | http://localhost:8000/docs |
| 前端界面 | frontend/index.html（直接打开） |

## 操作流程

1. **输入文字** → 输入超声所见内容，按回车
2. **系统匹配** → 自动匹配最佳模板，右侧显示备选
3. **确认/修改** → 用键盘上下键切换模板，确认后提交
4. **语音替代** → 接入麦克风后可语音输入（当前版本手动输入）


## 规则库

系统依赖 `超声规则库_rulebase.json`，位于桌面。包含：

- 15个检查部位的**关键词映射**
- 426个**报告模板**（含描述和诊断）
- 4类**变量提取规则**（尺寸、百分比、速度等）
- 8类**异常指标**判断
- **匹配策略**权重配置

## 医生模板统计

- 共 141 位超声医生
- 最常见诊断：前列腺稍大(19.3%)、肝脏脂肪沉积(12.2%)、脂肪肝(9.4%)
- 模板覆盖率达 95.2%
