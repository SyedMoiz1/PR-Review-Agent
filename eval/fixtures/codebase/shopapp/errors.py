class ShopError(Exception):
    """Base class for errors that handlers translate into HTTP responses."""
    status = 500


class AuthError(ShopError):
    status = 401


class ValidationError(ShopError):
    status = 400


class NotFoundError(ShopError):
    status = 404
