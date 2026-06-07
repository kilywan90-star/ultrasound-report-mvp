# 超声报告微调 环境安装指南

> 适用于本地 RTX 4070 Super (12GB) + Windows

## 1. 安装 Miniconda

下载: https://repo.anaconda.com/miniconda/Miniconda3-latest-Windows-x86_64.exe

一路默认安装，勾选 "Add to PATH"。

## 2. 创建训练环境

```powershell
# 打开 Anaconda Prompt 或 PowerShell
conda create -n ultrasound-ft python=3.12 -y
conda activate ultrasound-ft
```

## 3. CUDA 版 PyTorch

注意：必须是 CUDA 版本，不能用 CPU 版本

```powershell
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124
```

验证 CUDA:
```powershell
python -c "import torch; print(f'CUDA: {torch.cuda.is_available()}, GPU: {torch.cuda.get_device_name(0)}')"
# 应该输出: CUDA: True, GPU: NVIDIA GeForce RTX 4070 Super
```

## 4. 训练框架

```powershell
pip install transformers datasets accelerate peft bitsandbytes trl
```

## 5. 运行训练

小批量验证:
```powershell
python backend\ultrasound_ft_train.py --mode=demo --samples=2000
```

全量训练:
```powershell
python backend\ultrasound_ft_train.py --mode=train --samples=50000
```

## 6. 推理测试

```powershell
python backend\ultrasound_ft_train.py --mode=infer --model_path=output/adapter
```

## 内存说明

| 设置 | 显存 | 速度 | 说明 |
|------|------|------|------|
| batch=4, grad_accum=4 | ~8.5GB | 慢 | 稳定推荐 |
| batch=8, grad_accum=2 | ~10GB | 快 | 4070S极限 |
| batch=2, grad_accum=8 | ~6.5GB | 慢 | 其他程序占用时 |
