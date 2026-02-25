class ValueExistsException(Exception):
    def __init__(self, message: str = "Value already exists"):
        self.message = message
        super().__init__(self.message)


class AuthenticationError(Exception):
    pass

class NotFoundException(Exception):
    pass

class NotAllowedActionException(Exception):
    pass