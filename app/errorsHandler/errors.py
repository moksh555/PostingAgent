"""Custom application errors.

Each error carries an HTTP status code and a machine-readable code so
FastAPI exception handlers can translate them into consistent JSON responses.
"""

from fastapi import status  # type: ignore


class AppError(Exception):
    """Base class for all application-level errors."""

    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    code: str = "internal_error"
    message: str = "An internal error occurred"

    def __init__(self, message: str | None = None) -> None:
        super().__init__(message or self.message)
        if message:
            self.message = message


class NoPayloadError(AppError):
    """Raised when the request has no body (or an empty JSON body) where one is required."""

    status_code = status.HTTP_400_BAD_REQUEST
    code = "no_payload"
    message = "Request body is required but was empty"


class NoURLError(AppError):
    """Raised when the request has no URL where one is required."""

    status_code = status.HTTP_400_BAD_REQUEST
    code = "no_url"
    message = "URL is required but was empty"


class NoNumberOfPostsError(AppError):
    """Raised when the request has no number of posts where one is required."""

    status_code = status.HTTP_400_BAD_REQUEST
    code = "no_number_of_posts"
    message = "Number of posts is required but was empty"


class NoStartDateError(AppError):
    """Raised when the request has no start date where one is required."""

    status_code = status.HTTP_400_BAD_REQUEST
    code = "no_start_date"
    message = "Start date is required but was empty"


class FailedToScrapeURLError(AppError):
    """Raised when the request has no start date where one is required."""

    status_code = status.HTTP_400_BAD_REQUEST
    code = "failed_to_scrape_url"
    message = "Failed to scrape URL"


class FailedToBuildMarketingBriefError(AppError):
    """Raised when the request has no start date where one is required."""

    status_code = status.HTTP_400_BAD_REQUEST
    code = "failed_to_build_marketing_brief"
    message = "Failed to build marketing brief"


class FailedToBuildPosts(AppError):
    """Raised when the request has no start date where one is required."""

    status_code = status.HTTP_400_BAD_REQUEST
    code = "failed_to_build_marketing_brief"
    message = "Failed to build marketing brief"


class FailedToWriteSummaryToS3(AppError):
    """Raised when the thing that is being written to S3 fails to write"""

    status_code = status.HTTP_400_BAD_REQUEST
    code = "failed_to_write_summary_to_s3"
    message = "Failed to write summary to S3"
