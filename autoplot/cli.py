"""CLI entry point for autoplot."""

import argparse
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(
        description="Autoplot — interactive experiment data visualization"
    )
    parser.add_argument(
        "-c", "--config",
        default="./autoplotConfig.yml",
        help="Path to autoplotConfig.yml (default: ./autoplotConfig.yml)",
    )
    parser.add_argument(
        "-d", "--directory",
        default=None,
        help="Data directory to watch (overrides config's watch.directory)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging",
    )
    parser.add_argument(
        "--version",
        action="store_true",
        help="Show version and exit",
    )

    args = parser.parse_args()

    if args.version:
        from . import __version__
        print(f"autoplot {__version__}")
        return

    config_path = Path(args.config).resolve()

    if not config_path.exists():
        from .config import write_default_config
        write_default_config(config_path)
        print(f"Created default config at {config_path}")
        print("Edit this file to customize your autoplot setup, then re-run.")
        print("Launching with defaults...")

    from .config import load_config, apply_cli_overrides
    config = load_config(config_path)
    config = apply_cli_overrides(
        config,
        directory=args.directory,
        verbose=args.verbose,
    )

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    import nest_asyncio
    nest_asyncio.apply()

    import panel as pn
    pn.extension(notifications=True)

    data_dir = config.watch.directory
    logger.info(
        "Autoplot starting — data: %s | server: http://%s:%s",
        data_dir, config.server.address, config.server.port,
    )

    from .app import make_template
    template = make_template(config)

    logger.info(
        "Server running on http://%s:%s",
        config.server.address, config.server.port,
    )

    template.show(
        port=config.server.port,
        address=config.server.address,
        websocket_origin=config.server.allow_origin or None,
    )
