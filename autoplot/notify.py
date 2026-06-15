import logging

logger = logging.getLogger(__name__)


def notify_error(msg: str, duration: int = 0) -> None:
    logger.error(msg)
    import panel as pn
    pn.state.notifications.error(msg, duration=duration)


def notify_warning(msg: str, duration: int = 5000) -> None:
    logger.warning(msg)
    import panel as pn
    pn.state.notifications.warning(msg, duration=duration)


def notify_info(msg: str, duration: int = 3000) -> None:
    logger.info(msg)
    import panel as pn
    pn.state.notifications.info(msg, duration=duration)
