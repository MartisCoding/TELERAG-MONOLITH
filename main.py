from source import get_config, TeleRagService


async def main():
    """
    Main function to start the TeleRagService.
    """
    settings = get_config()
    service = TeleRagService(settings)
    await service.start()
    await service.idle()