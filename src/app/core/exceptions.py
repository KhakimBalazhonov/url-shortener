class AppException(Exception):
    status_code: int = 500
    message: str = "Внутренняя ошибка сервера"

    def __init__(self, message: str | None = None) -> None:
        self.message = message or self.message
        super().__init__(self.message)


class ShortCodeAlreadyExistsError(AppException):
    status_code = 409
    message = "Запись уже существует"


class LinkNotFoundError(AppException):
    status_code = 404
    message = "Ресурс не найден"


class ShortCodeGenerationError(AppException):
    message = "Не удалось сгенерировать уникальный код ссылки"
