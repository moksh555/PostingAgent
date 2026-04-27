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


class NoUserIdError(AppError):
    """Raised when the request has no user ID where one is required."""

    status_code = status.HTTP_400_BAD_REQUEST
    code = "no_user_id"
    message = "User ID is required but was empty"

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
    message = "Failed to build posts"


class FailedToWriteSummaryToS3(AppError):
    """Raised when the thing that is being written to S3 fails to write"""

    status_code = status.HTTP_400_BAD_REQUEST
    code = "failed_to_write_summary_to_s3"
    message = "Failed to write summary to S3"


class FailedToSaveFinalPostData(AppError):
    """Raised when the final post data fails to be saved"""

    status_code = status.HTTP_400_BAD_REQUEST
    code = "failed_to_save_final_post_data"
    message = "Failed to save final post data"

class FailedToStartAgent(AppError):
    """Raised when the agent fails to start"""

    status_code = status.HTTP_400_BAD_REQUEST
    code = "failed_to_start_agent"
    message = "Failed to start agent"

class FailedToResumeAgent(AppError):
    """Raised when the agent fails to resume"""

    status_code = status.HTTP_400_BAD_REQUEST
    code = "failed_to_resume_agent"
    message = "Failed to resume agent"

class FailedToPutObjectToS3(AppError):
    """Raised when the object fails to be put to S3"""

    status_code = status.HTTP_400_BAD_REQUEST
    code = "failed_to_put_object_to_s3"
    message = "Failed to put object to S3"

class FailedToGetFileFromS3(AppError):
    """Raised when the object fails to be get from S3"""

    status_code = status.HTTP_400_BAD_REQUEST
    code = "failed_to_get_object_from_s3"
    message = "Failed to get object from S3"

class FailedToBuildContext(AppError):
    """Raised when the context fails to be built"""

    status_code = status.HTTP_400_BAD_REQUEST
    code = "failed_to_build_context"
    message = "Failed to build context"