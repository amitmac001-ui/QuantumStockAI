from apps.scanner.engine.result import ScanResult


class ScoreEngine:

    @classmethod
    def calculate(cls, results):

        if not results:
            return {
                "score": 0.0,
                "confidence": 0.0,
                "signal": "WAIT",
            }

        total_score = 0.0
        total_confidence = 0.0
        total_weight = 0.0

        for result in results:

            if not isinstance(result, ScanResult):
                continue

            weight = max(
                result.confidence,
                1.0,
            )

            total_score += (
                result.score * weight
            )

            total_confidence += (
                result.confidence
            )

            total_weight += weight

        if total_weight == 0:
            return {
                "score": 0.0,
                "confidence": 0.0,
                "signal": "WAIT",
            }

        score = round(
            total_score / total_weight,
            2,
        )

        confidence = round(
            total_confidence / len(results),
            2,
        )

        if score >= 80:
            signal = "BUY"
        elif score >= 60:
            signal = "HOLD"
        elif score >= 40:
            signal = "WAIT"
        else:
            signal = "SELL"

        return {
            "score": score,
            "confidence": confidence,
            "signal": signal,
        }
