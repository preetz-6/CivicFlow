class DomainError(Exception):
    status_code = 400

    def __init__(self, message: str, **detail):
        super().__init__(message)
        self.message = message
        self.detail = detail


class InvalidTransition(DomainError):
    status_code = 409


class Forbidden(DomainError):
    status_code = 403


class NotFound(DomainError):
    status_code = 404


class MissingFields(DomainError):
    status_code = 422
