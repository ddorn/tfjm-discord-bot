"""
This module defines all the custom Exceptions used in this project.
"""

__all__ = ["TfjmError", "UnwantedCommand"]


class TfjmError(Exception):
    def __init__(self, msg):
        self.msg = msg

    def __repr__(self):
        return self.msg


class UnwantedCommand(TfjmError):
    """
    Exception to throw during when a command was not intended.

    This exception is handled specially in `on_command_error`:
     - The message is deleted
     - A private message is send to the sender with the reason.
    """

    def __init__(self, reason=None):
        if reason is None:
            reason = "Cette commande n'était pas attendu à ce moment."
        super(UnwantedCommand, self).__init__(reason)
