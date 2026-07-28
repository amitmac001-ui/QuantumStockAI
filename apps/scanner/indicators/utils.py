def closes(candles):

    return [
        float(c.close)
        for c in candles
    ]


def highs(candles):

    return [
        float(c.high)
        for c in candles
    ]


def lows(candles):

    return [
        float(c.low)
        for c in candles
    ]


def opens(candles):

    return [
        float(c.open)
        for c in candles
    ]


def volumes(candles):

    return [
        c.volume
        for c in candles
    ]
