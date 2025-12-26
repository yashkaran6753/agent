import tiktoken

class TokenTracker:
    def __init__(self, model: str = "gpt-4o-mini"):
        self.encoding = tiktoken.encoding_for_model(model)
        self.total = 0

    def count(self, text: str) -> int:
        tokens = len(self.encoding.encode(text))
        self.total += tokens
        return tokens

    def print_summary(self, start_time: float):
        import time
        elapsed = time.time() - start_time
        cost = (self.total / 1_000_000) * 0.15
        from loguru import logger
        logger.info("{}", "="*50)
        logger.info("⏱️  Time taken: {0:.1f}s ({0/60:.1f}min)", elapsed)
        logger.info("🪙  Tokens used: {0:,}", self.total)
        logger.info("💰  Est. cost: ${0:.4f}", cost)
        logger.info("{}", "="*50)