"""Domain errors."""


class GrimSproutError(Exception):
    """Base class for GrimSprout errors."""


class PlantNotFoundError(GrimSproutError):
    pass


class LLMResponseError(GrimSproutError):
    pass


class DirtyRepoError(GrimSproutError):
    pass
