class AppException(Exception):
    def __init__(self, message: str):
        self.message = message
        super().__init__(message)

class NotFoundException(AppException):
    def __init__(self, message: str = "Resource not found"):
        super().__init__(message)

class ValueExistsException(AppException):
    def __init__(self, message: str = "Value already exists"):
        super().__init__(message)

class NotAllowedActionException(AppException):
    def __init__(self, message: str = "Action not allowed"):
        super().__init__(message)

class AuthenticationException(AppException):
    def __init__(self, message: str = "Authentication failed"):
        super().__init__(message)

class PermissionException(AppException):
    def __init__(self, message: str = "Permission denied"):
        super().__init__(message)

class ValidationException(AppException):
    def __init__(self, message: str):
        super().__init__(message)