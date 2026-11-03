"""FastAPI Application entry point."""
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from starlette.middleware.sessions import SessionMiddleware
from app.config import settings
from app.routes.guest import router as guest_router, templates
from app.routes.staff import router as staff_router
from app.routes.enquire import router as enquire_router

app = FastAPI(title=settings.app_name)

# Session middleware for signed cookies and CSRF
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.secret_key,
    session_cookie="plantation_session",
    max_age=3600 * 24,
    same_site="lax",
    https_only=(settings.environment == "production")
)

# Static files
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Include Routers
app.include_router(guest_router)
app.include_router(staff_router)
app.include_router(enquire_router)


# Global error handlers
@app.exception_handler(404)
async def custom_404_handler(request: Request, exc):
    return templates.TemplateResponse(request, "errors/404.html", {
        "app_name": settings.app_name
    }, status_code=404)


@app.exception_handler(500)
async def custom_500_handler(request: Request, exc):
    return templates.TemplateResponse(request, "errors/500.html", {
        "app_name": settings.app_name
    }, status_code=500)
