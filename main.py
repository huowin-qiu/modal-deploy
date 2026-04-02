import modal
import subprocess
import os
import base64

app = modal.App("vevc-app")

# 保持镜像构建逻辑不变，增加必要的工具
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
        # 核心修改：确保环境变量中包含 ARGO_AUTH
        # 这样 install.sh 脚本内部启动 cloudflared 时能自动读取 Token
        env_vars = os.environ.copy()
        subprocess.run(["supervisord"], env=env_vars)
        _supervisor_started = True

@app.function(
    image=vevc_image,
    # 依然挂载这个密钥组
    secrets=[modal.Secret.from_name("custom-secret")],
    min_containers=1,
    max_containers=1
)
@modal.asgi_app()
def main():
    from fastapi import FastAPI
    from fastapi.responses import PlainTextResponse
    web_app = FastAPI()
    
    # 从 Secrets 中读取变量
    uuid = os.environ.get("U", "default-uuid")
    domain = os.environ.get("D", "your-domain.com")

    @web_app.get("/status", response_class=PlainTextResponse)
    async def status():
        start_supervisor()
        return "UP"

    @web_app.get(f"/{uuid}", response_class=PlainTextResponse)
    async def sub():
        start_supervisor()
        # 生成 VLESS 订阅链接
        sub_url = f"vless://{uuid}@{domain}:443?encryption=none&security=tls&sni={domain}&fp=chrome&insecure=0&allowInsecure=0&type=ws&host={domain}&path=%2F%3Fed%3D2560#modal-ws-argo"
        return base64.b64encode(sub_url.encode("utf-8"))

    return web_app
