from fastapi import Request
from fastapi.responses import JSONResponse

from shared.utils.token_manager import verify_token


def authenticate(handler):
    async def wrapper(request: Request):
        auth_header = request.headers.get("authorization", "")

        if not auth_header.startswith("Bearer "):
            return JSONResponse(
                status_code=401,
                content={
                    "success": False,
                    "message": "No authentication token provided",
                },
            )

        token = auth_header.split(" ", 1)[1].strip()

        if not token:
            return JSONResponse(
                status_code=401,
                content={
                    "success": False,
                    "message": "No authentication token provided",
                },
            )

        try:
            decoded = await verify_token(token)
            request.state.user = decoded
        except Exception as e:
            return JSONResponse(
                status_code=401,
                content={
                    "success": False,
                    "message": e.args[0] if e.args else "Authentication failed",
                },
            )

        return await handler(request)

    wrapper.__name__ = handler.__name__
    return wrapper