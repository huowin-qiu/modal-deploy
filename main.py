import modal
import subprocess
import os
import base64

# 创建 Modal App
app = modal.App("vevc-app")

# 构建容器镜像：安装必要组件并运行初始化脚本
vevc_image = (
    modal.Image.debian_slim()
        .apt_install("curl", "unzip", "supervisor", "procps")
        .run_commands("curl -sSL https://raw.githubusercontent.com/vevc/modal-deploy/refs/heads/main/install.sh | bash")
        .pip_install("fastapi[standard]")
)

_supervisor_started = False

def start_supervisor():
    global _supervisor_started
    if not _supervisor_started:
        # 强制重新部署以加载最新的环境变量 T
        print("--- [System] Starting Supervisor Service ---")
        
        # 准备环境变量
        env_vars = os.environ.copy()
        
        # 获取 Token (兼容多种变量名)
        argo_token = os.environ.get("T") or os.environ.get("ARGO_AUTH") or os.environ.get("TOKEN")
        
        if argo_token:
            print(f"--- [System] Argo Token found (Length: {len(argo_token)}) ---")
            # 这里的 T 是日志报错中明确要求的变量名
            env_vars["T"] = argo_token
            env_vars["TOKEN"] = argo_token
        else:
            print("--- [Warning] No Argo Token found in Secrets! ---")
            
        # 启动后台守护进程
        subprocess.run(["supervisord"], env=env_vars)
        _supervisor_started = True

@app.function(
    image=vevc_image,
    # 必须关联你在 Modal 网页上创建的那个秘密组
    secrets=[modal.Secret.from_name("custom-secret")],
    min_containers=1,
    max_containers=1
)
@modal.asgi_app()
def main():
    from fastapi import FastAPI
    from fastapi.responses import PlainTextResponse
    web_app = FastAPI()
    
    # 从环境变量读取配置
    uuid = os.environ.get("U", "default-uuid")
    domain = os.environ.get("D", "your-domain.com")

    @web_app.get("/status", response_class=PlainTextResponse)
    async def status():
        # 访问此页面会触发容器启动并运行 supervisor
        start_supervisor()
        return "UP"

    @web_app.get(f"/{uuid}", response_class=PlainTextResponse)
    async def sub():
        start_supervisor()
        # 构造并返回 Base64 编码的订阅链接
        sub_url = f"vless://{uuid}@{domain}:443?encryption=none&security=tls&sni={domain}&fp=chrome&insecure=0&allowInsecure=0&type=ws&host={domain}&path=%2F%3Fed%3D2560#modal-ws-argo"
        return base64.b64encode(sub_url.encode("utf-8"))

    return web_app
