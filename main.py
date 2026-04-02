import modal
import subprocess
import os
import base64

# 创建 Modal App
app = modal.App("vevc-app")

# 构建容器镜像：在这里直接集成 cloudflared 安装，确保万无一失
vevc_image = (
    modal.Image.debian_slim()
        .apt_install("curl", "unzip", "supervisor", "procps", "ca-certificates")
        .run_commands(
            "curl -L --output cloudflared.deb https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb",
            "dpkg -i cloudflared.deb",
            "curl -sSL https://raw.githubusercontent.com/vevc/modal-deploy/refs/heads/main/install.sh | bash"
        )
        .pip_install("fastapi[standard]")
)

_supervisor_started = False

def start_supervisor():
    global _supervisor_started
    if not _supervisor_started:
        print("--- [System] Manual Tunnel Activation Start ---")
        env_vars = os.environ.copy()
        
        # 获取 Token (尝试所有可能的变量名)
        token = os.environ.get("T") or os.environ.get("ARGO_AUTH") or os.environ.get("TOKEN")
        
        if token:
            print(f"--- [System] Using Token (Length: {len(token)}) ---")
            env_vars["T"] = token
            env_vars["TOKEN"] = token
            
            # 【核心修改】：直接手动拉起 cloudflared，不经过任何中间脚本
            try:
                subprocess.Popen(
                    ["cloudflared", "tunnel", "--no-autoupdate", "run", "--token", token],
                    env=env_vars,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT
                )
                print("--- [Success] Cloudflared command executed! ---")
            except Exception as e:
                print(f"--- [Error] Failed to execute cloudflared: {e} ---")
        else:
            print("--- [Critical] No Token found in Secrets (T/ARGO_AUTH) ---")
        
        # 启动 supervisor 保持原有兼容性
        subprocess.run(["supervisord"], env=env_vars)
        _supervisor_started = True

@app.function(
    image=vevc_image,
    secrets=[modal.Secret.from_name("custom-secret")],
    min_containers=1,
    max_containers=1
)
@modal.asgi_app()
def main():
    from fastapi import FastAPI
    from fastapi.responses import PlainTextResponse
    web_app = FastAPI()
    
    uuid = os.environ.get("U", "default-uuid")
    domain = os.environ.get("D", "your-domain.com")

    @web_app.get("/status", response_class=PlainTextResponse)
    async def status():
        start_supervisor()
        return "UP"

    @web_app.get(f"/{uuid}", response_class=PlainTextResponse)
    async def sub():
        start_supervisor()
        sub_url = f"vless://{uuid}@{domain}:443?encryption=none&security=tls&sni={domain}&fp=chrome&insecure=0&allowInsecure=0&type=ws&host={domain}&path=%2F%3Fed%3D2560#modal-ws-argo"
        return base64.b64encode(sub_url.encode("utf-8"))

    return web_app
