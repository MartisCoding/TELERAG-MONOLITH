"""
Module for custom database exceptions
"""

class MongoHelperException(Exception):
    """
    Base class for all exceptions raised by MongoHelper.
    """
    def __init__(self, message: str, details: dict = None):
        super().__init__(message)
        self.message = message
        self.details = details if details else {}

    def __str__(self):
        base_message = super().__str__()
        if self.details:
            return f"{base_message} | Details: {self.details}"
        return base_message

class UserAlreadyExists(MongoHelperException):
    """
    Exception raised when a user already exists in the database.
    """
    pass

class UserNotFound(MongoHelperException):
    """
    Exception raised when a user is not found in the database.
    """
    pass

class ChannelAlreadyExists(MongoHelperException):
    """
    Exception raised when a channel already exists in the database.
    """
    pass

class ChannelNotFound(MongoHelperException):
    """
    Exception raised when a channel is not found in the database.
    """
    pass

class ChannelHasSubscribers(MongoHelperException):
    """
    Exception raised when a channel has subscribers and cannot be deleted.
    """
    pass

class ChannelsAlreadyPresentInUser(MongoHelperException):
    """
    Exception raised when channels are already present in a user while trying to add them.
    """
    pass

class ChannelsNotPresentInUser(MongoHelperException):
    """
    Exception raised when channels are not present in a user while trying to remove them.
    """
    pass

class CannotEndTransaction(MongoHelperException):
    """
    Exception raised when a transaction cannot be ended. Due to some reason.
    """
    pass
