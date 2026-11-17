class StoryPatternError(Exception):
    """产品可预期错误的基类。"""


class ValidationError(StoryPatternError):
    """输入可解析为 JSON，但不符合故事记录约束。"""


class ConflictError(StoryPatternError):
    """稳定标识被重复用于不同的不可变内容。"""


class NotFoundError(StoryPatternError):
    """请求的本地记录不存在。"""


class AnalysisError(StoryPatternError):
    """分析请求无法按指定规则计算。"""
