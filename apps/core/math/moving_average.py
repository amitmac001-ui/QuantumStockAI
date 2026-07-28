from statistics import mean


def sma(values, period):

    if len(values) < period:
        return None

    return mean(values[-period:])

