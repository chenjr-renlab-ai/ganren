class PlatformError(Exception):
    code: str = "error"
    http_status: int = 500

    def __init__(self, message: str, **extras):
        super().__init__(message)
        self.extras = extras

class MissingDecisionRecord(PlatformError):
    code = "missing_decision_record"
    http_status = 400

class InvalidTags(PlatformError):
    code = "invalid_tags"
    http_status = 400

class CtxTooLarge(PlatformError):
    code = "ctx_too_large"
    http_status = 400

class NotAllowed(PlatformError):
    code = "not_allowed"
    http_status = 403

class TaskNotFound(PlatformError):
    code = "task_not_found"
    http_status = 404

class QuestionNotFound(PlatformError):
    code = "question_not_found"
    http_status = 404

class AlreadyClaimed(PlatformError):
    code = "already_claimed"
    http_status = 409

class InvalidState(PlatformError):
    code = "invalid_state"
    http_status = 409

class VersionConflict(PlatformError):
    code = "version_conflict"
    http_status = 409
