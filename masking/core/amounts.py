"""금액 배율 적용(형식 공통)."""


def _gran(n):
    g = 1
    while g < 1000 and n % (g * 10) == 0:
        g *= 10
    return g


def scale_amount(n, k):
    """원 단위 절삭 자릿수(최대 천 단위)를 원본과 맞춰 배율 적용."""
    g = _gran(int(n))
    return int(round(n * k / g)) * g or g
