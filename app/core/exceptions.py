class AppError(Exception):
    status_code = 400
    code = "APP_ERROR"

    def __init__(self, message: str, status_code: int | None = None, code: str | None = None):
        super().__init__(message)
        self.message = message
        if status_code is not None:
            self.status_code = status_code
        if code is not None:
            self.code = code


class InvalidUrlError(AppError):
    code = "INVALID_URL"
    status_code = 400


class ExtractionError(AppError):
    code = "EXTRACTION_FAILED"
    status_code = 422


class UnsupportedMediaError(AppError):
    code = "UNSUPPORTED_MEDIA"
    status_code = 422


class QualityNotAvailableError(AppError):
    code = "QUALITY_NOT_AVAILABLE"
    status_code = 400


class FFmpegRequiredError(AppError):
    code = "FFMPEG_REQUIRED"
    status_code = 409


class DownloadFailedError(AppError):
    code = "DOWNLOAD_FAILED"
    status_code = 500


class JobNotFoundError(AppError):
    code = "JOB_NOT_FOUND"
    status_code = 404


class JobNotReadyError(AppError):
    code = "JOB_NOT_READY"
    status_code = 409


class MediaTooLargeError(AppError):
    code = "MEDIA_TOO_LARGE"
    status_code = 413


class CancelledByUser(Exception):
    """Raised from a yt-dlp progress hook when the job is cancelled."""
