import os

import opik
from loguru import logger
from opik.configurator.configure import OpikConfigurator

from llm_engineering import settings


def configure_opik() -> None:
    # Check if COMET_API_KEY is set and not a placeholder value
    if (settings.COMET_API_KEY and 
        settings.COMET_PROJECT and 
        settings.COMET_API_KEY != "str"):
        try:
            client = OpikConfigurator(api_key=settings.COMET_API_KEY)
            default_workspace = client._get_default_workspace()
        except Exception:
            logger.warning("Default workspace not found. Setting workspace to None and enabling interactive mode.")
            default_workspace = None

        os.environ["OPIK_PROJECT_NAME"] = settings.COMET_PROJECT

        opik.configure(api_key=settings.COMET_API_KEY, workspace=default_workspace, use_local=False, force=True)
        logger.info("Opik configured successfully.")
    else:
        logger.warning(
            "COMET_API_KEY is not set or is a placeholder value. Set it to enable prompt monitoring with Opik (powered by Comet ML)."
        )
