
class CrawlerException(Exception):
    """Base class for all exceptions raised by the crawler."""
    def __init__(self, message: str, details: dict = None):
        super().__init__(message)
        self.message = message
        self.details = details if details else {}

    def __str__(self):
        base_message = super().__str__()
        if self.details:
            return f"{base_message} | Details: {self.details}"
        return base_message


class CrawlerCannotSubscribe(CrawlerException):
    """Exception raised when the crawler cannot subscribe to a channel."""
    pass

class CrawlerCannotUnsubscribe(CrawlerException):
    """Exception raised when the crawler cannot unsubscribe from a channel."""
    pass

class CrawlerAlreadySubscribed(CrawlerException):
    """Exception raised when the crawler is already subscribed to a channel."""
    pass

class CrawlerChannelInvalid(CrawlerException):
    """Exception raised when the crawler channel is invalid."""
    pass
