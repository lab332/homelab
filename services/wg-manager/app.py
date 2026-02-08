#!/usr/bin/env python3

import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional

from config import settings
import wg_manager
from telegram_bot import start_bot, start_bot_webhook, stop_bot, process_webhook_update


class RestartResponse(BaseModel):
    success: bool
    internal: Optional[dict] = None
    external: Optional[dict] = None
    message: str


class StatusResponse(BaseModel):
    success: bool
    output: str
    error: str = ""


class CreateUserRequest(BaseModel):
    username: str


class DeleteUserRequest(BaseModel):
    username: str


class CreateUserResponse(BaseModel):
    success: bool
    username: str
    ip: str
    config_path: str
    qr_path: str
    message: str


class DeleteUserResponse(BaseModel):
    success: bool
    username: str
    message: str


def verify_api_key(x_api_key: Optional[str] = Header(None)):
    """Verify API key if configured."""
    if settings.api_secret and settings.api_secret != x_api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return True


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    # Start Telegram bot - webhook or polling mode
    if settings.telegram_webhook_url:
        # Webhook mode - bot runs within FastAPI
        await start_bot_webhook()
        yield
        await stop_bot()
    else:
        # Polling mode - bot runs in background task
        bot_task = asyncio.create_task(start_bot())
        yield
        await stop_bot()
        bot_task.cancel()


app = FastAPI(
    title="WireGuard Manager",
    description="API for managing WireGuard VPN tunnels",
    version="1.0.0",
    lifespan=lifespan
)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/telegram_webhook")
async def telegram_webhook(request_data: dict):
    """
    Telegram webhook endpoint.
    Receives updates from Telegram and processes them.
    """
    await process_webhook_update(request_data)
    return {"ok": True}


@app.post("/restart", response_model=RestartResponse)
async def restart_all(authorized: bool = Depends(verify_api_key)):
    internal_result, external_result = wg_manager.restart_all()
    
    success = internal_result.success and external_result.success
    
    return RestartResponse(
        success=success,
        internal={
            "success": internal_result.success,
            "output": internal_result.output,
            "error": internal_result.error
        },
        external={
            "success": external_result.success,
            "output": external_result.output,
            "error": external_result.error
        },
        message="All tunnels restarted" if success else "Some restarts failed"
    )


@app.post("/restart-internal", response_model=StatusResponse)
async def restart_internal(authorized: bool = Depends(verify_api_key)):
    result = wg_manager.restart_internal()
    return StatusResponse(
        success=result.success,
        output=result.output,
        error=result.error
    )


@app.post("/restart-external", response_model=StatusResponse)
async def restart_external(authorized: bool = Depends(verify_api_key)):
    result = wg_manager.restart_external()
    return StatusResponse(
        success=result.success,
        output=result.output,
        error=result.error
    )


@app.get("/status", response_model=dict)
async def get_status(authorized: bool = Depends(verify_api_key)):
    internal = wg_manager.get_status_internal()
    external = wg_manager.get_status_external()
    
    return {
        "internal": {
            "success": internal.success,
            "output": internal.output,
            "error": internal.error
        },
        "external": {
            "success": external.success,
            "output": external.output,
            "error": external.error
        }
    }


@app.get("/status-internal", response_model=StatusResponse)
async def get_status_internal(authorized: bool = Depends(verify_api_key)):
    result = wg_manager.get_status_internal()
    return StatusResponse(
        success=result.success,
        output=result.output,
        error=result.error
    )


@app.get("/status-external", response_model=StatusResponse)
async def get_status_external(authorized: bool = Depends(verify_api_key)):
    result = wg_manager.get_status_external()
    return StatusResponse(
        success=result.success,
        output=result.output,
        error=result.error
    )


@app.post("/create-user", response_model=CreateUserResponse)
async def create_user(request: CreateUserRequest, authorized: bool = Depends(verify_api_key)):
    try:
        result = wg_manager.create_user(request.username)
        return CreateUserResponse(
            success=True,
            username=result["username"],
            ip=result["ip"],
            config_path=result["config_path"],
            qr_path=result["qr_path"],
            message=f"User {request.username} created successfully"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/users")
async def list_users(authorized: bool = Depends(verify_api_key)):
    """List all WireGuard clients."""
    users = wg_manager.list_users()
    return {"users": users}


@app.delete("/delete-user", response_model=DeleteUserResponse)
async def delete_user(request: DeleteUserRequest, authorized: bool = Depends(verify_api_key)):
    try:
        result = wg_manager.delete_user(request.username)
        return DeleteUserResponse(
            success=True,
            username=result["username"],
            message=f"User {request.username} deleted successfully"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/user/{username}/config")
async def get_user_config(username: str, authorized: bool = Depends(verify_api_key)):
    """Get user configuration file."""
    from pathlib import Path
    config_path = Path(settings.wg_clients_dir) / username / f"{username}.conf"
    
    if not config_path.exists():
        raise HTTPException(status_code=404, detail="User not found")
    
    return FileResponse(
        config_path,
        media_type="text/plain",
        filename=f"{username}.conf"
    )


@app.get("/user/{username}/qr")
async def get_user_qr(username: str, authorized: bool = Depends(verify_api_key)):
    """Get user QR code."""
    from pathlib import Path
    qr_path = Path(settings.wg_clients_dir) / username / f"{username}.png"
    
    if not qr_path.exists():
        raise HTTPException(status_code=404, detail="QR code not found")
    
    return FileResponse(
        qr_path,
        media_type="image/png",
        filename=f"{username}.png"
    )


@app.get("/get_user_info/{user}")
async def get_user_info(user: str, authorized: bool = Depends(verify_api_key)):
    """Get user QR code."""
    from pathlib import Path
    qr_path = Path(settings.wg_clients_dir) / user / f"{user}.png"
    
    if not qr_path.exists():
        raise HTTPException(status_code=404, detail="User not found")
    
    return FileResponse(
        qr_path,
        media_type="image/png",
        filename=f"{user}.png"
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=False
    )
