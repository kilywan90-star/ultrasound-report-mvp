@echo off
chcp 65001 >nul
echo ========================================
echo  超声报告 LoRA 测试 — 一键环境安装
echo ========================================
echo.
echo 步骤 1/3: 卸载 CPU 版 PyTorch...
pip uninstall torch torchvision torchaudio -y

echo.
echo 步骤 2/3: 安装 GPU 版 PyTorch (CUDA 12.1)...
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121

echo.
echo 步骤 3/3: 安装其他依赖...
pip install transformers peft accelerate

echo.
echo ========================================
echo  安装完成!
echo.
echo  运行测试:
echo  cd E:\claude\ultrasound-report-mvp\backend
echo  python scripts\benchmark_ab.py --mode lora --count 50
echo ========================================
pause
