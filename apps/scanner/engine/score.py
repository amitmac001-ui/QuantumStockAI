from apps.scanner.engine.result import ScanResult


class ScoreEngine:

    @classmethod
    def calculate(cls, results):

        if not results:
            return {
                "total_score": 0.0,
                "confidence": 0.0,
                "verdict": "WAIT",
            }

        valid_results = [
            r for r in results
            if isinstance(r, ScanResult)
        ]

        if not valid_results:
            return {
                "total_score": 0.0,
                "confidence": 0.0,
                "verdict": "WAIT",
            }

        total_score = 0.0
        total_confidence = 0.0
        total_weight = 0.0

        for result in valid_results:

            weight = max(result.confidence, 1.0)

            total_score += result.score * weight
            total_confidence += result.confidence
            total_weight += weight

        score = round(total_score / total_weight, 2)
        confidence = round(
            total_confidence / len(valid_results),
            2,
        )

        if score >= 80:
            verdict = "BUY"
        elif score >= 60:
            verdict = "HOLD"
        elif score >= 40:
            verdict = "WAIT"
        else:
            verdict = "SELL"

        return {
            "total_score": score,
            "confidence": confidence,
            "verdict": verdict,
        }