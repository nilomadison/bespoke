from pathlib import Path

from fastapi.templating import Jinja2Templates

from src.config import settings

_template_dir = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(_template_dir))
templates.env.globals["app_title"] = settings.app_title
