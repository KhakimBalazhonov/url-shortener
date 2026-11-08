class AppException(Exception):
    status_code: int = 500
    message: str = "Внутренняя ошибка сервера"

    def __init__(self, message: str | None = None) -> None:
        # Позволяет переопределить стандартное сообщение об ошибке при создании исключения
        self.message = message or self.message
        super().__init__(self.message)


class ShortCodeAlreadyExistsError(AppException):
    status_code = 409
    message = "Запись уже существует"


class LinkNotFoundError(AppException):
    status_code = 404
    message = "Ссылка не найдена или срок её действия истек"


class ShortCodeGenerationError(AppException):
    message = "Не удалось сгенерировать уникальный код ссылки"


class SelfReferencingUrlError(AppException):
    status_code = 400
    message = "Нельзя сокращать ссылку на этот же сервис"
